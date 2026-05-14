"""Tests for diagnosis agent tools — Phase 3 real AWS API integration."""

import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src_backend"))


@pytest.fixture(autouse=True)
def reset_clients():
    """Reset global boto3 clients between tests."""
    import agents.diagnosis_agent as mod
    mod._logs_client = None
    mod._rds_client = None
    mod._cw_client = None
    yield


class TestPullLogs:

    @patch("agents.diagnosis_agent._get_logs_client")
    def test_real_pull_logs_returns_log_lines(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.start_query.return_value = {"queryId": "q-123"}
        mock_client.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [
                    {"field": "@timestamp", "value": "2026-05-14T10:00:00Z"},
                    {"field": "@message", "value": "ERROR: Connection refused"},
                ],
                [
                    {"field": "@timestamp", "value": "2026-05-14T10:01:00Z"},
                    {"field": "@message", "value": "WARNING: High latency"},
                ],
            ],
        }

        from agents.diagnosis_agent import _real_pull_logs
        result = _real_pull_logs("aurora-db", 5)
        assert "ERROR: Connection refused" in result
        assert "WARNING: High latency" in result
        mock_client.start_query.assert_called_once()

    @patch("agents.diagnosis_agent._get_logs_client")
    def test_real_pull_logs_no_results(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.start_query.return_value = {"queryId": "q-456"}
        mock_client.get_query_results.return_value = {
            "status": "Complete",
            "results": [],
        }

        from agents.diagnosis_agent import _real_pull_logs
        result = _real_pull_logs("aurora-db", 5)
        assert "No errors found" in result

    @patch("agents.diagnosis_agent._real_pull_logs")
    def test_pull_logs_falls_back_on_error(self, mock_real):
        mock_real.side_effect = Exception("Logs Insights throttled")
        from agents.diagnosis_agent import pull_logs
        result = pull_logs(service="aurora-db", minutes=5)
        assert "ERROR" in result
        assert "Connection pool exhausted" in result

    def test_pull_logs_non_aurora_uses_simulated(self):
        from agents.diagnosis_agent import pull_logs
        result = pull_logs(service="ecs-cluster", minutes=5)
        assert "operating normally" in result


class TestCheckHealth:

    @patch("agents.diagnosis_agent._get_cw_client")
    @patch("agents.diagnosis_agent._get_rds_client")
    def test_real_check_health_available(self, mock_get_rds, mock_get_cw):
        mock_rds = MagicMock()
        mock_get_rds.return_value = mock_rds
        mock_rds.describe_db_clusters.return_value = {
            "DBClusters": [{"Status": "available"}]
        }

        mock_cw = MagicMock()
        mock_get_cw.return_value = mock_cw
        mock_cw.get_metric_statistics.side_effect = [
            {"Datapoints": [{"Timestamp": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc), "Average": 15.0}]},
            {"Datapoints": [{"Timestamp": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc), "Average": 5.0}]},
            {"Datapoints": [{"Timestamp": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc), "Average": 800_000_000.0}]},
        ]

        from agents.diagnosis_agent import _real_check_health
        result = _real_check_health("aurora-db")
        assert "AVAILABLE" in result
        assert "CPU: 15%" in result
        assert "Connections: 5" in result

    @patch("agents.diagnosis_agent._get_cw_client")
    @patch("agents.diagnosis_agent._get_rds_client")
    def test_real_check_health_stopped(self, mock_get_rds, mock_get_cw):
        mock_rds = MagicMock()
        mock_get_rds.return_value = mock_rds
        mock_rds.describe_db_clusters.return_value = {
            "DBClusters": [{"Status": "stopped"}]
        }

        mock_cw = MagicMock()
        mock_get_cw.return_value = mock_cw
        mock_cw.get_metric_statistics.return_value = {"Datapoints": []}

        from agents.diagnosis_agent import _real_check_health
        result = _real_check_health("aurora-db")
        assert "STOPPED" in result
        assert "N/A" in result

    @patch("agents.diagnosis_agent._real_check_health")
    def test_check_health_falls_back_on_error(self, mock_real):
        mock_real.side_effect = Exception("Access denied")
        from agents.diagnosis_agent import check_health
        result = check_health(service="aurora-db")
        assert "UNHEALTHY" in result

    def test_check_health_ecs_uses_simulated(self):
        from agents.diagnosis_agent import check_health
        result = check_health(service="ecs-cluster")
        assert "DEGRADED" in result


class TestCheckRecentChanges:

    @patch("agents.diagnosis_agent._get_rds_client")
    def test_real_check_recent_changes_with_events(self, mock_get_rds):
        mock_rds = MagicMock()
        mock_get_rds.return_value = mock_rds
        mock_rds.describe_events.return_value = {
            "Events": [
                {
                    "Date": datetime(2026, 5, 14, 8, 0, tzinfo=timezone.utc),
                    "Message": "DB cluster stopped",
                },
                {
                    "Date": datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
                    "Message": "DB cluster started",
                },
            ]
        }

        from agents.diagnosis_agent import _real_check_recent_changes
        result = _real_check_recent_changes("aurora-db", 24)
        assert "DB cluster stopped" in result
        assert "DB cluster started" in result
        assert "Recent RDS events" in result

    @patch("agents.diagnosis_agent._get_rds_client")
    def test_real_check_recent_changes_empty(self, mock_get_rds):
        mock_rds = MagicMock()
        mock_get_rds.return_value = mock_rds
        mock_rds.describe_events.return_value = {"Events": []}

        from agents.diagnosis_agent import _real_check_recent_changes
        result = _real_check_recent_changes("aurora-db", 24)
        assert "No recent changes" in result

    @patch("agents.diagnosis_agent._real_check_recent_changes")
    def test_check_recent_changes_falls_back_on_error(self, mock_real):
        mock_real.side_effect = Exception("RDS throttled")
        from agents.diagnosis_agent import check_recent_changes
        result = check_recent_changes(service="aurora-db", hours=24)
        assert "nightly-etl" in result

    def test_check_recent_changes_non_aurora_uses_simulated(self):
        from agents.diagnosis_agent import check_recent_changes
        result = check_recent_changes(service="lambda", hours=24)
        assert "No significant changes" in result


class TestCdkIamPermissions:

    def test_task_role_has_logs_permissions(self):
        import aws_cdk as cdk
        from aws_cdk import assertions
        from src_infra.stack_infrastructure import InfrastructureStack
        from src_infra.stack_backend import BackendStack

        app = cdk.App()
        env_context = {
            "project_name": "rca",
            "ecs": {"cpu": 512, "memory_mib": 1024, "desired_count": 1},
            "bedrock": {"region": "eu-west-1", "models": {"standard": {"model_id": "test-model"}}},
            "nlb_cert_arn": "arn:aws:acm:eu-west-1:123456789012:certificate/test-cert-id",
            "api_token": "test-token",
        }
        infra = InfrastructureStack(app, "TestInfra2", env_name="test", env_context=env_context)
        backend = BackendStack(app, "TestBackend2", env_name="test", env_context=env_context, infrastructure=infra)
        template = assertions.Template.from_stack(backend)

        template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": assertions.Match.object_like({
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Action": ["logs:StartQuery", "logs:GetQueryResults"],
                        "Effect": "Allow",
                    }),
                ]),
            }),
        })

    def test_task_role_has_rds_describe_events(self):
        import aws_cdk as cdk
        from aws_cdk import assertions
        from src_infra.stack_infrastructure import InfrastructureStack
        from src_infra.stack_backend import BackendStack

        app = cdk.App()
        env_context = {
            "project_name": "rca",
            "ecs": {"cpu": 512, "memory_mib": 1024, "desired_count": 1},
            "bedrock": {"region": "eu-west-1", "models": {"standard": {"model_id": "test-model"}}},
            "nlb_cert_arn": "arn:aws:acm:eu-west-1:123456789012:certificate/test-cert-id",
            "api_token": "test-token",
        }
        infra = InfrastructureStack(app, "TestInfra3", env_name="test", env_context=env_context)
        backend = BackendStack(app, "TestBackend3", env_name="test", env_context=env_context, infrastructure=infra)
        template = assertions.Template.from_stack(backend)

        template.has_resource_properties("AWS::IAM::Policy", {
            "PolicyDocument": assertions.Match.object_like({
                "Statement": assertions.Match.array_with([
                    assertions.Match.object_like({
                        "Action": "rds:DescribeEvents",
                        "Effect": "Allow",
                        "Resource": "*",
                    }),
                ]),
            }),
        })
