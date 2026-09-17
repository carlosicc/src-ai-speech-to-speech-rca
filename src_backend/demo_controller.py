import asyncio
import logging
from typing import Any

from shared.config import INCIDENT_LOOP_INTERVAL, VOICE_SESSION_TIMEOUT, TWILIO_CALLING_TIMEOUT
from shared.state import Phase, demo_state
from websocket_server import broadcast_phase_change, build_system_status, manager

# Backstop for a call that is answered but useless (voicemail, phone in a pocket): the media
# stream keeps flowing so the idle timer never fires. A real conversation runs 50-60s.
VOICE_HARD_CEILING: float = 120.0

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
        self._voice_session_ran: bool = False

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
        self._voice_session_ran = False

    async def _broadcast_phase_change(self) -> None:
        await broadcast_phase_change(demo_state)

    async def trigger_incident(self, service: str = "aurora-db", auto: bool = False) -> None:
        if demo_state.phase != Phase.HEALTHY:
            return
        self._auto_triggered = auto
        self._voice_session_ran = False
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
                await self._run_parallel_diagnosis_and_call()
                if demo_state.phase == Phase.HEALTHY:
                    break
                # After voice session ends, advance through remaining phases normally
                if demo_state.phase in (Phase.RECOVERING, Phase.RESOLVED):
                    duration = PHASE_DURATIONS.get(demo_state.phase, 3.0)
                    await asyncio.sleep(duration)
                    demo_state.advance_phase()
                    await broadcast_phase_change(demo_state)
                    continue
                continue
            elif demo_state.phase == Phase.CALLING:
                if self._voice_session_ran:
                    logger.warning("Voice session already ran this incident — skipping re-entry, advancing phase")
                    demo_state.advance_phase()
                    await broadcast_phase_change(demo_state)
                    continue
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

        await self._ensure_link_restored()

    async def _ensure_link_restored(self) -> None:
        """Safety net: a run must never end with the TCP/3306 rule still revoked.

        The rule is normally restored by the DBA authorising apply_network_fix, or by RESET.
        When the voice call never gets that far (no answer, timeout, Twilio failure) the demo
        would otherwise return to HEALTHY with the database still unreachable, leaving the 3D
        link red and the presenter button disabled until someone pressed RESET.
        """
        from shared.network_operations import restore_db_access
        from shared.state import LinkStatus
        from websocket_server import broadcast_link_error, set_link_status

        if demo_state.link_status == LinkStatus.CONNECTED:
            return

        result = await restore_db_access()
        if result["status"] in ("success", "already_present"):
            logger.info(f"End of run: restored TCP/3306 rule (result={result['status']})")
            await set_link_status(LinkStatus.CONNECTED, None, result["message"])
        else:
            logger.error(f"End of run: failed to restore TCP/3306 rule: {result}")
            demo_state.link_status = LinkStatus.DISCONNECTED
            await broadcast_link_error(result["message"])

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

    async def _run_parallel_diagnosis_and_call(self) -> None:
        """Run diagnosis and voice call in parallel.

        The Twilio+Nova Sonic setup takes ~7s. By the time the DBA picks up and
        the agent starts speaking, diagnosis tools have already finished.
        """
        service = demo_state.incident.service if demo_state.incident else "aurora-db"
        incident_id = demo_state.incident.incident_id if demo_state.incident else "unknown"

        # Start diagnosis in background (fire-and-forget — results broadcast to UI)
        diagnosis_task = asyncio.create_task(self._run_diagnosis_only(service, incident_id))

        # Immediately advance to CALLING and start voice session
        await asyncio.sleep(0.5)  # Brief pause for UI to show DIAGNOSING
        demo_state.phase = Phase.CALLING
        demo_state.active_agent = "voice"
        await broadcast_phase_change(demo_state)
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": "Master Agent → escalating to on-call DBA via voice...", "level": "warn"},
        })

        await self._run_voice_session()

        # Ensure diagnosis completes (it should be done by now)
        if not diagnosis_task.done():
            try:
                await asyncio.wait_for(diagnosis_task, timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                diagnosis_task.cancel()

    async def _run_diagnosis_only(self, service: str, incident_id: str) -> None:
        """Run diagnosis agent standalone — broadcasts RCA to UI but doesn't block."""
        from agents.master_agent import _broadcast, _notify_agent_activity

        await _notify_agent_activity("master", "active")
        await _broadcast({
            "type": "agent_log",
            "payload": {"message": "Master Agent activated — following SoP...", "level": "warn"},
        })
        await _notify_agent_activity("master", "assessing")
        await _broadcast({
            "type": "agent_log",
            "payload": {"message": f"Severity: CRITICAL — {service} is a production dependency", "level": "error"},
        })

        await _notify_agent_activity("diagnosis", "running")
        await _broadcast({
            "type": "agent_log",
            "payload": {"message": "Diagnosis agent activated. Pulling logs and running health checks...", "level": "info"},
        })

        from agents.diagnosis_agent import run_diagnosis, _fallback_rca
        try:
            rca = await asyncio.wait_for(run_diagnosis(service, incident_id), timeout=30.0)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Diagnosis failed in parallel: {e}")
            rca = _fallback_rca(service, incident_id)

        await _broadcast({
            "type": "agent_log",
            "payload": {"message": f"RCA Complete: {rca[:200]}", "level": "success"},
        })
        await _notify_agent_activity("diagnosis", "complete")

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
        self._voice_session_ran = True
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

        idle_timeout = TWILIO_CALLING_TIMEOUT if voice_mode in ("mode_a", "mode_b") else VOICE_SESSION_TIMEOUT
        idle_elapsed = 0.0
        total_elapsed = 0.0
        from voice.voice_router import voice_router
        while demo_state.phase == Phase.CALLING and total_elapsed < VOICE_HARD_CEILING:
            await asyncio.sleep(1.0)
            total_elapsed += 1.0
            # Reset idle timer if Twilio audio is actively flowing
            handler = self._get_twilio_handler(voice_router)
            if handler and handler.active:
                idle_elapsed = 0.0
            else:
                idle_elapsed += 1.0
            if idle_elapsed >= idle_timeout:
                break

        if voice_router.active:
            logger.info(f"Voice session timeout reached (idle={idle_elapsed:.0f}s, total={total_elapsed:.0f}s), stopping")
            await voice_router.stop_session()

        demo_state.active_agent = "master"

    @staticmethod
    def _get_twilio_handler(voice_router) -> Any:
        """Get the active TwilioMediaStreamHandler if one exists."""
        twilio_session = voice_router.twilio_session
        if twilio_session:
            return getattr(twilio_session, "_handler", None)
        return None

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
