"""Guards the aws_sdk_bedrock_runtime pin that the Nova Sonic voice path depends on.

Regression test for a deployed-only failure: `requirements.txt` had an unpinned
`aws_sdk_bedrock_runtime>=0.6.0`, so a fresh image build installed 0.11.0, where
`BedrockRuntimeClient` is no longer exported from `aws_sdk_bedrock_runtime.client`.
The Twilio call connected but Nova Sonic died with an ImportError.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

REQUIREMENTS = Path(__file__).resolve().parents[2] / "src_backend" / "requirements.txt"


def test_bedrock_runtime_symbols_nova_sonic_imports_are_available() -> None:
    """The symbols nova_sonic_client imports at call time must exist."""
    from aws_sdk_bedrock_runtime.client import (  # noqa: F401
        BedrockRuntimeClient,
        InvokeModelWithBidirectionalStreamOperationInput,
    )
    from aws_sdk_bedrock_runtime.config import Config  # noqa: F401


def test_bedrock_runtime_is_pinned_exactly() -> None:
    """An unpinned floor lets a fresh container build pull an incompatible major."""
    lines = REQUIREMENTS.read_text().splitlines()
    pins = [line for line in lines if line.strip().startswith("aws_sdk_bedrock_runtime")]

    assert len(pins) == 1, f"expected one aws_sdk_bedrock_runtime line, got {pins}"
    assert re.fullmatch(r"aws_sdk_bedrock_runtime==\d+\.\d+\.\d+", pins[0].strip()), (
        f"aws_sdk_bedrock_runtime must be pinned with '==' so image builds are "
        f"reproducible, got: {pins[0]!r}"
    )
