"""BidiAgent for RCA Voice Agent — deployed on AgentCore Runtime.

AgentCore Runtime requires:
- HTTP server on port 8080
- WebSocket endpoint at /ws
- Health check endpoint at /ping
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn

from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.models import BidiNovaSonicModel

from tools import authenticate_user, restart_database, check_service_health

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an AI Operations Center voice agent handling a critical database incident. "
    "You have called the on-call DBA to assist with incident recovery.\n\n"
    "IMPORTANT: Start speaking IMMEDIATELY when the session begins. Do not wait for user input first. "
    "Your opening line should be: 'This is the AI Operations Center. We have a critical Aurora database incident. "
    "Connection pool exhausted. I need your voice passphrase to authenticate.'\n\n"
    "Your workflow:\n"
    "1. Greet the DBA immediately (do NOT wait). State the situation in one sentence.\n"
    "2. Ask for their voice passphrase to authenticate identity\n"
    "3. Use the authenticate_user tool to verify their passphrase\n"
    "4. If authenticated, provide a brief status using check_service_health\n"
    "5. Ask for authorization to restart the database\n"
    "6. When authorized, use restart_database to initiate recovery\n\n"
    "Be very concise and professional. This is an urgent incident. "
    "Speak clearly and wait for responses. Keep sentences as short as possible for voice clarity."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("RCA BidiAgent starting up")
    yield
    logger.info("RCA BidiAgent shutting down")


app = FastAPI(title="RCA Voice BidiAgent", lifespan=lifespan)


@app.get("/ping")
async def health_check():
    return JSONResponse(content={"status": "healthy"}, status_code=200)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    from strands.experimental.bidi.types.events import (
        BidiAudioInputEvent,
        BidiTextInputEvent,
    )

    logger.info("AgentCore WebSocket connection initiated")

    try:
        await websocket.accept()

        region = os.environ.get("NOVA_SONIC_REGION", "us-east-1")
        voice_id = os.environ.get("VOICE_ID", "tiffany")

        tools = [authenticate_user, restart_database, check_service_health]

        model = BidiNovaSonicModel(
            region=region,
            model_id="amazon.nova-sonic-v1:0",
            provider_config={
                "audio": {
                    "input_sample_rate": 16000,
                    "output_sample_rate": 16000,
                    "voice": voice_id,
                }
            },
            tools=tools,
        )

        agent = BidiAgent(
            model=model,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
        )

        async def receive_and_convert():
            data = await websocket.receive_json()
            if not isinstance(data, dict) or "type" not in data:
                return data

            event_type = data["type"]
            event_data = {k: v for k, v in data.items() if k != "type"}

            if event_type == "bidi_audio_input":
                return BidiAudioInputEvent(**event_data)
            elif event_type == "bidi_text_input":
                return BidiTextInputEvent(**event_data)
            elif event_type == "bidi_session_start":
                logger.info("Session start received — triggering agent greeting")
                return BidiTextInputEvent(
                    text="[SYSTEM: The on-call DBA has answered the phone. Begin immediately.]"
                )
            else:
                return data

        await agent.run(
            inputs=[receive_and_convert],
            outputs=[websocket.send_json],
        )

    except WebSocketDisconnect:
        logger.info("AgentCore WebSocket client disconnected")
    except Exception as e:
        logger.error(f"AgentCore WebSocket error: {type(e).__name__}: {e}")
        try:
            await websocket.close(code=1011, reason=str(e)[:120])
        except Exception:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
