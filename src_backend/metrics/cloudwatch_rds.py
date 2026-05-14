"""Fetches real CloudWatch metrics for the Aurora MySQL cluster."""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3

logger = logging.getLogger(__name__)

_CLUSTER_ID = "rca-rds-aurora-cluster-dev01"
_NAMESPACE = "AWS/RDS"
_POLL_INTERVAL = 10.0
_PERIOD = 60  # CloudWatch minimum period for RDS

_client: Optional[boto3.client] = None


def _get_client() -> boto3.client:
    global _client
    if _client is None:
        region = os.environ.get("BEDROCK_REGION", "eu-west-1")
        _client = boto3.client("cloudwatch", region_name=region)
    return _client


def _fetch_metric(metric_name: str, stat: str = "Average") -> Optional[float]:
    """Fetch a single metric's most recent datapoint from CloudWatch."""
    client = _get_client()
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=5)
    try:
        resp = client.get_metric_statistics(
            Namespace=_NAMESPACE,
            MetricName=metric_name,
            Dimensions=[{"Name": "DBClusterIdentifier", "Value": _CLUSTER_ID}],
            StartTime=start,
            EndTime=end,
            Period=_PERIOD,
            Statistics=[stat],
        )
        datapoints = resp.get("Datapoints", [])
        if not datapoints:
            return None
        latest = max(datapoints, key=lambda d: d["Timestamp"])
        return latest.get(stat)
    except Exception as e:
        logger.error(f"CloudWatch fetch error for {metric_name}: {e}")
        return None


class CloudWatchRdsMetrics:
    """Background poller that caches CloudWatch metrics for aurora-db."""

    def __init__(self) -> None:
        self._cpu: Optional[float] = None
        self._mem: Optional[float] = None
        self._read_iops: Optional[float] = None
        self._write_iops: Optional[float] = None
        self._connections: Optional[float] = None
        self._task: Optional[asyncio.Task] = None
        self._ready = False

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("CloudWatch RDS metrics poller started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _poll_loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self._fetch_all)
                self._ready = True
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"CloudWatch RDS poll error: {e}")
            await asyncio.sleep(_POLL_INTERVAL)

    def _fetch_all(self) -> None:
        self._cpu = _fetch_metric("CPUUtilization")
        freeable_mem = _fetch_metric("FreeableMemory")
        if freeable_mem is not None:
            # Serverless v2 0.5 ACU ≈ 1 GB RAM; convert bytes to percentage used
            total_bytes = 1 * 1024 * 1024 * 1024
            used_pct = ((total_bytes - freeable_mem) / total_bytes) * 100
            self._mem = max(0.0, min(100.0, used_pct))
        else:
            self._mem = None
        self._read_iops = _fetch_metric("ReadIOPS")
        self._write_iops = _fetch_metric("WriteIOPS")
        self._connections = _fetch_metric("DatabaseConnections")

    def get_current_metrics(self) -> Optional[dict]:
        """Return metrics in the frontend-expected shape, or None if not ready."""
        if not self._ready:
            return None
        cpu = int(self._cpu) if self._cpu is not None else 0
        mem = int(self._mem) if self._mem is not None else 0
        read_iops = self._read_iops or 0.0
        write_iops = self._write_iops or 0.0
        iops = int(read_iops + write_iops)
        return {"cpu": cpu, "mem": mem, "iops": iops}


cloudwatch_rds = CloudWatchRdsMetrics()
