import asyncio
import logging
from typing import Optional
from strands import Agent, tool
from strands.models import BedrockModel
from shared.config import BEDROCK_MODEL_ID, BEDROCK_REGION
from shared.prompts import get_prompt, get_soul

logger = logging.getLogger(__name__)

FALLBACK_PROMPT = """You are the Master Agent for an AI Operations Center.
When an incident is reported, follow this Standard Operating Procedure (SoP):

1. ASSESS: Use assess_severity to evaluate the incident severity.
2. DIAGNOSE: Use activate_diagnosis to run the diagnosis agent and get the RCA.
3. ESCALATE: Use activate_voice_call to connect with the on-call DBA for authorization.
4. RESOLVE: Once the DBA authorizes, use update_incident_status to mark as recovering/resolved.

Always follow the SoP in order. Be concise in your reasoning. Execute each tool exactly once."""

FALLBACK_SOUL = """You are decisive, calm, and methodical.
You follow standard operating procedures precisely.
You communicate status updates clearly and briefly."""

ORCHESTRATION_TIMEOUT: float = 150.0

_broadcast_fn = None
_on_phase_change_fn = None
_event_loop: Optional[asyncio.AbstractEventLoop] = None


def set_broadcast(broadcast_fn, on_phase_change_fn) -> None:
    global _broadcast_fn, _on_phase_change_fn
    _broadcast_fn = broadcast_fn
    _on_phase_change_fn = on_phase_change_fn


def _run_async(coro) -> None:
    """Run an async coroutine from a sync tool context (fire-and-forget for broadcasts)."""
    if _event_loop and _event_loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, _event_loop)
    else:
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            pass


def _run_async_with_result(coro, timeout: float = 60.0):
    """Run an async coroutine and return the result from a sync tool context."""
    if _event_loop and _event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _event_loop)
        return future.result(timeout=timeout)
    try:
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
    except RuntimeError:
        return asyncio.run(coro)


async def _broadcast(message: dict) -> None:
    if _broadcast_fn:
        await _broadcast_fn(message)


async def _notify_agent_activity(agent_name: str, status: str) -> None:
    await _broadcast({
        "type": "agent_activity",
        "payload": {"agent": agent_name, "status": status},
    })


@tool
def assess_severity(service: str, incident_id: str) -> str:
    """Assess the severity of an incident based on the affected service.

    Args:
        service: The affected service name (e.g., 'aurora-db')
        incident_id: The incident identifier
    """
    logger.info(f"Tool: assess_severity(service={service}, incident_id={incident_id})")
    _run_async(_notify_agent_activity("master", "assessing"))

    severity_map = {
        "aurora-db": ("CRITICAL", "Production database — all services depend on it"),
        "ecs-cluster": ("HIGH", "Compute layer — affects running tasks"),
        "api-gateway": ("HIGH", "Entry point — all external traffic blocked"),
        "lambda": ("MEDIUM", "Serverless compute — partial degradation"),
        "s3-storage": ("LOW", "Storage — async operations affected"),
        "monitoring": ("LOW", "Observability — no user impact"),
        "network": ("CRITICAL", "Network layer — total connectivity loss"),
    }
    severity, reason = severity_map.get(service, ("MEDIUM", "Unknown service"))
    return (
        f"Severity Assessment for incident {incident_id[:8]}:\n"
        f"Service: {service}\n"
        f"Severity: {severity}\n"
        f"Reason: {reason}\n"
        f"Action: {'Immediate escalation required' if severity == 'CRITICAL' else 'Monitor and escalate if needed'}"
    )


@tool
def activate_diagnosis(service: str, incident_id: str) -> str:
    """Activate the diagnosis agent to investigate the incident root cause.

    Args:
        service: The affected service to diagnose
        incident_id: The incident identifier
    """
    logger.info(f"Tool: activate_diagnosis(service={service}, incident_id={incident_id})")

    _run_async(_notify_agent_activity("diagnosis", "running"))
    _run_async(_broadcast({
        "type": "agent_log",
        "payload": {"message": "Master Agent → activating Diagnosis Agent...", "level": "info"},
    }))

    from agents.diagnosis_agent import run_diagnosis, _fallback_rca
    try:
        rca = _run_async_with_result(
            asyncio.wait_for(run_diagnosis(service, incident_id), timeout=30.0)
        )
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Diagnosis agent failed/timed out: {e}")
        rca = _fallback_rca(service, incident_id)

    _run_async(_broadcast({
        "type": "agent_log",
        "payload": {"message": f"RCA Complete: {rca[:200]}", "level": "success"},
    }))
    _run_async(_notify_agent_activity("diagnosis", "complete"))

    return rca


@tool
def activate_voice_call(incident_id: str, severity: str, rca_summary: str) -> str:
    """Activate voice call to on-call DBA for incident authorization and recovery.

    Args:
        incident_id: The incident identifier
        severity: The assessed severity level
        rca_summary: Brief RCA summary to provide context to the DBA
    """
    logger.info(f"Tool: activate_voice_call(incident_id={incident_id}, severity={severity})")

    _run_async(_notify_agent_activity("voice", "calling"))
    _run_async(_broadcast({
        "type": "agent_log",
        "payload": {"message": "Master Agent → escalating to on-call DBA via voice...", "level": "warn"},
    }))

    from shared.state import Phase, demo_state
    demo_state.phase = Phase.CALLING
    if _on_phase_change_fn:
        _run_async(_on_phase_change_fn())

    return (
        f"Voice call initiated for incident {incident_id[:8]}.\n"
        f"Severity: {severity}\n"
        f"Waiting for DBA authentication and recovery authorization.\n"
        f"The voice agent will handle the conversation and tool execution."
    )


@tool
def update_incident_status(incident_id: str, new_status: str, resolution: str = "") -> str:
    """Update the incident status after DBA authorization or recovery completion.

    Args:
        incident_id: The incident identifier
        new_status: New status: 'recovering' or 'resolved'
        resolution: Description of the resolution applied
    """
    logger.info(f"Tool: update_incident_status(incident_id={incident_id}, status={new_status})")

    from shared.state import Phase, demo_state
    if new_status == "recovering":
        demo_state.phase = Phase.RECOVERING
    elif new_status == "resolved":
        demo_state.phase = Phase.RESOLVED

    if _on_phase_change_fn:
        _run_async(_on_phase_change_fn())

    _run_async(_notify_agent_activity("master", new_status))
    _run_async(_broadcast({
        "type": "agent_log",
        "payload": {
            "message": f"Incident {incident_id[:8]} → {new_status.upper()}: {resolution or 'status updated'}",
            "level": "success" if new_status == "resolved" else "info",
        },
    }))

    return f"Incident {incident_id[:8]} status updated to {new_status}. {resolution}"


def _build_system_prompt() -> str:
    prompt = get_prompt("master") or FALLBACK_PROMPT
    soul = get_soul("master_agent") or FALLBACK_SOUL
    return f"{soul}\n\n{prompt}"


async def run_master_orchestration(service: str, incident_id: str) -> str:
    """Run the master agent to orchestrate the full incident lifecycle.

    Returns a summary of all actions taken.
    """
    global _event_loop
    _event_loop = asyncio.get_event_loop()
    logger.info(f"Master agent starting orchestration: service={service}, incident={incident_id}")

    await _notify_agent_activity("master", "active")
    await _broadcast({
        "type": "agent_log",
        "payload": {"message": "Master Agent activated — following SoP...", "level": "warn"},
    })

    system_prompt = _build_system_prompt()

    try:
        model = BedrockModel(
            model_id=BEDROCK_MODEL_ID,
            region_name=BEDROCK_REGION,
        )
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=[assess_severity, activate_diagnosis, activate_voice_call, update_incident_status],
        )

        user_prompt = (
            f"Incident {incident_id} detected on service '{service}' with severity CRITICAL.\n"
            f"Follow the SoP: assess severity, run diagnosis, escalate via voice call, "
            f"then update status to recovering.\n"
            f"Execute each step in order."
        )

        response = await asyncio.to_thread(agent, user_prompt)
        summary = str(response)
        logger.info(f"Master agent orchestration complete: incident={incident_id}")
        await _notify_agent_activity("master", "complete")
        return summary

    except Exception as e:
        logger.error(f"Master agent failed: {e}")
        await _notify_agent_activity("master", "error")
        return f"Master agent error: {e}"


async def run_master_orchestration_fallback(service: str, incident_id: str) -> str:
    """Fallback orchestration when LLM is unavailable — executes SoP directly."""
    logger.info(f"Master agent fallback: service={service}, incident={incident_id}")

    await _notify_agent_activity("master", "active")
    await _broadcast({
        "type": "agent_log",
        "payload": {"message": "Master Agent activated (deterministic SoP)...", "level": "warn"},
    })

    # Step 1: Assess severity
    await _notify_agent_activity("master", "assessing")
    await _broadcast({
        "type": "agent_log",
        "payload": {"message": f"Assessing severity for {service}...", "level": "info"},
    })
    await asyncio.sleep(1.0)
    await _broadcast({
        "type": "agent_log",
        "payload": {"message": f"Severity: CRITICAL — {service} is a production dependency", "level": "error"},
    })

    # Step 2: Diagnosis
    await _notify_agent_activity("diagnosis", "running")
    await _broadcast({
        "type": "agent_log",
        "payload": {"message": "Master Agent → activating Diagnosis Agent...", "level": "info"},
    })

    from agents.diagnosis_agent import run_diagnosis, _fallback_rca
    try:
        rca = await asyncio.wait_for(run_diagnosis(service, incident_id), timeout=30.0)
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Diagnosis failed in fallback: {e}")
        rca = _fallback_rca(service, incident_id)

    await _broadcast({
        "type": "agent_log",
        "payload": {"message": f"RCA Complete: {rca[:200]}", "level": "success"},
    })
    await _notify_agent_activity("diagnosis", "complete")

    # Step 3: Escalate — advance to CALLING phase
    await _notify_agent_activity("voice", "calling")
    await _broadcast({
        "type": "agent_log",
        "payload": {"message": "Master Agent → escalating to on-call DBA via voice...", "level": "warn"},
    })

    from shared.state import Phase, demo_state
    demo_state.phase = Phase.CALLING
    if _on_phase_change_fn:
        await _on_phase_change_fn()

    return rca
