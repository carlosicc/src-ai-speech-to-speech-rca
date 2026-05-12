import asyncio
import base64
import json
import logging
import os
from typing import Any, Callable, Coroutine
from uuid import uuid4

from shared.config import NOVA_SONIC_MODEL_ID, NOVA_SONIC_REGION
from voice.voice_tools import TOOL_SPECS, execute_tool

logger = logging.getLogger(__name__)

VOICE_AGENT_SYSTEM_PROMPT = (
    "You are an AI Operations Center voice agent handling a critical database incident. "
    "You have called the on-call DBA to assist with incident recovery.\n\n"
    "Your workflow:\n"
    "1. Greet the DBA quickly. Explain the situation very briefly (Aurora DB is down, connection pool exhausted)\n"
    "2. Ask for their voice passphrase to authenticate identity\n"
    "3. Use the authenticate_user tool to verify their passphrase\n"
    "4. If authenticated, provide a brief status using check_service_health\n"
    "5. Ask for authorization to restart the database\n"
    "6. When authorized, use restart_database to initiate recovery\n\n"
    "Be very concise and professional. This is an urgent incident. "
    "Speak clearly and wait for responses. Keep sentences as short as possible for voice clarity."
)


def _create_bedrock_client() -> Any:
    from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
    from aws_sdk_bedrock_runtime.config import Config
    from smithy_aws_core.auth.sigv4 import SigV4AuthScheme
    from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver
    from smithy_aws_core.identity.container import ContainerCredentialsResolver
    from smithy_http.aio.aiohttp import AIOHTTPClient, AIOHTTPClientConfig

    uri = os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "")
    if uri:
        logger.info("Using ContainerCredentialsResolver for Bedrock client")
        client_config = AIOHTTPClientConfig()
        http_client = AIOHTTPClient(client_config=client_config)
        resolver = ContainerCredentialsResolver(http_client)
    else:
        logger.info("Using EnvironmentCredentialsResolver for Bedrock client")
        resolver = EnvironmentCredentialsResolver()

    config = Config(
        endpoint_uri=f"https://bedrock-runtime.{NOVA_SONIC_REGION}.amazonaws.com",
        region=NOVA_SONIC_REGION,
        aws_credentials_identity_resolver=resolver,
        auth_schemes={"aws.auth#sigv4": SigV4AuthScheme(service="bedrock")},
    )
    return BedrockRuntimeClient(config=config)


class NovaSonicSession:
    def __init__(
        self,
        on_audio_output: Callable[[bytes], Coroutine[Any, Any, None]],
        on_transcript: Callable[[str, str], Coroutine[Any, Any, None]],
        on_session_end: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        self._on_audio_output = on_audio_output
        self._on_transcript = on_transcript
        self._on_session_end = on_session_end

        self._prompt_name: str = str(uuid4())
        self._audio_content_name: str = str(uuid4())
        self._stream_response: Any = None
        self._response_task: asyncio.Task | None = None
        self._active = False
        self._client: Any = None
        self._speculative_content_ids: set[str] = set()

    @property
    def active(self) -> bool:
        return self._active

    async def start(self) -> None:
        from aws_sdk_bedrock_runtime.client import InvokeModelWithBidirectionalStreamOperationInput

        logger.info(f"Starting Nova Sonic session, model={NOVA_SONIC_MODEL_ID}, region={NOVA_SONIC_REGION}")
        self._active = True
        self._client = _create_bedrock_client()

        self._stream_response = await self._client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=NOVA_SONIC_MODEL_ID)
        )

        self._response_task = asyncio.create_task(self._process_responses())
        await asyncio.sleep(0.1)

        await self._send_session_start()
        await self._send_prompt_start()
        await self._send_system_prompt()
        await self._send_audio_content_start()
        logger.info("Nova Sonic session initialized, ready for audio input")

    async def send_audio(self, pcm_base64: str) -> None:
        if not self._active:
            return
        event = {
            "event": {
                "audioInput": {
                    "promptName": self._prompt_name,
                    "contentName": self._audio_content_name,
                    "content": pcm_base64,
                    "role": "USER",
                }
            }
        }
        await self._send_event(event)

    async def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        logger.info("Stopping Nova Sonic session")

        try:
            await self._send_audio_content_end()
            await self._send_prompt_end()
            await self._send_session_end()
        except Exception as e:
            logger.warning(f"Error sending close events: {e}")

        if self._stream_response:
            try:
                await self._stream_response.input_stream.close()
            except Exception:
                pass

        if self._response_task:
            self._response_task.cancel()
            try:
                await self._response_task
            except asyncio.CancelledError:
                pass
            self._response_task = None

        if self._client and hasattr(self._client, "_config"):
            try:
                http_client = getattr(self._client._config, "_http_client", None)
                if http_client and hasattr(http_client, "close"):
                    await http_client.close()
            except Exception:
                pass

        self._stream_response = None
        self._client = None

    async def _send_event(self, event: dict[str, Any]) -> None:
        if not self._stream_response:
            return
        from aws_sdk_bedrock_runtime.models import (
            InvokeModelWithBidirectionalStreamInputChunk,
            BidirectionalInputPayloadPart,
        )

        event_json = json.dumps(event)
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )
        await self._stream_response.input_stream.send(chunk)

    async def _send_session_start(self) -> None:
        await self._send_event({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7,
                    }
                }
            }
        })

    async def _send_prompt_start(self) -> None:
        await self._send_event({
            "event": {
                "promptStart": {
                    "promptName": self._prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": {
                        "audioType": "SPEECH",
                        "encoding": "base64",
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 24000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": "tiffany",
                    },
                    "toolConfiguration": {"tools": TOOL_SPECS},
                }
            }
        })

    async def _send_system_prompt(self) -> None:
        content_name = str(uuid4())
        await self._send_event({
            "event": {
                "contentStart": {
                    "promptName": self._prompt_name,
                    "contentName": content_name,
                    "type": "TEXT",
                    "interactive": False,
                    "role": "SYSTEM",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        })
        await self._send_event({
            "event": {
                "textInput": {
                    "promptName": self._prompt_name,
                    "contentName": content_name,
                    "content": VOICE_AGENT_SYSTEM_PROMPT,
                }
            }
        })
        await self._send_event({
            "event": {
                "contentEnd": {
                    "promptName": self._prompt_name,
                    "contentName": content_name,
                }
            }
        })

    async def _send_audio_content_start(self) -> None:
        await self._send_event({
            "event": {
                "contentStart": {
                    "promptName": self._prompt_name,
                    "contentName": self._audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "audioType": "SPEECH",
                        "encoding": "base64",
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 24000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                    },
                }
            }
        })

    async def _send_audio_content_end(self) -> None:
        await self._send_event({
            "event": {
                "contentEnd": {
                    "promptName": self._prompt_name,
                    "contentName": self._audio_content_name,
                }
            }
        })

    async def _send_prompt_end(self) -> None:
        await self._send_event({
            "event": {
                "promptEnd": {
                    "promptName": self._prompt_name,
                }
            }
        })

    async def _send_session_end(self) -> None:
        await self._send_event({"event": {"sessionEnd": {}}})

    async def _send_tool_result(self, tool_use_id: str, result: dict[str, Any]) -> None:
        content_name = str(uuid4())
        await self._send_event({
            "event": {
                "contentStart": {
                    "promptName": self._prompt_name,
                    "contentName": content_name,
                    "interactive": False,
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
        await self._send_event({
            "event": {
                "toolResult": {
                    "promptName": self._prompt_name,
                    "contentName": content_name,
                    "content": json.dumps(result),
                }
            }
        })
        await self._send_event({
            "event": {
                "contentEnd": {
                    "promptName": self._prompt_name,
                    "contentName": content_name,
                }
            }
        })

    async def _process_responses(self) -> None:
        try:
            while self._active and self._stream_response:
                output = await self._stream_response.await_output()
                result = await output[1].receive()
                if result.value and result.value.bytes_:
                    response_data = result.value.bytes_.decode("utf-8")
                    payload = json.loads(response_data)
                    await self._handle_response_event(payload)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self._active:
                logger.error(f"Error processing Nova Sonic responses: {e}")
        finally:
            if self._active:
                self._active = False
                await self._on_session_end()

    async def _handle_response_event(self, payload: dict[str, Any]) -> None:
        event = payload.get("event", {})

        if "contentStart" in event:
            content_start = event["contentStart"]
            content_id = content_start.get("contentId", "")
            additional = content_start.get("additionalModelFields", "")
            if additional:
                try:
                    fields = json.loads(additional) if isinstance(additional, str) else additional
                    if fields.get("generationStage") == "SPECULATIVE":
                        self._speculative_content_ids.add(content_id)
                except (json.JSONDecodeError, AttributeError):
                    pass

        elif "audioOutput" in event:
            content_id = event["audioOutput"].get("contentId", "")
            if content_id not in self._speculative_content_ids:
                audio_data = event["audioOutput"].get("content", "")
                if audio_data:
                    pcm_bytes = base64.b64decode(audio_data)
                    await self._on_audio_output(pcm_bytes)

        elif "textOutput" in event:
            content_id = event["textOutput"].get("contentId", "")
            if content_id not in self._speculative_content_ids:
                text = event["textOutput"].get("content", "")
                role = event["textOutput"].get("role", "ASSISTANT")
                if text and role == "ASSISTANT":
                    await self._on_transcript(text, "agent")

        elif "toolUse" in event:
            tool_data = event["toolUse"]
            tool_name = tool_data.get("toolName", "")
            tool_use_id = tool_data.get("toolUseId", "")
            tool_input_str = tool_data.get("content", "{}")
            try:
                tool_input = json.loads(tool_input_str)
            except json.JSONDecodeError:
                tool_input = {}

            logger.info(f"Nova Sonic requested tool: {tool_name}")
            await self._on_transcript(f"[Executing: {tool_name}]", "agent")

            result = await execute_tool(tool_name, tool_input)
            await self._send_tool_result(tool_use_id, result)

        elif "contentEnd" in event:
            content_id = event["contentEnd"].get("contentId", "")
            self._speculative_content_ids.discard(content_id)
            stop_reason = event["contentEnd"].get("stopReason", "")
            if stop_reason == "END_TURN":
                logger.info("Nova Sonic turn ended")
