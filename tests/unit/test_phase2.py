import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from monitoring_simulator import (
    INCIDENT_OVERRIDES,
    NORMAL_PROFILES,
    MetricSnapshot,
    MonitoringSimulator,
    generate_metrics,
)
from shared.state import DemoState, Phase, demo_state


@pytest.fixture(autouse=True)
def reset_state():
    demo_state.reset()
    demo_state.auto_advance = True
    demo_state.voice_mode = "mode_c"
    demo_state.phone_number = "+44XXXXXXXXXX"
    yield
    demo_state.reset()


class TestGenerateMetrics:
    def test_generates_all_seven_services(self):
        metrics = generate_metrics()
        assert len(metrics) == 7
        service_names = {m.service for m in metrics}
        assert service_names == set(NORMAL_PROFILES.keys())

    def test_healthy_metrics_within_normal_range(self):
        for _ in range(20):
            metrics = generate_metrics()
            for m in metrics:
                profile = NORMAL_PROFILES[m.service]
                assert profile.cpu_min <= m.cpu <= profile.cpu_max + 1
                assert profile.mem_min <= m.mem <= profile.mem_max
                assert profile.iops_min <= m.iops <= profile.iops_max

    def test_incident_metrics_aurora_spikes(self):
        for _ in range(20):
            metrics = generate_metrics(incident_service="aurora-db")
            aurora = next(m for m in metrics if m.service == "aurora-db")
            assert aurora.cpu >= 95
            assert aurora.mem >= 90
            assert aurora.iops == 0

    def test_incident_ecs_affected(self):
        for _ in range(20):
            metrics = generate_metrics(incident_service="aurora-db")
            ecs = next(m for m in metrics if m.service == "ecs-cluster")
            assert ecs.cpu >= 80

    def test_incident_other_services_slight_degradation(self):
        metrics = generate_metrics(incident_service="aurora-db")
        for m in metrics:
            if m.service not in INCIDENT_OVERRIDES:
                profile = NORMAL_PROFILES[m.service]
                assert m.cpu <= profile.cpu_max + 15 + 1

    def test_metric_snapshot_structure(self):
        metrics = generate_metrics()
        for m in metrics:
            assert isinstance(m, MetricSnapshot)
            assert isinstance(m.cpu, int)
            assert isinstance(m.mem, int)
            assert isinstance(m.iops, int)
            assert isinstance(m.service, str)


class TestMonitoringSimulator:
    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        sim = MonitoringSimulator()
        broadcast = AsyncMock()
        await sim.start(broadcast)
        assert sim._task is not None
        await asyncio.sleep(0.05)
        await sim.stop()
        assert sim._task is None

    @pytest.mark.asyncio
    async def test_broadcasts_metrics(self):
        sim = MonitoringSimulator()
        broadcast = AsyncMock()
        await sim.start(broadcast)
        await asyncio.sleep(2.2)
        await sim.stop()
        assert broadcast.call_count >= 7
        first_call = broadcast.call_args_list[0][0][0]
        assert first_call["type"] == "metrics_update"
        assert "service" in first_call["payload"]
        assert "cpu" in first_call["payload"]
        assert "mem" in first_call["payload"]
        assert "iops" in first_call["payload"]

    @pytest.mark.asyncio
    async def test_incident_mode_changes_metrics(self):
        sim = MonitoringSimulator()
        broadcast = AsyncMock()
        demo_state.trigger_incident("aurora-db")
        await sim.start(broadcast)
        await asyncio.sleep(2.2)
        await sim.stop()
        aurora_calls = [
            c[0][0] for c in broadcast.call_args_list
            if c[0][0].get("payload", {}).get("service") == "aurora-db"
        ]
        assert len(aurora_calls) > 0
        for call in aurora_calls:
            assert call["payload"]["cpu"] >= 95


class TestDiagnosisAgentTools:
    @patch("agents.diagnosis_agent._real_pull_logs", side_effect=Exception("no creds"))
    def test_pull_logs_aurora_fallback(self, _mock):
        from agents.diagnosis_agent import pull_logs
        result = pull_logs._tool_func(service="aurora-db", minutes=5)
        assert "ERROR" in result
        assert "Connection pool exhausted" in result

    def test_pull_logs_healthy_service(self):
        from agents.diagnosis_agent import pull_logs
        result = pull_logs._tool_func(service="lambda", minutes=5)
        assert "operating normally" in result

    @patch("agents.diagnosis_agent._real_check_health", side_effect=Exception("no creds"))
    def test_check_health_aurora_fallback(self, _mock):
        from agents.diagnosis_agent import check_health
        result = check_health._tool_func(service="aurora-db")
        assert "UNHEALTHY" in result
        assert "saturated" in result

    def test_check_health_ecs(self):
        from agents.diagnosis_agent import check_health
        result = check_health._tool_func(service="ecs-cluster")
        assert "DEGRADED" in result

    def test_check_health_healthy_service(self):
        from agents.diagnosis_agent import check_health
        result = check_health._tool_func(service="s3-storage")
        assert "HEALTHY" in result

    @patch("agents.diagnosis_agent._real_check_recent_changes", side_effect=Exception("no creds"))
    def test_check_recent_changes_aurora_fallback(self, _mock):
        from agents.diagnosis_agent import check_recent_changes
        result = check_recent_changes._tool_func(service="aurora-db", hours=24)
        assert "nightly-etl" in result
        assert "Root cause indicator" in result

    def test_check_recent_changes_no_changes(self):
        from agents.diagnosis_agent import check_recent_changes
        result = check_recent_changes._tool_func(service="lambda", hours=24)
        assert "No significant changes" in result


class TestDiagnosisAgentFallback:
    def test_fallback_rca_produces_summary(self):
        from agents.diagnosis_agent import _fallback_rca
        result = _fallback_rca("aurora-db", "test-incident-123")
        assert "aurora-db" in result
        assert "Root Cause" in result
        assert "Recommended Action" in result

    @pytest.mark.asyncio
    async def test_run_diagnosis_uses_fallback_on_error(self):
        from agents.diagnosis_agent import run_diagnosis
        with patch("agents.diagnosis_agent.BedrockModel", side_effect=Exception("No credentials")):
            result = await run_diagnosis("aurora-db", "test-123")
        assert "aurora-db" in result
        assert "Root Cause" in result


class TestPromptsLoader:
    def test_get_prompt_returns_none_without_table(self):
        from shared.prompts import get_prompt, clear_cache
        clear_cache()
        with patch.dict("os.environ", {"DDB_TABLE_NAME": ""}, clear=False):
            result = get_prompt("diagnosis")
        assert result is None

    def test_get_soul_returns_none_without_table(self):
        from shared.prompts import get_soul, clear_cache
        clear_cache()
        with patch.dict("os.environ", {"DDB_TABLE_NAME": ""}, clear=False):
            result = get_soul("diagnosis_agent")
        assert result is None

    def test_get_prompt_caches_result(self):
        from shared.prompts import get_prompt, clear_cache, _cache
        clear_cache()
        _cache["PROMPT#test_agent"] = ("cached prompt", time.time())
        result = get_prompt("test_agent")
        assert result == "cached prompt"
        clear_cache()

    def test_get_prompt_from_dynamodb(self):
        from shared.prompts import get_prompt, clear_cache
        clear_cache()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"PK": "PROMPT#diagnosis", "SK": "LATEST", "prompt_text": "You are a diagnosis agent"}
        }
        with patch.dict("os.environ", {"DDB_TABLE_NAME": "test-table"}, clear=False):
            with patch("shared.prompts._get_table", return_value=mock_table):
                result = get_prompt("diagnosis")
        assert result == "You are a diagnosis agent"
        clear_cache()

    def test_get_soul_from_dynamodb(self):
        from shared.prompts import get_soul, clear_cache
        clear_cache()
        mock_table = MagicMock()
        mock_table.get_item.return_value = {
            "Item": {"PK": "SOUL#diagnosis_agent", "SK": "LATEST", "soul_text": "Calm and precise"}
        }
        with patch.dict("os.environ", {"DDB_TABLE_NAME": "test-table"}, clear=False):
            with patch("shared.prompts._get_table", return_value=mock_table):
                result = get_soul("diagnosis_agent")
        assert result == "Calm and precise"
        clear_cache()

    def test_cache_expires(self):
        from shared.prompts import get_prompt, clear_cache, _cache, CACHE_TTL_SECONDS
        clear_cache()
        _cache["PROMPT#expired"] = ("old prompt", time.time() - CACHE_TTL_SECONDS - 1)
        with patch.dict("os.environ", {"DDB_TABLE_NAME": ""}, clear=False):
            result = get_prompt("expired")
        assert result is None
        clear_cache()


class TestDemoControllerDiagnosisIntegration:
    @pytest.mark.asyncio
    async def test_run_phases_calls_diagnosis(self):
        from demo_controller import DemoController
        from websocket_server import manager
        from agents.master_agent import set_broadcast
        controller = DemoController()
        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.DIAGNOSING
        broadcast_mock = AsyncMock()
        manager.broadcast = broadcast_mock
        set_broadcast(broadcast_mock, AsyncMock())
        with patch("agents.diagnosis_agent.run_diagnosis", new_callable=AsyncMock) as mock_diag:
            mock_diag.return_value = "Test RCA: database overloaded"
            with patch("agents.master_agent.run_master_orchestration", new_callable=AsyncMock) as mock_master:
                mock_master.side_effect = RuntimeError("force fallback")
                task = asyncio.create_task(controller._run_master_orchestration())
                await task
        agent_log_calls = [
            c[0][0] for c in broadcast_mock.call_args_list
            if c[0][0].get("type") == "agent_log"
        ]
        assert len(agent_log_calls) >= 2
        assert any("RCA Complete" in c["payload"]["message"] for c in agent_log_calls)

    @pytest.mark.asyncio
    async def test_diagnosis_timeout_uses_fallback(self):
        from demo_controller import DemoController
        from websocket_server import manager
        from agents.master_agent import set_broadcast
        controller = DemoController()
        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.DIAGNOSING
        broadcast_mock = AsyncMock()
        manager.broadcast = broadcast_mock
        set_broadcast(broadcast_mock, AsyncMock())

        async def slow_diagnosis(*args, **kwargs):
            await asyncio.sleep(999)
            return "never reached"

        with patch("agents.diagnosis_agent.run_diagnosis", new=slow_diagnosis):
            with patch("agents.master_agent.run_master_orchestration", new_callable=AsyncMock) as mock_master:
                mock_master.side_effect = RuntimeError("force fallback")
                task = asyncio.create_task(controller._run_master_orchestration())
                await task
        rca_calls = [
            c[0][0] for c in broadcast_mock.call_args_list
            if c[0][0].get("type") == "agent_log" and "RCA Complete" in c[0][0].get("payload", {}).get("message", "")
        ]
        assert len(rca_calls) == 1
        assert "RCA Summary" in rca_calls[0]["payload"]["message"]
