import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from shared.config import DEFAULT_PHONE_NUMBER, DEFAULT_VOICE_MODE

logger = logging.getLogger(__name__)


class Phase(str, Enum):
    HEALTHY = "HEALTHY"
    INCIDENT_DETECTED = "INCIDENT_DETECTED"
    DIAGNOSING = "DIAGNOSING"
    CALLING = "CALLING"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"


PHASE_ORDER: list[Phase] = [
    Phase.HEALTHY,
    Phase.INCIDENT_DETECTED,
    Phase.DIAGNOSING,
    Phase.CALLING,
    Phase.RECOVERING,
    Phase.RESOLVED,
]


@dataclass
class Incident:
    incident_id: str = field(default_factory=lambda: str(uuid4()))
    service: str = "aurora-db"
    severity: str = "critical"
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DemoState:
    phase: Phase = Phase.HEALTHY
    incident: Optional[Incident] = None
    voice_mode: str = DEFAULT_VOICE_MODE
    phone_number: str = DEFAULT_PHONE_NUMBER
    auto_advance: bool = True

    def trigger_incident(self, service: str = "aurora-db") -> Incident:
        self.incident = Incident(service=service)
        self.phase = Phase.INCIDENT_DETECTED
        logger.info(f"Incident triggered on {service}: {self.incident.incident_id}")
        return self.incident

    def advance_phase(self) -> Phase:
        idx = PHASE_ORDER.index(self.phase)
        next_idx = (idx + 1) % len(PHASE_ORDER)
        self.phase = PHASE_ORDER[next_idx]
        if self.phase == Phase.HEALTHY:
            self.incident = None
        logger.info(f"Phase advanced to {self.phase.value}")
        return self.phase

    def reset(self) -> None:
        self.phase = Phase.HEALTHY
        self.incident = None
        logger.info("Demo state reset to HEALTHY")


demo_state = DemoState()
