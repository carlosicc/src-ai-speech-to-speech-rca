"""Closed-loop Nova Sonic test client — streams WAV audio and collects tool invocations."""
import asyncio
import base64
import json
import logging
import os
import wave
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)

NOVA_SONIC_MODEL_ID = "amazon.nova-2-sonic-v1:0"
NOVA_SONIC_REGION = os.environ.get("NOVA_SONIC_REGION", "eu-north-1")


@dataclass
class TestSessionResult:
    tool_invocations: list[dict[str, Any]] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)
    audio_output_count: int = 0
    error: str | None = None


def _ensure_env_credentials() -> None:
    """Export AWS credentials to env vars if not already set (Smithy SDK needs them there)."""
    if os.environ.get("AWS_ACCESS_KEY_ID"):
        return
    import boto3
    session = boto3.Session()
    creds = session.get_credentials()
    if creds:
        frozen = creds.get_frozen_credentials()
        os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
        if frozen.token:
            os.environ["AWS_SESSION_TOKEN"] = frozen.token


def _create_bedrock_client() -> Any:
    from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
    from aws_sdk_bedrock_runtime.config import Config
    from smithy_aws_core.auth.sigv4 import SigV4AuthScheme
    from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver

    _ensure_env_credentials()

    config = Config(
        endpoint_uri=f"https://bedrock-runtime.{NOVA_SONIC_REGION}.amazonaws.com",
        region=NOVA_SONIC_REGION,
        aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="bedrock")},
    )
    return BedrockRuntimeClient(config=config)


def _read_wav_chunks(audio_path: str, chunk_size: int = 3200) -> list[bytes]:
    """Read WAV file and return PCM chunks (chunk_size bytes each)."""
    with wave.open(audio_path, "rb") as wf:
        assert wf.getnchannels() == 1, "Expected mono audio"
        assert wf.getsampwidth() == 2, "Expected 16-bit audio"
        pcm_data = wf.readframes(wf.getnframes())

    chunks = []
    for i in range(0, len(pcm_data), chunk_size):
        chunks.append(pcm_data[i:i + chunk_size])
    return chunks


async def run_nova_sonic_test(
    audio_path: str,
    system_prompt: str,
    tools: list[dict[str, Any]],
    tool_handler: Callable[[str, dict[str, Any]], Any],
    region: str | None = None,
    chunk_size: int = 3200,
    timeout: float = 60.0,
) -> TestSessionResult:
    """Run a complete Nova Sonic session with pre-recorded audio and return results.

    The model starts speaking immediately (greeting). Audio is sent after a brief delay
    to allow session setup, then the model processes it as barge-in and invokes tools.
    """
    global NOVA_SONIC_REGION
    if region:
        NOVA_SONIC_REGION = region

    result = TestSessionResult()
    prompt_name = str(uuid4())
    audio_content_name = str(uuid4())
    speculative_content_ids: set[str] = set()
    audio_sent = asyncio.Event()
    session_done = asyncio.Event()

    from aws_sdk_bedrock_runtime.client import InvokeModelWithBidirectionalStreamOperationInput
    from aws_sdk_bedrock_runtime.models import (
        InvokeModelWithBidirectionalStreamInputChunk,
        BidirectionalInputPayloadPart,
    )

    client = _create_bedrock_client()

    stream_response = await client.invoke_model_with_bidirectional_stream(
        InvokeModelWithBidirectionalStreamOperationInput(model_id=NOVA_SONIC_MODEL_ID)
    )

    async def send_event(event: dict[str, Any]) -> None:
        event_json = json.dumps(event)
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )
        await stream_response.input_stream.send(chunk)

    async def send_tool_result(tool_use_id: str, tool_result: dict[str, Any]) -> None:
        content_name = str(uuid4())
        status = "error" if tool_result.get("status") == "error" else "success"
        await send_event({
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "interactive": True,
                    "type": "TOOL",
                    "role": "TOOL",
                    "toolResultInputConfiguration": {
                        "toolUseId": tool_use_id,
                        "type": "TEXT",
                        "textInputConfiguration": {"mediaType": "text/plain"},
                    },
                }
            }
        })
        await send_event({
            "event": {
                "toolResult": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                    "content": json.dumps(tool_result),
                    "status": status,
                }
            }
        })
        await send_event({
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": content_name,
                }
            }
        })

    async def process_responses() -> None:
        try:
            while True:
                output = await stream_response.await_output()
                resp = await output[1].receive()
                if not (resp.value and resp.value.bytes_):
                    continue

                payload = json.loads(resp.value.bytes_.decode("utf-8"))
                event = payload.get("event", {})

                if "contentStart" in event:
                    content_start = event["contentStart"]
                    content_id = content_start.get("contentId", "")
                    additional = content_start.get("additionalModelFields", "")
                    if additional:
                        try:
                            fields = json.loads(additional) if isinstance(additional, str) else additional
                            if fields.get("generationStage") == "SPECULATIVE":
                                speculative_content_ids.add(content_id)
                        except (json.JSONDecodeError, AttributeError):
                            pass

                elif "audioOutput" in event:
                    content_id = event["audioOutput"].get("contentId", "")
                    if content_id not in speculative_content_ids:
                        result.audio_output_count += 1

                elif "textOutput" in event:
                    content_id = event["textOutput"].get("contentId", "")
                    if content_id not in speculative_content_ids:
                        text = event["textOutput"].get("content", "")
                        role = event["textOutput"].get("role", "ASSISTANT")
                        if text and role == "ASSISTANT":
                            result.transcript.append(text)
                            logger.info(f"[transcript] {text[:100]}")

                elif "toolUse" in event:
                    tool_data = event["toolUse"]
                    tool_name = tool_data.get("toolName", "")
                    tool_use_id = tool_data.get("toolUseId", "")
                    tool_input_str = tool_data.get("content", "{}")
                    try:
                        tool_input = json.loads(tool_input_str)
                    except json.JSONDecodeError:
                        tool_input = {}

                    logger.info(f"[tool_call] {tool_name}({tool_input})")
                    tool_result = await tool_handler(tool_name, tool_input)
                    result.tool_invocations.append({
                        "name": tool_name,
                        "input": tool_input,
                        "result": tool_result,
                    })
                    await send_tool_result(tool_use_id, tool_result)

                elif "contentEnd" in event:
                    content_id = event["contentEnd"].get("contentId", "")
                    speculative_content_ids.discard(content_id)
                    stop_reason = event["contentEnd"].get("stopReason", "")
                    if stop_reason == "END_TURN" and audio_sent.is_set():
                        logger.info("[end_turn] Nova Sonic turn complete (post-audio)")
                        session_done.set()

        except Exception as e:
            if "closed" not in str(e).lower() and "cancel" not in str(e).lower():
                result.error = str(e)
                logger.error(f"Response processing error: {e}")
            session_done.set()

    # Start response processing
    response_task = asyncio.create_task(process_responses())

    try:
        # 1. sessionStart with HIGH sensitivity for fast turn detection on short utterances
        await send_event({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7,
                    },
                    "turnDetectionConfiguration": {
                        "endpointingSensitivity": "HIGH",
                    },
                }
            }
        })

        # 2. promptStart
        await send_event({
            "event": {
                "promptStart": {
                    "promptName": prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": {
                        "audioType": "SPEECH",
                        "encoding": "base64",
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 16000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": "tiffany",
                    },
                    "toolUseOutputConfiguration": {
                        "mediaType": "application/json",
                    },
                    "toolConfiguration": {"tools": tools},
                }
            }
        })

        # 3. System prompt
        sys_content_name = str(uuid4())
        await send_event({
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": sys_content_name,
                    "type": "TEXT",
                    "interactive": True,
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        })
        await send_event({
            "event": {
                "textInput": {
                    "promptName": prompt_name,
                    "contentName": sys_content_name,
                    "content": system_prompt,
                    "role": "SYSTEM",
                }
            }
        })
        await send_event({
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": sys_content_name,
                }
            }
        })

        # 4. audioContentStart
        await send_event({
            "event": {
                "contentStart": {
                    "promptName": prompt_name,
                    "contentName": audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "audioInputConfiguration": {
                        "audioType": "SPEECH",
                        "encoding": "base64",
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 16000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                    },
                }
            }
        })

        # 5. Wait for stream to stabilize before sending audio
        logger.info("Waiting for session to stabilize...")
        await asyncio.sleep(5.0)

        # 6. Stream audio chunks with real-time pacing + trailing silence
        chunks = _read_wav_chunks(audio_path, chunk_size)
        sample_rate = 16000
        chunk_duration = chunk_size / (sample_rate * 2)  # 2 bytes per sample

        logger.info(f"Streaming {len(chunks)} audio chunks ({chunk_duration*1000:.0f}ms each)")
        for chunk in chunks:
            pcm_b64 = base64.b64encode(chunk).decode("utf-8")
            await send_event({
                "event": {
                    "audioInput": {
                        "promptName": prompt_name,
                        "contentName": audio_content_name,
                        "content": pcm_b64,
                        "role": "USER",
                    }
                }
            })
            await asyncio.sleep(chunk_duration)

        # Send 2s of trailing silence to trigger turn detection
        silence_chunks = int(2.0 / chunk_duration)
        silence_b64 = base64.b64encode(b"\x00" * chunk_size).decode("utf-8")
        for _ in range(silence_chunks):
            await send_event({
                "event": {
                    "audioInput": {
                        "promptName": prompt_name,
                        "contentName": audio_content_name,
                        "content": silence_b64,
                        "role": "USER",
                    }
                }
            })
            await asyncio.sleep(chunk_duration)

        audio_sent.set()

        # 7. Wait for model to process and invoke tools
        logger.info("Audio + silence sent. Waiting for tool invocations...")
        try:
            await asyncio.wait_for(session_done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Session timed out after {timeout}s")
            if not result.tool_invocations:
                result.error = f"Timeout after {timeout}s with no tool invocations"

        # 8. Clean shutdown
        await send_event({
            "event": {
                "contentEnd": {
                    "promptName": prompt_name,
                    "contentName": audio_content_name,
                }
            }
        })
        await send_event({"event": {"promptEnd": {"promptName": prompt_name}}})
        await send_event({"event": {"sessionEnd": {}}})

    except Exception as e:
        result.error = str(e)
        logger.error(f"Test session error: {e}", exc_info=True)
    finally:
        response_task.cancel()
        try:
            await response_task
        except asyncio.CancelledError:
            pass
        try:
            await stream_response.input_stream.close()
        except Exception:
            pass

    return result
