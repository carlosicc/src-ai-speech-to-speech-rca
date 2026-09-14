import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from demo_controller import demo_controller
from monitoring_simulator import monitoring_simulator
from shared.config import API_TOKEN, WS_PORT
from shared.state import Phase, demo_state
from websocket_server import (
    broadcast_phase_change,
    build_system_status,
    configure_voice_router_url,
    handle_client_message,
    manager,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from shared.config import load_twilio_credentials
    from websocket_server import sync_link_status_from_aws

    load_twilio_credentials()
    await sync_link_status_from_aws()

    await monitoring_simulator.start(manager.broadcast)
    await demo_controller.start()
    logger.info(f"Backend started on port {WS_PORT}")
    yield
    await demo_controller.stop()
    await monitoring_simulator.stop()
    logger.info("Backend shutting down")


app = FastAPI(lifespan=lifespan)

OPEN_PATHS = {"/health", "/twilio/outbound-call"}


class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not API_TOKEN:
            return await call_next(request)
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        token = request.query_params.get("token") or request.headers.get("x-api-token")
        if token != API_TOKEN:
            return JSONResponse(status_code=403, content={"error": "forbidden"})
        return await call_next(request)


app.add_middleware(TokenAuthMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


_voice_url_configured = False


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if API_TOKEN:
        token = websocket.query_params.get("token")
        if token != API_TOKEN:
            await websocket.close(code=4003, reason="forbidden")
            return

    global _voice_url_configured
    await manager.connect(websocket)

    if not _voice_url_configured:
        host = websocket.headers.get("host", "")
        if host:
            configure_voice_router_url(host, "wss")
            _voice_url_configured = True

    try:
        await websocket.send_text(
            __import__("json").dumps(build_system_status(demo_state))
        )
        while True:
            data = await websocket.receive_text()
            await handle_client_message(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# --- Twilio Integration Endpoints ---

@app.api_route("/twilio/outbound-call", methods=["GET", "POST"])
async def twilio_outbound_call(request: Request) -> Response:
    """TwiML webhook: Twilio fetches this when the outbound call connects.

    Returns TwiML that tells Twilio to connect a Media Stream WebSocket back to us.
    """
    host = request.headers.get("host", request.base_url.hostname or "localhost")
    media_stream_url = f"wss://{host}/twilio/media-stream"

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        '<Say language="en-US" voice="Polly.Matthew-Generative">'
        "Connecting to AI Operations."
        "</Say>"
        "<Connect>"
        f'<Stream url="{media_stream_url}" />'
        "</Connect>"
        "</Response>"
    )
    return Response(content=twiml, media_type="text/xml")


@app.websocket("/twilio/media-stream")
async def twilio_media_stream(websocket: WebSocket) -> None:
    """WebSocket endpoint that Twilio's Media Stream connects to.

    Bridges Twilio audio (mulaw 8kHz) ↔ Nova Sonic (PCM 24kHz).
    """
    await websocket.accept()
    logger.info("Twilio Media Stream WebSocket connected")

    from voice.twilio_handler import TwilioMediaStreamHandler
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

    handler = TwilioMediaStreamHandler(
        websocket=websocket,
        on_transcript=on_transcript,
        on_session_end=on_session_end,
    )

    if voice_router.twilio_session:
        voice_router.twilio_session.set_handler(handler)

    await handler.handle()


# Serve frontend static files if available (same-origin for WebSocket)
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    from fastapi.responses import FileResponse

    @app.get("/{path:path}")
    async def serve_frontend(path: str) -> FileResponse:
        file_path = STATIC_DIR / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WS_PORT)
