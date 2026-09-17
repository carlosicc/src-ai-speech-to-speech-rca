"""The voice passphrase must never reach the logs.

Backend logs go to CloudWatch, which is read by more people than know the demo
passphrase. Every log line on the authentication path is checked here.
"""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from shared.config import VOICE_PASSPHRASE
from voice.voice_tools import execute_tool, redact_passphrase, _authenticate_user


class TestRedactPassphrase:
    """Nova Sonic event payloads carry the live transcript, passphrase included."""

    def test_removes_the_passphrase_from_a_transcript_payload(self) -> None:
        payload = f'{{"textOutput": {{"content": "my passphrase is {VOICE_PASSPHRASE}"}}}}'

        scrubbed = redact_passphrase(payload)

        assert VOICE_PASSPHRASE not in scrubbed
        assert "***" in scrubbed
        assert "textOutput" in scrubbed

    def test_is_case_insensitive(self) -> None:
        assert VOICE_PASSPHRASE.upper() not in redact_passphrase(f"heard: {VOICE_PASSPHRASE.upper()}")

    def test_leaves_unrelated_text_untouched(self) -> None:
        assert redact_passphrase("no secret here") == "no secret here"


class TestPassphraseNeverLogged:
    def test_tool_invocation_masks_the_spoken_passphrase(self, caplog) -> None:
        caplog.set_level(logging.INFO)

        import asyncio
        asyncio.run(execute_tool("authenticate_user", {"passphrase": VOICE_PASSPHRASE}))

        assert VOICE_PASSPHRASE not in caplog.text
        assert "***" in caplog.text

    def test_failed_auth_logs_neither_spoken_nor_expected_passphrase(self, caplog) -> None:
        caplog.set_level(logging.INFO)

        result = _authenticate_user("completely different words")

        assert result["status"] == "failed"
        assert VOICE_PASSPHRASE not in caplog.text
        assert "completely different words" not in caplog.text

    def test_word_level_match_does_not_log_the_spoken_text(self, caplog) -> None:
        caplog.set_level(logging.INFO)
        spoken = f"i think it is {' and '.join(VOICE_PASSPHRASE.split())} maybe"

        result = _authenticate_user(spoken)

        assert result["status"] == "authenticated"
        assert spoken not in caplog.text
        assert VOICE_PASSPHRASE not in caplog.text

    def test_non_sensitive_tool_arguments_are_still_logged(self, caplog) -> None:
        """Redaction must not blind us to ordinary tool debugging."""
        caplog.set_level(logging.INFO)

        import asyncio
        asyncio.run(execute_tool("check_service_health", {"service": "aurora-db"}))

        assert "aurora-db" in caplog.text


class TestAgentCorePassphraseNeverLogged:
    @pytest.mark.parametrize("spoken", ["completely different words", "test passphrase"])
    def test_agentcore_auth_never_logs_the_passphrase(self, spoken: str, caplog) -> None:
        caplog.set_level(logging.INFO)
        from voice.agentcore_agent import tools as agentcore_tools

        agentcore_tools.authenticate_user(spoken_passphrase=spoken)

        assert agentcore_tools.VOICE_PASSPHRASE not in caplog.text
        assert spoken not in caplog.text
