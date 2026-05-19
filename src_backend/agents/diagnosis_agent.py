import asyncio
import logging
import os
import boto3
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Coroutine, Optional
from botocore.exceptions import ClientError
from strands import Agent, tool
from strands.models import BedrockModel
from shared.config import BEDROCK_MODEL_ID, BEDROCK_REGION
from shared.prompts import get_prompt, get_soul

# Options
logger = logging.getLogger(__name__)
_broadcast_fn: Optional[Callable[[dict[str, Any]], Coroutine]] = None


def set_diagnosis_broadcast(broadcast_fn: Callable[[dict[str, Any]], Coroutine]) -> None:
    global _broadcast_fn
    _broadcast_fn = broadcast_fn


def _broadcast_aws_error(tool_name: str, error: Exception) -> None:
    """Broadcast an AWS error to the UI agent_log panel."""
    if _broadcast_fn is None:
        return
    msg = {"type": "agent_log", "payload": {"message": f"[AWS ERROR] {tool_name}: {error}", "level": "error"}}
    try:
        loop = asyncio.get_running_loop()
        asyncio.run_coroutine_threadsafe(_broadcast_fn(msg), loop)
    except RuntimeError:
        pass

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

_RDS_CLUSTER_ID = os.environ.get("RDS_CLUSTER_ID", "rca-rds-aurora-cluster-dev01")
_AWS_REGION = os.environ.get("BEDROCK_REGION", "eu-west-1")
_RDS_SG_ID = os.environ.get("RDS_SECURITY_GROUP_ID", "sg-XXXXXXXXXXXXXXXXX")
_ECS_SG_ID = os.environ.get("ECS_SECURITY_GROUP_ID", "sg-YYYYYYYYYYYYYYYYY")

_logs_client: Optional[boto3.client] = None
_rds_client: Optional[boto3.client] = None
_cw_client: Optional[boto3.client] = None
_ec2_client: Optional[boto3.client] = None


def _get_logs_client() -> boto3.client:
    global _logs_client
    if _logs_client is None:
        _logs_client = boto3.client("logs", region_name=_AWS_REGION)
    return _logs_client


def _get_rds_client() -> boto3.client:
    global _rds_client
    if _rds_client is None:
        _rds_client = boto3.client("rds", region_name=_AWS_REGION)
    return _rds_client


def _get_cw_client() -> boto3.client:
    global _cw_client
    if _cw_client is None:
        _cw_client = boto3.client("cloudwatch", region_name=_AWS_REGION)
    return _cw_client


def _get_ec2_client() -> boto3.client:
    global _ec2_client
    if _ec2_client is None:
        _ec2_client = boto3.client("ec2", region_name=_AWS_REGION)
    return _ec2_client


def _simulated_pull_logs(service: str, minutes: int) -> str:
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


def _simulated_check_health(service: str) -> str:
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


def _simulated_check_recent_changes(service: str, hours: int) -> str:
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


def _real_pull_logs(service: str, minutes: int) -> str:
    """Query CloudWatch Logs Insights on the RDS error log group."""
    log_group = f"/aws/rds/cluster/{_RDS_CLUSTER_ID}/error"
    client = _get_logs_client()
    end_time = int(datetime.now(timezone.utc).timestamp())
    start_time = end_time - (minutes * 60)

    query = "fields @timestamp, @message | filter @message like /ERROR|WARNING|WARN/ | sort @timestamp desc | limit 20"

    resp = client.start_query(
        logGroupName=log_group,
        startTime=start_time,
        endTime=end_time,
        queryString=query,
    )
    query_id = resp["queryId"]

    import time
    for _ in range(10):
        time.sleep(1)
        result = client.get_query_results(queryId=query_id)
        if result["status"] in ("Complete", "Failed", "Cancelled"):
            break

    if result["status"] != "Complete" or not result["results"]:
        return f"No errors found in {service} logs (last {minutes} minutes)."

    lines = []
    for row in result["results"]:
        fields = {f["field"]: f["value"] for f in row}
        ts = fields.get("@timestamp", "")
        msg = fields.get("@message", "").strip()
        if msg:
            lines.append(f"[{ts}] {msg}")

    return "\n".join(lines) if lines else f"No errors found in {service} logs (last {minutes} minutes)."


def _real_check_health(service: str) -> str:
    """Call rds:DescribeDBClusters + CloudWatch for real status."""
    rds_client = _get_rds_client()
    cw_client = _get_cw_client()

    cluster_resp = rds_client.describe_db_clusters(DBClusterIdentifier=_RDS_CLUSTER_ID)
    cluster = cluster_resp["DBClusters"][0]
    status = cluster.get("Status", "unknown")

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=5)

    def get_metric(metric_name: str) -> Optional[float]:
        resp = cw_client.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName=metric_name,
            Dimensions=[{"Name": "DBClusterIdentifier", "Value": _RDS_CLUSTER_ID}],
            StartTime=start,
            EndTime=end,
            Period=60,
            Statistics=["Average"],
        )
        dps = resp.get("Datapoints", [])
        if not dps:
            return None
        return max(dps, key=lambda d: d["Timestamp"])["Average"]

    cpu = get_metric("CPUUtilization")
    connections = get_metric("DatabaseConnections")
    freeable_mem = get_metric("FreeableMemory")

    cpu_str = f"{int(cpu)}%" if cpu is not None else "N/A"
    conn_str = str(int(connections)) if connections is not None else "N/A"
    if freeable_mem is not None:
        total_bytes = 1 * 1024 * 1024 * 1024
        mem_pct = int(((total_bytes - freeable_mem) / total_bytes) * 100)
        mem_str = f"{mem_pct}%"
    else:
        mem_str = "N/A"

    return (
        f"Service: aurora-db\n"
        f"Status: {status.upper()}\n"
        f"CPU: {cpu_str} | Memory: {mem_str}\n"
        f"Connections: {conn_str}"
    )


def _real_check_recent_changes(service: str, hours: int) -> str:
    """Call rds:DescribeEvents for real RDS events."""
    rds_client = _get_rds_client()
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    resp = rds_client.describe_events(
        SourceIdentifier=_RDS_CLUSTER_ID,
        SourceType="db-cluster",
        StartTime=start_time,
        MaxRecords=20,
    )
    events = resp.get("Events", [])
    if not events:
        return f"No recent changes to {service} in the last {hours} hours."

    lines = [f"Recent RDS events (last {hours}h):"]
    for event in events:
        ts = event.get("Date", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        msg = event.get("Message", "")
        lines.append(f"- [{ts}] {msg}")

    return "\n".join(lines)


@tool
def check_network(service: str) -> str:
    """Check network connectivity and security group configuration for a service.

    Args:
        service: The service to check network config for (e.g., 'aurora-db')
    """
    logger.info(f"Tool: check_network(service={service})")
    if service == "aurora-db":
        try:
            client = _get_ec2_client()
            response = client.describe_security_groups(GroupIds=[_RDS_SG_ID])
            sg = response["SecurityGroups"][0]
            for perm in sg.get("IpPermissions", []):
                if perm.get("FromPort") == 3306 and perm.get("ToPort") == 3306:
                    for pair in perm.get("UserIdGroupPairs", []):
                        if pair.get("GroupId") == _ECS_SG_ID:
                            return (
                                f"Network: OK — port 3306 inbound rule present on {_RDS_SG_ID}\n"
                                f"Source: {_ECS_SG_ID} (ECS tasks)\n"
                                f"Status: Connectivity NORMAL"
                            )
            return (
                f"ALERT: Port 3306 inbound rule MISSING from security group {_RDS_SG_ID}\n"
                f"Expected source: {_ECS_SG_ID} (ECS tasks)\n"
                f"Impact: All database connections from ECS tasks are BLOCKED\n"
                f"Root cause: Security group misconfiguration — firewall rule removed"
            )
        except Exception as e:
            logger.warning(f"Real check_network failed, using fallback: {e}")
            _broadcast_aws_error("check_network", e)
            return (
                f"ALERT: Unable to verify security group rules ({e}). "
                f"Network connectivity to {service} may be impaired."
            )
    return f"Network: OK — no security group issues detected for {service}"


@tool
def pull_logs(service: str, minutes: int = 5) -> str:
    """Pull recent logs from the specified service.

    Args:
        service: The service to pull logs from (e.g., 'aurora-db')
        minutes: Number of minutes of logs to retrieve
    """
    logger.info(f"Tool: pull_logs(service={service}, minutes={minutes})")
    if service == "aurora-db":
        try:
            return _real_pull_logs(service, minutes)
        except Exception as e:
            logger.warning(f"Real pull_logs failed, using fallback: {e}")
            _broadcast_aws_error("pull_logs", e)
            return _simulated_pull_logs(service, minutes)
    return _simulated_pull_logs(service, minutes)


@tool
def check_health(service: str) -> str:
    """Check the current health status of a service and its dependencies.

    Args:
        service: The service to check health for
    """
    logger.info(f"Tool: check_health(service={service})")
    if service == "aurora-db":
        try:
            return _real_check_health(service)
        except Exception as e:
            logger.warning(f"Real check_health failed, using fallback: {e}")
            _broadcast_aws_error("check_health", e)
            return _simulated_check_health(service)
    return _simulated_check_health(service)


@tool
def check_recent_changes(service: str, hours: int = 24) -> str:
    """Check recent infrastructure or deployment changes for a service.

    Args:
        service: The service to check changes for
        hours: Number of hours to look back
    """
    logger.info(f"Tool: check_recent_changes(service={service}, hours={hours})")
    if service == "aurora-db":
        try:
            return _real_check_recent_changes(service, hours)
        except Exception as e:
            logger.warning(f"Real check_recent_changes failed, using fallback: {e}")
            _broadcast_aws_error("check_recent_changes", e)
            return _simulated_check_recent_changes(service, hours)
    return _simulated_check_recent_changes(service, hours)


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
            tools=[check_network, pull_logs, check_health, check_recent_changes],
        )
        user_prompt = (
            f"Incident {incident_id} detected on service '{service}' with CRITICAL severity. "
            f"First check network connectivity (security group rules), then check service health, "
            f"pull logs, and check recent changes. Produce a concise RCA summary with: "
            f"affected service, root cause, impact assessment, and recommended action."
        )
        response = await asyncio.to_thread(agent, user_prompt)
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
