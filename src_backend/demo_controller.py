import asyncio
import logging

from agents.diagnosis_agent import run_diagnosis
from shared.config import INCIDENT_LOOP_INTERVAL, VOICE_SESSION_TIMEOUT, TWILIO_CALLING_TIMEOUT
from shared.state import Phase, demo_state
from websocket_server import broadcast_phase_change, build_system_status, manager

logger = logging.getLogger(__name__)

PHASE_DURATIONS: dict[Phase, float] = {
    Phase.INCIDENT_DETECTED: 3.0,
    Phase.DIAGNOSING: 0.0,
    Phase.CALLING: 0.0,
    Phase.RECOVERING: 5.0,
    Phase.RESOLVED: 3.0,
}

DIAGNOSIS_TIMEOUT: float = 30.0


class DemoController:
    def __init__(self) -> None:
        self._loop_task: asyncio.Task | None = None
        self._phase_task: asyncio.Task | None = None
        self._auto_triggered: bool = False

    async def start(self) -> None:
        self._loop_task = asyncio.create_task(self._auto_loop())
        logger.info("Demo controller started")

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        if self._phase_task:
            self._phase_task.cancel()
            self._phase_task = None
        logger.info("Demo controller stopped")

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
                await self._run_diagnosis()
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
                await manager.broadcast(build_system_status(demo_state))

    async def _run_diagnosis(self) -> None:
        service = demo_state.incident.service if demo_state.incident else "aurora-db"
        incident_id = demo_state.incident.incident_id if demo_state.incident else "unknown"
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": f"Diagnosis agent running analysis on {service}...", "level": "info"},
        })
        try:
            rca_summary = await asyncio.wait_for(
                run_diagnosis(service, incident_id),
                timeout=DIAGNOSIS_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Diagnosis agent timed out, using fallback RCA")
            from agents.diagnosis_agent import _fallback_rca
            rca_summary = _fallback_rca(service, incident_id)
        except Exception as e:
            logger.error(f"Diagnosis agent error: {e}")
            from agents.diagnosis_agent import _fallback_rca
            rca_summary = _fallback_rca(service, incident_id)
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": f"RCA Complete: {rca_summary[:200]}", "level": "success"},
        })
        await manager.broadcast({
            "type": "phase_update",
            "payload": {
                "phase": "DIAGNOSING",
                "agent": "diagnosis",
                "details": rca_summary,
                "incident_id": incident_id,
            },
        })

    async def _run_voice_session(self) -> None:
        voice_mode = demo_state.voice_mode
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
