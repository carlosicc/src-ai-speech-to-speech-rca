"""Pydantic models for structured data across the RCA platform."""

from datetime import datetime
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    ESCALATING = "escalating"
    CALLING = "calling"
    RECOVERING = "recovering"
    RESOLVED = "resolved"


class Incident(BaseModel):
    incident_id: str
    status: IncidentStatus
    severity: Severity
    service_name: str
    description: str
    started_at: datetime
    resolved_at: Optional[datetime] = None
    rca_summary: Optional[str] = None


class IncidentPhase(BaseModel):
    incident_id: str
    phase_name: str
    agent_name: str
    timestamp: datetime
    details: str
    success: bool = True


class AgentPrompt(BaseModel):
    agent_type: str
    prompt_text: str
    max_tokens: int = 4096
    version: str = "LATEST"
