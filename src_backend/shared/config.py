import json
import logging
import os

logger = logging.getLogger(__name__)


def get_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def get_env_int(name: str, default: int = 0) -> int:
    return int(os.environ.get(name, str(default)))


def get_env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("true", "1", "yes")


WS_PORT: int = get_env_int("WS_PORT", 8080)
INCIDENT_LOOP_INTERVAL: int = get_env_int("INCIDENT_LOOP_INTERVAL", 180)
DEFAULT_PHONE_NUMBER: str = get_env("DEFAULT_PHONE_NUMBER", "+44XXXXXXXXXX")
DEFAULT_VOICE_MODE: str = get_env("DEFAULT_VOICE_MODE", "mode_c")
BEDROCK_REGION: str = get_env("BEDROCK_REGION", "eu-west-1")
BEDROCK_MODEL_ID: str = get_env("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
NOVA_SONIC_MODEL_ID: str = get_env("NOVA_SONIC_MODEL_ID", "amazon.nova-sonic-v1:0")
NOVA_SONIC_REGION: str = get_env("NOVA_SONIC_REGION", "us-east-1")
VOICE_PASSPHRASE: str = get_env("VOICE_PASSPHRASE", "REDACTED_PASSPHRASE")
VOICE_SESSION_TIMEOUT: int = get_env_int("VOICE_SESSION_TIMEOUT", 90)
DDB_TABLE_NAME: str = get_env("DDB_TABLE_NAME", "")
TWILIO_SECRET_ARN: str = get_env("TWILIO_SECRET_ARN", "")


def load_twilio_credentials() -> tuple[str, str, str]:
    """Load Twilio credentials from Secrets Manager or env vars.

    Returns (account_sid, auth_token, from_number).
    Falls back to env vars if secret not configured.
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_FROM_NUMBER", "")

    if account_sid and auth_token:
        return account_sid, auth_token, from_number

    if not TWILIO_SECRET_ARN:
        logger.warning("Twilio credentials not configured (no env vars or secret ARN)")
        return "", "", ""

    try:
        import boto3
        client = boto3.client("secretsmanager", region_name=BEDROCK_REGION)
        response = client.get_secret_value(SecretId=TWILIO_SECRET_ARN)
        secret = json.loads(response["SecretString"])
        account_sid = secret.get("account_sid", "")
        auth_token = secret.get("auth_token", "")
        from_number = secret.get("from_number", "")

        os.environ["TWILIO_ACCOUNT_SID"] = account_sid
        os.environ["TWILIO_AUTH_TOKEN"] = auth_token
        os.environ["TWILIO_FROM_NUMBER"] = from_number

        logger.info("Twilio credentials loaded from Secrets Manager")
        return account_sid, auth_token, from_number
    except Exception as e:
        logger.error(f"Failed to load Twilio credentials from Secrets Manager: {e}")
        return "", "", ""
