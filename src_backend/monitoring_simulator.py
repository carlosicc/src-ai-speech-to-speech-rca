import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Optional

from shared.state import Phase, demo_state

logger = logging.getLogger(__name__)

METRICS_INTERVAL: float = 2.0


@dataclass
class ServiceProfile:
    cpu_min: int
    cpu_max: int
    mem_min: int
    mem_max: int
    iops_min: int
    iops_max: int


NORMAL_PROFILES: dict[str, ServiceProfile] = {
    "monitoring": ServiceProfile(20, 40, 30, 50, 100, 500),
    "network": ServiceProfile(10, 30, 20, 40, 50, 200),
    "aurora-db": ServiceProfile(30, 60, 40, 70, 1000, 5000),
    "ecs-cluster": ServiceProfile(40, 70, 50, 80, 200, 800),
    "lambda": ServiceProfile(10, 50, 20, 60, 50, 300),
    "api-gateway": ServiceProfile(15, 35, 25, 45, 100, 400),
    "s3-storage": ServiceProfile(5, 15, 10, 30, 50, 200),
}

INCIDENT_OVERRIDES: dict[str, ServiceProfile] = {
    "aurora-db": ServiceProfile(95, 100, 90, 95, 0, 0),
    "ecs-cluster": ServiceProfile(80, 90, 70, 85, 100, 300),
}

INCIDENT_CPU_BOOST: int = 15


@dataclass
class MetricSnapshot:
    service: str
    cpu: int
    mem: int
    iops: int


def generate_metrics(incident_service: Optional[str] = None) -> list[MetricSnapshot]:
    results: list[MetricSnapshot] = []
    for service, profile in NORMAL_PROFILES.items():
        if incident_service and service in INCIDENT_OVERRIDES:
            p = INCIDENT_OVERRIDES[service]
            cpu = random.randint(p.cpu_min, p.cpu_max)
            mem = random.randint(p.mem_min, p.mem_max)
            iops = random.randint(p.iops_min, p.iops_max)
        elif incident_service and service != incident_service:
            cpu = random.randint(profile.cpu_min, profile.cpu_max) + random.randint(0, INCIDENT_CPU_BOOST)
            mem = random.randint(profile.mem_min, profile.mem_max)
            iops = random.randint(profile.iops_min, profile.iops_max)
        else:
            cpu = random.randint(profile.cpu_min, profile.cpu_max)
            mem = random.randint(profile.mem_min, profile.mem_max)
            iops = random.randint(profile.iops_min, profile.iops_max)
        results.append(MetricSnapshot(service=service, cpu=cpu, mem=mem, iops=iops))
    return results


class MonitoringSimulator:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._broadcast_fn = None

    async def start(self, broadcast_fn) -> None:
        self._broadcast_fn = broadcast_fn
        self._task = asyncio.create_task(self._loop())
        logger.info("Monitoring simulator started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Monitoring simulator stopped")

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(METRICS_INTERVAL)
                if self._broadcast_fn is None:
                    continue
                incident_service = None
                if demo_state.incident and demo_state.phase not in (Phase.HEALTHY, Phase.RESOLVED):
                    incident_service = demo_state.incident.service
                metrics = generate_metrics(incident_service)
                for m in metrics:
                    await self._broadcast_fn({
                        "type": "metrics_update",
                        "payload": {
                            "service": m.service,
                            "cpu": m.cpu,
                            "mem": m.mem,
                            "iops": m.iops,
                        },
                    })
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")


monitoring_simulator = MonitoringSimulator()
