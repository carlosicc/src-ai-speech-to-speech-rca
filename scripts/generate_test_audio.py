"""Generate WAV audio fixtures for Nova Sonic closed-loop testing using Amazon Polly."""
import wave
from pathlib import Path

import boto3

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "audio"

PHRASES: dict[str, str] = {
    "correct_passphrase": "REDACTED_PASSPHRASE",
    "wrong_passphrase": "bravo midnight",
    "authorize_fix": "yes, please restore the firewall rule",
    "silence": "",
}


def generate_fixtures() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    polly = boto3.client("polly", region_name="eu-west-1")

    for name, text in PHRASES.items():
        wav_path = FIXTURES_DIR / f"{name}.wav"

        if name == "silence":
            # 3 seconds of silence at 16kHz 16-bit mono
            silence_bytes = b"\x00" * (16000 * 2 * 3)
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(silence_bytes)
            print(f"Generated silence: {wav_path} ({wav_path.stat().st_size} bytes)")
            continue

        response = polly.synthesize_speech(
            Text=text,
            OutputFormat="pcm",
            SampleRate="16000",
            VoiceId="Joanna",
        )
        pcm_bytes = response["AudioStream"].read()

        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_bytes)

        print(f"Generated: {wav_path} ({wav_path.stat().st_size} bytes)")


if __name__ == "__main__":
    generate_fixtures()
