"""Tests for metrics/cloudwatch_rds.py — Phase 2 real CloudWatch metrics."""

import sys
import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest

# Ensure src_backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src_backend"))


@pytest.fixture(autouse=True)
def reset_module():
    """Re-import module fresh for each test to reset global state."""
    import importlib
    if "metrics.cloudwatch_rds" in sys.modules:
        importlib.reload(sys.modules["metrics.cloudwatch_rds"])
    yield


@patch("metrics.cloudwatch_rds.boto3.client")
def test_fetch_metric_returns_latest_datapoint(mock_boto_client):
    mock_cw = MagicMock()
    mock_boto_client.return_value = mock_cw
    mock_cw.get_metric_statistics.return_value = {
        "Datapoints": [
            {"Timestamp": datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc), "Average": 5.0},
            {"Timestamp": datetime(2026, 5, 14, 10, 1, tzinfo=timezone.utc), "Average": 8.0},
        ]
    }

    from metrics.cloudwatch_rds import _fetch_metric, _get_client
    # Force client init
    import metrics.cloudwatch_rds as mod
    mod._client = None
    result = _fetch_metric("CPUUtilization")
    assert result == 8.0


@patch("metrics.cloudwatch_rds.boto3.client")
def test_fetch_metric_returns_none_on_empty(mock_boto_client):
    mock_cw = MagicMock()
    mock_boto_client.return_value = mock_cw
    mock_cw.get_metric_statistics.return_value = {"Datapoints": []}

    import metrics.cloudwatch_rds as mod
    mod._client = None
    result = mod._fetch_metric("CPUUtilization")
    assert result is None


@patch("metrics.cloudwatch_rds.boto3.client")
def test_fetch_metric_returns_none_on_exception(mock_boto_client):
    mock_cw = MagicMock()
    mock_boto_client.return_value = mock_cw
    mock_cw.get_metric_statistics.side_effect = Exception("throttled")

    import metrics.cloudwatch_rds as mod
    mod._client = None
    result = mod._fetch_metric("CPUUtilization")
    assert result is None


@patch("metrics.cloudwatch_rds._fetch_metric")
def test_get_current_metrics_shape(mock_fetch):
    mock_fetch.side_effect = [
        25.0,           # CPUUtilization
        800_000_000.0,  # FreeableMemory (800MB of ~1GB)
        150.0,          # ReadIOPS
        50.0,           # WriteIOPS
        3.0,            # DatabaseConnections
    ]

    from metrics.cloudwatch_rds import CloudWatchRdsMetrics
    poller = CloudWatchRdsMetrics()
    poller._fetch_all()
    poller._ready = True

    result = poller.get_current_metrics()
    assert result is not None
    assert "cpu" in result
    assert "mem" in result
    assert "iops" in result
    assert result["cpu"] == 25
    # ~20% memory used (200MB / 1GB)
    assert 15 <= result["mem"] <= 25
    assert result["iops"] == 200  # 150 + 50


def test_get_current_metrics_returns_none_when_not_ready():
    from metrics.cloudwatch_rds import CloudWatchRdsMetrics
    poller = CloudWatchRdsMetrics()
    assert poller.get_current_metrics() is None


@patch("metrics.cloudwatch_rds._fetch_metric")
def test_get_current_metrics_zero_on_none_values(mock_fetch):
    mock_fetch.return_value = None

    from metrics.cloudwatch_rds import CloudWatchRdsMetrics
    poller = CloudWatchRdsMetrics()
    poller._fetch_all()
    poller._ready = True

    result = poller.get_current_metrics()
    assert result == {"cpu": 0, "mem": 0, "iops": 0}
