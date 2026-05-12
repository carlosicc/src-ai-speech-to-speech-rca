import logging
import os
import random
from datetime import datetime, timezone
from typing import Optional

from strands import Agent, tool
from strands.models import BedrockModel

from shared.config import BEDROCK_MODEL_ID, BEDROCK_REGION
from shared.prompts import get_prompt, get_soul

logger = logging.getLogger(__name__)

FALLBACK_PROMPT = """You are a diagnosis agent for a cloud operations center.
When an incident is detected, you must:
1. Pull recent logs from the affected service
2. Check the health of dependent services
3. Check recent infrastructure changes
4. Produce a concise Root Cause Analysis (RCA) summary

Be direct and technical. Output a structured RCA with: affected service, root cause, impact, and recommended action."""

FALLBACK_SOUL = """You are methodical, precise, and calm under pressure.
You communicate findings clearly with supporting evidence.
You prioritize speed without sacrificing accuracy."""


@tool
def pull_logs(service: str, minutes: int = 5) -> str:
    """Pull recent logs from the specified service.

    Args:
        service: The service to pull logs from (e.g., 'aurora-db')
        minutes: Number of minutes of logs to retrieve
    """
    logger.info(f"Tool: pull_logs(service={service}, minutes={minutes})")
    now = datetime.now(timezone.utc)
    if service == "aurora-db":
        return (
            f"[{now.isoformat()}] ERROR: Connection pool exhausted - max_connections=150 reached\n"
            f"[{now.isoformat()}] ERROR: Query timeout after 30000ms on table 'transactions'\n"
            f"[{now.isoformat()}] WARN: Disk IOPS at 0 - storage subsystem unresponsive\n"
            f"[{now.isoformat()}] ERROR: Replication lag exceeded 60s on read replica\n"
            f"[{now.isoformat()}] CRITICAL: Health check failed - instance not responding"
        )
    return f"[{now.isoformat()}] INFO: Service {service} operating normally. No errors in last {minutes} minutes."


@tool
def check_health(service: str) -> str:
    """Check the current health status of a service and its dependencies.

    Args:
        service: The service to check health for
    """
    logger.info(f"Tool: check_health(service={service})")
    if service == "aurora-db":
        return (
            "Service: aurora-db\n"
            "Status: UNHEALTHY\n"
            "CPU: 98% | Memory: 93% | IOPS: 0\n"
            "Connections: 150/150 (saturated)\n"
            "Read Replicas: 2/2 degraded (replication lag >60s)\n"
            "Last successful write: 45 seconds ago\n"
            "Dependencies affected: ecs-cluster (retry storms), api-gateway (elevated 5xx)"
        )
    if service == "ecs-cluster":
        return (
            "Service: ecs-cluster\n"
            "Status: DEGRADED\n"
            "CPU: 85% | Memory: 72%\n"
            "Running tasks: 12/12 | Pending: 5\n"
            "Reason: upstream database connection failures causing retry storms"
        )
    return f"Service: {service}\nStatus: HEALTHY\nAll metrics within normal range."


@tool
def check_recent_changes(service: str, hours: int = 24) -> str:
    """Check recent infrastructure or deployment changes for a service.

    Args:
        service: The service to check changes for
        hours: Number of hours to look back
    """
    logger.info(f"Tool: check_recent_changes(service={service}, hours={hours})")
    if service == "aurora-db":
        return (
            "Recent changes (last 24h):\n"
            "- 2h ago: Auto-scaling policy triggered (added read replica)\n"
            "- 4h ago: Parameter group change: max_connections 100 → 150\n"
            "- 6h ago: Batch job 'nightly-etl' started (unusually large dataset)\n"
            "Root cause indicator: The nightly ETL job is processing 3x normal volume, "
            "exhausting connection pool and causing disk IOPS saturation."
        )
    return f"No significant changes to {service} in the last {hours} hours."


def _build_system_prompt() -> str:
    prompt = get_prompt("diagnosis") or FALLBACK_PROMPT
    soul = get_soul("diagnosis_agent") or FALLBACK_SOUL
    return f"{soul}\n\n{prompt}"


async def run_diagnosis(service: str, incident_id: str) -> str:
    """Run the diagnosis agent and return an RCA summary."""
    logger.info(f"Starting diagnosis for service={service}, incident={incident_id}")

    system_prompt = _build_system_prompt()

    try:
        model = BedrockModel(
            model_id=BEDROCK_MODEL_ID,
            region_name=BEDROCK_REGION,
        )
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=[pull_logs, check_health, check_recent_changes],
        )
        user_prompt = (
            f"Incident {incident_id} detected on service '{service}' with CRITICAL severity. "
            f"Investigate the root cause. Use all available tools to gather evidence, then produce "
            f"a concise RCA summary with: affected service, root cause, impact assessment, and recommended action."
        )
        response = agent(user_prompt)
        rca_summary = str(response)
        logger.info(f"Diagnosis complete for incident={incident_id}")
        return rca_summary
    except Exception as e:
        logger.error(f"Diagnosis agent failed: {e}")
        return _fallback_rca(service, incident_id)


def _fallback_rca(service: str, incident_id: str) -> str:
    """Static RCA used when the LLM agent is unavailable."""
    return (
        f"**RCA Summary — Incident {incident_id[:8]}**\n\n"
        f"**Affected Service:** {service}\n"
        f"**Root Cause:** Nightly ETL batch job processing 3x normal data volume, "
        f"exhausting connection pool (150/150) and saturating disk IOPS.\n"
        f"**Impact:** Database unresponsive, ECS services in retry storm, "
        f"elevated 5xx on API Gateway.\n"
        f"**Recommended Action:** Restart the database instance and throttle "
        f"the ETL job to prevent recurrence."
    )
