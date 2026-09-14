import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect

from shared.state import DemoState, LinkStatus, Phase, demo_state

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            pass
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
        data = json.dumps(message)
        disconnected: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            try:
                self.active_connections.remove(conn)
            except ValueError:
                pass


manager = ConnectionManager()

LINK_ID = "ecs-aurora"


def build_link_update(status: str, request_id: Optional[str] = None, message: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"link_id": LINK_ID, "status": status, "message": message}
    if request_id:
        payload["request_id"] = request_id
    return {"type": "infrastructure_link_update", "payload": payload}


async def set_link_status(status: LinkStatus, request_id: Optional[str] = None, message: str = "") -> None:
    demo_state.link_status = status
    await manager.broadcast(build_link_update(status.value, request_id, message))


async def broadcast_link_error(message: str, request_id: Optional[str] = None) -> None:
    await manager.broadcast(build_link_update("error", request_id, message))


async def sync_link_status_from_aws() -> None:
    """Startup pre-check: make the real SG rule and demo_state.link_status agree."""
    from shared.network_operations import check_sg_rule_exists, restore_db_access

    if await check_sg_rule_exists():
        demo_state.link_status = LinkStatus.CONNECTED
        logger.info("Startup pre-check: SG rule present — database reachable")
        return
    logger.warning("Startup pre-check: SG rule for port 3306 is MISSING — auto-restoring")
    result = await restore_db_access()
    logger.info(f"Startup pre-check: restore_db_access result={result['status']}")
    if result["status"] in ("success", "already_present"):
        demo_state.link_status = LinkStatus.CONNECTED
    else:
        demo_state.link_status = LinkStatus.DISCONNECTED


def build_system_status(state: DemoState) -> dict[str, Any]:
    services = ["aurora-db", "ecs-cluster", "lambda", "api-gateway", "s3-storage", "monitoring", "network"]
    systems = []
    for svc in services:
        is_affected = state.incident and state.incident.service == svc and state.phase != Phase.HEALTHY
        systems.append({"name": svc, "status": "degraded" if is_affected else "healthy"})
    return {
        "type": "system_status",
        "payload": {
            "systems": systems,
            "phase": state.phase.value,
            "voice_mode": state.voice_mode,
            "auto_advance": state.auto_advance,
            "active_agent": state.active_agent,
            "infrastructure_links": [{
                "id": LINK_ID,
                "source": "ecs-cluster",
                "target": "aurora-db",
                "protocol": "tcp",
                "port": 3306,
                "status": state.link_status.value,
            }],
        },
    }


def build_phase_update(state: DemoState, details: str = "") -> dict[str, Any]:
    agent_map: dict[Phase, str] = {
        Phase.INCIDENT_DETECTED: "master",
        Phase.DIAGNOSING: "diagnosis",
        Phase.CALLING: "voice",
        Phase.RECOVERING: "master",
        Phase.RESOLVED: "master",
    }
    return {
        "type": "phase_update",
        "payload": {
            "phase": state.phase.value,
            "agent": agent_map.get(state.phase, ""),
            "details": details,
            "incident_id": state.incident.incident_id if state.incident else None,
        },
    }


PHASE_LOG_MESSAGES: dict[Phase, tuple[str, str]] = {
    Phase.INCIDENT_DETECTED: ("Incident detected. Activating response protocol.", "error"),
    Phase.DIAGNOSING: ("Diagnosis agent activated. Pulling logs and running health checks...", "warn"),
    Phase.CALLING: ("Escalation triggered. Connecting to on-call DBA via voice...", "warn"),
    Phase.RECOVERING: ("DBA confirmed. Executing recovery procedure...", "info"),
    Phase.RESOLVED: ("All systems restored. Incident resolved successfully.", "success"),
    Phase.HEALTHY: ("System nominal. Returning to monitoring state.", "info"),
}


async def broadcast_phase_change(state: DemoState) -> None:
    await manager.broadcast(build_phase_update(state))
    msg, level = PHASE_LOG_MESSAGES.get(state.phase, ("", "info"))
    if msg:
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": msg, "level": level},
        })


async def handle_client_message(data: str) -> None:
    try:
        message = json.loads(data)
    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON from client: {data[:100]}")
        return

    msg_type = message.get("type", "")
    payload = message.get("payload", {})

    if msg_type == "break_database":
        request_id = payload.get("request_id")
        if demo_state.phase != Phase.HEALTHY:
            logger.info("break_database ignored: phase is not HEALTHY")
            return
        if demo_state.link_status == LinkStatus.DISCONNECTING:
            logger.warning("break_database ignored: a disconnect is already in progress")
            return
        from shared.network_operations import revoke_db_access
        await set_link_status(LinkStatus.DISCONNECTING, request_id, "Removing ECS -> Aurora TCP/3306 rule")
        result = await revoke_db_access()
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": f"Break DB: {result['message']}", "level": "warn"},
        })
        if result["status"] in ("success", "already_revoked"):
            await set_link_status(LinkStatus.DISCONNECTED, request_id, result["message"])
            from demo_controller import demo_controller
            await demo_controller.trigger_incident("aurora-db")
        else:
            demo_state.link_status = LinkStatus.CONNECTED
            await broadcast_link_error(result["message"], request_id)

    elif msg_type == "trigger_incident":
        service = payload.get("service", "aurora-db")
        if demo_state.phase == Phase.HEALTHY:
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

    elif msg_type == "reset_demo":
        from demo_controller import demo_controller
        from voice.voice_router import voice_router
        await demo_controller.cancel_simulation()
        await voice_router.stop_session()
        await _cancel_inflight_twilio_call()
        demo_state.reset()
        from shared.network_operations import restore_db_access
        await set_link_status(LinkStatus.RESTORING, None, "Restoring ECS -> Aurora TCP/3306 rule")
        restore_result = await restore_db_access()
        if restore_result["status"] in ("success", "already_present"):
            logger.info(f"Reset: SG rule confirmed present (result={restore_result['status']})")
            await set_link_status(LinkStatus.CONNECTED, None, restore_result["message"])
        else:
            logger.warning(f"Reset: SG rule restore returned unexpected status: {restore_result}")
            demo_state.link_status = LinkStatus.DISCONNECTED
            await broadcast_link_error(restore_result["message"])
        await manager.broadcast(build_system_status(demo_state))
        await manager.broadcast({
            "type": "agent_log",
            "payload": {"message": "Demo reset. All systems healthy.", "level": "info"},
        })

    elif msg_type == "set_phone_number":
        phone = payload.get("phone_number", "")
        if phone.startswith("+") and 7 <= len(phone) <= 16:
            demo_state.phone_number = phone
            logger.info(f"Phone number set to {phone}")

    elif msg_type == "set_voice_mode":
        mode = payload.get("mode", "")
        if mode in ("mode_a", "mode_b", "mode_c"):
            demo_state.voice_mode = mode
            logger.info(f"Voice mode set to {mode}")

    elif msg_type == "set_auto_advance":
        enabled = payload.get("enabled", True)
        demo_state.auto_advance = bool(enabled)
        logger.info(f"Auto advance set to {demo_state.auto_advance}")

    elif msg_type == "audio_input":
        audio = payload.get("audio", "")
        if audio and demo_state.phase == Phase.CALLING and demo_state.voice_mode == "mode_c":
            from voice.voice_router import voice_router
            if not voice_router.active:
                await _start_voice_session()
            await voice_router.receive_audio(audio)

    elif msg_type == "stop_voice":
        from voice.voice_router import voice_router
        await voice_router.stop_session()

    else:
        logger.warning(f"Unknown message type: {msg_type}")


async def _start_voice_session() -> None:
    from voice.voice_router import voice_router

    async def on_audio_output(audio_base64: str) -> None:
        await manager.broadcast({
            "type": "audio_output",
            "payload": {"audio": audio_base64},
        })

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
        logger.info("Voice session ended naturally")
        if demo_state.phase == Phase.CALLING:
            demo_state.advance_phase()
            await broadcast_phase_change(demo_state)

    logger.info("Starting voice session (triggered by first audio_input)")
    await voice_router.start_session(
        on_audio_output=on_audio_output,
        on_transcript=on_transcript,
        on_session_end=on_session_end,
    )


async def _cancel_inflight_twilio_call() -> None:
    """Hang up any in-flight Twilio call when demo resets."""
    try:
        from voice.voice_router import voice_router
        twilio_session = voice_router.twilio_session
        if twilio_session and twilio_session.call_sid:
            import asyncio
            from shared.config import load_twilio_credentials
            account_sid, auth_token, _ = load_twilio_credentials()
            if account_sid and auth_token:
                from twilio.rest import Client
                client = Client(account_sid, auth_token)
                await asyncio.to_thread(
                    client.calls(twilio_session.call_sid).update,
                    status="completed",
                )
                logger.info(f"Cancelled in-flight Twilio call: {twilio_session.call_sid}")
    except Exception as e:
        logger.warning(f"Failed to cancel Twilio call on reset: {e}")


def configure_voice_router_url(host: str, scheme: str = "wss") -> None:
    """Set the public media stream URL on the voice router for Mode B."""
    from voice.voice_router import voice_router
    url = f"{scheme}://{host}/twilio/media-stream"
    voice_router.set_media_stream_url(url)
    logger.info(f"Voice router media stream URL set to: {url}")
