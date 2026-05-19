import asyncio
import logging

from shared.config import INCIDENT_LOOP_INTERVAL, VOICE_SESSION_TIMEOUT, TWILIO_CALLING_TIMEOUT
from shared.state import Phase, demo_state
from websocket_server import broadcast_phase_change, build_system_status, manager

logger = logging.getLogger(__name__)

PHASE_DURATIONS: dict[Phase, float] = {
    Phase.INCIDENT_DETECTED: 2.0,
    Phase.DIAGNOSING: 0.0,
    Phase.CALLING: 0.0,
    Phase.RECOVERING: 3.0,
    Phase.RESOLVED: 2.0,
}

ORCHESTRATION_TIMEOUT: float = 150.0


class DemoController:
    def __init__(self) -> None:
        self._loop_task: asyncio.Task | None = None
        self._phase_task: asyncio.Task | None = None
        self._auto_triggered: bool = False

    async def start(self) -> None:
        from agents.master_agent import set_broadcast
        from agents.diagnosis_agent import set_diagnosis_broadcast
        set_broadcast(manager.broadcast, self._broadcast_phase_change)
        set_diagnosis_broadcast(manager.broadcast)
        self._loop_task = asyncio.create_task(self._auto_loop())
        logger.info("Demo controller started")

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        await self.cancel_simulation()
        logger.info("Demo controller stopped")

    async def cancel_simulation(self) -> None:
        """Cancel any in-progress phase orchestration task."""
        if self._phase_task and not self._phase_task.done():
            self._phase_task.cancel()
            try:
                await self._phase_task
            except asyncio.CancelledError:
                pass
        self._phase_task = None
        self._auto_triggered = False

    async def _broadcast_phase_change(self) -> None:
        await broadcast_phase_change(demo_state)

    async def trigger_incident(self, service: str = "aurora-db", auto: bool = False) -> None:
        if demo_state.phase != Phase.HEALTHY:
            return
        self._auto_triggered = auto
        demo_state.trigger_incident(service)
        await manager.broadcast({
            "type": "incident_detected",
            "payload": {
                "incident_id": demo_state.incident.incident_id,
                "severity": demo_state.incident.severity,
                "service": service,
            },
        })
        await broadcast_phase_change(demo_state)
        self._phase_task = asyncio.create_task(self._run_phases())

    async def _run_phases(self) -> None:
        while demo_state.phase != Phase.HEALTHY:
            if demo_state.phase == Phase.DIAGNOSING:
                await self._run_master_orchestration()
                # Master agent sets phase to CALLING internally via activate_voice_call.
                # Don't advance — fall through to the next loop iteration which handles CALLING.
                if demo_state.phase == Phase.CALLING:
                    continue
            elif demo_state.phase == Phase.CALLING:
                await self._run_voice_session()
            else:
                duration = PHASE_DURATIONS.get(demo_state.phase, 3.0)
                await asyncio.sleep(duration)
            if demo_state.phase == Phase.HEALTHY:
                break
            demo_state.advance_phase()
            await broadcast_phase_change(demo_state)
            if demo_state.phase == Phase.HEALTHY:
                demo_state.active_agent = None
                await manager.broadcast(build_system_status(demo_state))

    async def _run_master_orchestration(self) -> None:
        """Master agent orchestrates: assess → diagnose → escalate to voice."""
        service = demo_state.incident.service if demo_state.incident else "aurora-db"
        incident_id = demo_state.incident.incident_id if demo_state.incident else "unknown"
        demo_state.active_agent = "master"

        from agents.master_agent import run_master_orchestration, run_master_orchestration_fallback

        try:
            await asyncio.wait_for(
                run_master_orchestration(service, incident_id),
                timeout=ORCHESTRATION_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Master agent timed out, running fallback orchestration")
            demo_state.active_agent = "master"
            try:
                await asyncio.wait_for(
                    run_master_orchestration_fallback(service, incident_id),
                    timeout=60.0,
                )
            except (asyncio.TimeoutError, Exception) as e:
                logger.error(f"Fallback orchestration also failed: {e}")
                await self._force_advance_to_calling(service, incident_id)
        except Exception as e:
            logger.error(f"Master agent error: {e}, running fallback")
            try:
                await asyncio.wait_for(
                    run_master_orchestration_fallback(service, incident_id),
                    timeout=60.0,
                )
            except (asyncio.TimeoutError, Exception) as fallback_err:
                logger.error(f"Fallback also failed: {fallback_err}")
                await self._force_advance_to_calling(service, incident_id)

        # After orchestration, if still in DIAGNOSING (master advanced to CALLING already),
        # check if phase was already changed by the master agent tools
        if demo_state.phase == Phase.DIAGNOSING:
            # Master didn't advance phase — do it manually
            await manager.broadcast({
                "type": "phase_update",
                "payload": {
                    "phase": "DIAGNOSING",
                    "agent": "master",
                    "details": "Orchestration complete, advancing to escalation.",
                    "incident_id": incident_id,
                },
            })

    async def _force_advance_to_calling(self, service: str, incident_id: str) -> None:
        """Last-resort: force demo to CALLING phase so it doesn't hang."""
        logger.warning("Force-advancing to CALLING phase")
        demo_state.phase = Phase.CALLING
        demo_state.active_agent = "voice"
        await broadcast_phase_change(demo_state)
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": "Failsafe: advancing to voice escalation...", "level": "warn"},
        })

    async def _run_voice_session(self) -> None:
        voice_mode = demo_state.voice_mode
        demo_state.active_agent = "voice"
        # Only place real phone calls on manual trigger — never on auto-loop
        if voice_mode in ("mode_a", "mode_b") and self._auto_triggered:
            logger.info(f"Auto-loop: skipping real call (mode={voice_mode}), using simulated call")
            voice_mode = "mode_c"

        await manager.broadcast({
            "type": "call_started",
            "payload": {
                "incident_id": demo_state.incident.incident_id if demo_state.incident else "",
                "phone_number": demo_state.phone_number,
                "voice_mode": voice_mode,
            },
        })

        if voice_mode == "mode_b":
            await manager.broadcast({
                "type": "agent_log",
                "payload": {"message": f"Placing call to {demo_state.phone_number} (Mode B: Twilio + Bedrock)...", "level": "info"},
            })
            await self._start_twilio_voice_session()
        else:
            await manager.broadcast({
                "type": "agent_log",
                "payload": {"message": "Waiting for on-call DBA to connect (click Start Mic)...", "level": "info"},
            })

        timeout = TWILIO_CALLING_TIMEOUT if voice_mode in ("mode_a", "mode_b") else VOICE_SESSION_TIMEOUT
        elapsed = 0.0
        while demo_state.phase == Phase.CALLING and elapsed < timeout:
            await asyncio.sleep(1.0)
            elapsed += 1.0

        from voice.voice_router import voice_router
        if voice_router.active:
            logger.info("Voice session timeout reached, stopping")
            await voice_router.stop_session()

        demo_state.active_agent = "master"

    async def _start_twilio_voice_session(self) -> None:
        """Start a Mode B voice session (outbound Twilio call)."""
        from voice.voice_router import voice_router

        async def on_transcript(text: str, speaker: str) -> None:
            await manager.broadcast({
                "type": "call_transcript",
                "payload": {"speaker": speaker, "text": text},
            })
            await manager.broadcast({
                "type": "agent_log",
                "payload": {"message": f"[{speaker.upper()}] {text}", "level": "info"},
            })

        async def on_session_end() -> None:
            logger.info("Twilio voice session ended")
            if demo_state.phase == Phase.CALLING:
                demo_state.advance_phase()
                await broadcast_phase_change(demo_state)

        await voice_router.start_session(
            on_audio_output=lambda _: asyncio.sleep(0),
            on_transcript=on_transcript,
            on_session_end=on_session_end,
        )

    async def _auto_loop(self) -> None:
        while True:
            await asyncio.sleep(INCIDENT_LOOP_INTERVAL)
            if not demo_state.auto_advance:
                continue
            if demo_state.phase != Phase.HEALTHY:
                continue
            if not manager.active_connections:
                continue
            logger.info("Auto-loop triggering incident")
            await self.trigger_incident("aurora-db", auto=True)


demo_controller = DemoController()
