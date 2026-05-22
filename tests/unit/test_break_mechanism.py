import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src_backend"))

from shared.state import DemoState, Phase, demo_state


@pytest.fixture(autouse=True)
def reset_state():
    demo_state.reset()
    demo_state.auto_advance = False
    demo_state.voice_mode = "mode_b"
    demo_state.phone_number = "+44XXXXXXXXXX"
    yield
    demo_state.reset()


class TestNetworkOperations:
    @pytest.mark.asyncio
    async def test_revoke_db_access_success(self):
        from shared.network_operations import revoke_db_access

        mock_client = MagicMock()
        mock_client.revoke_security_group_ingress = MagicMock(return_value={})

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await revoke_db_access()

        assert result["status"] == "success"
        mock_client.revoke_security_group_ingress.assert_called_once()
        call_kwargs = mock_client.revoke_security_group_ingress.call_args[1]
        assert call_kwargs["GroupId"] == "sg-XXXXXXXXXXXXXXXXX"
        assert call_kwargs["IpPermissions"][0]["FromPort"] == 3306

    @pytest.mark.asyncio
    async def test_revoke_db_access_already_revoked(self):
        from shared.network_operations import revoke_db_access
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.revoke_security_group_ingress = MagicMock(
            side_effect=ClientError(
                {"Error": {"Code": "InvalidPermission.NotFound", "Message": "rule not found"}},
                "RevokeSecurityGroupIngress",
            )
        )

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await revoke_db_access()

        assert result["status"] == "already_revoked"

    @pytest.mark.asyncio
    async def test_revoke_db_access_error(self):
        from shared.network_operations import revoke_db_access
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.revoke_security_group_ingress = MagicMock(
            side_effect=ClientError(
                {"Error": {"Code": "UnauthorizedOperation", "Message": "no permission"}},
                "RevokeSecurityGroupIngress",
            )
        )

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await revoke_db_access()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_restore_db_access_success(self):
        from shared.network_operations import restore_db_access

        mock_client = MagicMock()
        mock_client.authorize_security_group_ingress = MagicMock(return_value={})

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await restore_db_access()

        assert result["status"] == "success"
        mock_client.authorize_security_group_ingress.assert_called_once()
        call_kwargs = mock_client.authorize_security_group_ingress.call_args[1]
        assert call_kwargs["GroupId"] == "sg-XXXXXXXXXXXXXXXXX"
        assert call_kwargs["IpPermissions"][0]["UserIdGroupPairs"][0]["GroupId"] == "sg-YYYYYYYYYYYYYYYYY"

    @pytest.mark.asyncio
    async def test_restore_db_access_already_present(self):
        from shared.network_operations import restore_db_access
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.authorize_security_group_ingress = MagicMock(
            side_effect=ClientError(
                {"Error": {"Code": "InvalidPermission.Duplicate", "Message": "rule exists"}},
                "AuthorizeSecurityGroupIngress",
            )
        )

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await restore_db_access()

        assert result["status"] == "already_present"

    @pytest.mark.asyncio
    async def test_restore_db_access_error(self):
        from shared.network_operations import restore_db_access
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.authorize_security_group_ingress = MagicMock(
            side_effect=ClientError(
                {"Error": {"Code": "UnauthorizedOperation", "Message": "no permission"}},
                "AuthorizeSecurityGroupIngress",
            )
        )

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await restore_db_access()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_check_sg_rule_exists_true(self):
        from shared.network_operations import check_sg_rule_exists

        mock_client = MagicMock()
        mock_client.describe_security_groups = MagicMock(return_value={
            "SecurityGroups": [{
                "IpPermissions": [{
                    "FromPort": 3306,
                    "ToPort": 3306,
                    "IpProtocol": "tcp",
                    "UserIdGroupPairs": [{"GroupId": "sg-YYYYYYYYYYYYYYYYY"}],
                }]
            }]
        })

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await check_sg_rule_exists()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_sg_rule_exists_false(self):
        from shared.network_operations import check_sg_rule_exists

        mock_client = MagicMock()
        mock_client.describe_security_groups = MagicMock(return_value={
            "SecurityGroups": [{"IpPermissions": []}]
        })

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await check_sg_rule_exists()

        assert result is False

    @pytest.mark.asyncio
    async def test_check_sg_rule_exists_error_returns_false(self):
        from shared.network_operations import check_sg_rule_exists

        mock_client = MagicMock()
        mock_client.describe_security_groups = MagicMock(side_effect=Exception("network error"))

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            result = await check_sg_rule_exists()

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_no_config(self):
        from shared.network_operations import revoke_db_access

        with patch("shared.network_operations.RDS_SECURITY_GROUP_ID", ""):
            result = await revoke_db_access()

        assert result["status"] == "error"
        assert "not configured" in result["message"]

    @pytest.mark.asyncio
    async def test_restore_no_config(self):
        from shared.network_operations import restore_db_access

        with patch("shared.network_operations.ECS_SECURITY_GROUP_ID", ""):
            result = await restore_db_access()

        assert result["status"] == "error"
        assert "not configured" in result["message"]


class TestCheckNetworkTool:
    def test_check_network_rule_present(self):
        from agents.diagnosis_agent import check_network

        mock_client = MagicMock()
        mock_client.describe_security_groups = MagicMock(return_value={
            "SecurityGroups": [{
                "IpPermissions": [{
                    "FromPort": 3306,
                    "ToPort": 3306,
                    "IpProtocol": "tcp",
                    "UserIdGroupPairs": [{"GroupId": "sg-YYYYYYYYYYYYYYYYY"}],
                }]
            }]
        })

        with patch("agents.diagnosis_agent._get_ec2_client", return_value=mock_client):
            result = check_network(service="aurora-db")

        assert "OK" in result
        assert "3306" in result

    def test_check_network_rule_missing(self):
        from agents.diagnosis_agent import check_network

        mock_client = MagicMock()
        mock_client.describe_security_groups = MagicMock(return_value={
            "SecurityGroups": [{"IpPermissions": []}]
        })

        with patch("agents.diagnosis_agent._get_ec2_client", return_value=mock_client):
            result = check_network(service="aurora-db")

        assert "ALERT" in result
        assert "MISSING" in result
        assert "3306" in result

    def test_check_network_api_error_fallback(self):
        from agents.diagnosis_agent import check_network

        mock_client = MagicMock()
        mock_client.describe_security_groups = MagicMock(side_effect=Exception("timeout"))

        with patch("agents.diagnosis_agent._get_ec2_client", return_value=mock_client):
            result = check_network(service="aurora-db")

        assert "ALERT" in result
        assert "timeout" in result

    def test_check_network_non_aurora_service(self):
        from agents.diagnosis_agent import check_network

        result = check_network(service="ecs-cluster")
        assert "OK" in result


class TestBreakDatabaseWebSocket:
    @pytest.mark.asyncio
    async def test_break_database_calls_revoke_and_triggers_incident(self):
        from websocket_server import handle_client_message, manager

        manager.active_connections = []

        with patch("shared.network_operations._get_ec2_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.revoke_security_group_ingress = MagicMock(return_value={})
            mock_get_client.return_value = mock_client

            with patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
                msg = json.dumps({"type": "break_database", "payload": {}})
                await handle_client_message(msg)

                mock_client.revoke_security_group_ingress.assert_called_once()
                mock_trigger.assert_called_once_with("aurora-db")

    @pytest.mark.asyncio
    async def test_break_database_ignored_when_not_healthy(self):
        from websocket_server import handle_client_message

        demo_state.trigger_incident("aurora-db")

        with patch("shared.network_operations._get_ec2_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            msg = json.dumps({"type": "break_database", "payload": {}})
            await handle_client_message(msg)

            mock_client.revoke_security_group_ingress.assert_not_called()

    @pytest.mark.asyncio
    async def test_break_database_does_not_trigger_on_aws_error(self):
        from websocket_server import handle_client_message, manager
        from botocore.exceptions import ClientError

        manager.active_connections = []

        with patch("shared.network_operations._get_ec2_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.revoke_security_group_ingress = MagicMock(
                side_effect=ClientError(
                    {"Error": {"Code": "UnauthorizedOperation", "Message": "no access"}},
                    "RevokeSecurityGroupIngress",
                )
            )
            mock_get_client.return_value = mock_client

            with patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
                msg = json.dumps({"type": "break_database", "payload": {}})
                await handle_client_message(msg)

                mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_break_database_triggers_on_already_revoked(self):
        from websocket_server import handle_client_message, manager
        from botocore.exceptions import ClientError

        manager.active_connections = []

        with patch("shared.network_operations._get_ec2_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.revoke_security_group_ingress = MagicMock(
                side_effect=ClientError(
                    {"Error": {"Code": "InvalidPermission.NotFound", "Message": "not found"}},
                    "RevokeSecurityGroupIngress",
                )
            )
            mock_get_client.return_value = mock_client

            with patch("demo_controller.demo_controller.trigger_incident", new_callable=AsyncMock) as mock_trigger:
                msg = json.dumps({"type": "break_database", "payload": {}})
                await handle_client_message(msg)

                mock_trigger.assert_called_once_with("aurora-db")


class TestResetRestoresAccess:
    @pytest.mark.asyncio
    async def test_reset_demo_calls_restore_db_access(self):
        from websocket_server import handle_client_message, manager

        manager.active_connections = []
        demo_state.trigger_incident("aurora-db")

        with patch("shared.network_operations._get_ec2_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.authorize_security_group_ingress = MagicMock(return_value={})
            mock_get_client.return_value = mock_client

            with patch("demo_controller.demo_controller.cancel_simulation", new_callable=AsyncMock):
                with patch("voice.voice_router.voice_router.stop_session", new_callable=AsyncMock):
                    msg = json.dumps({"type": "reset_demo", "payload": {}})
                    await handle_client_message(msg)

                    mock_client.authorize_security_group_ingress.assert_called_once()


class TestVoiceToolRestoreConnectivity:
    @pytest.mark.asyncio
    async def test_apply_network_fix_calls_restore_db_access(self):
        from voice.voice_tools import execute_tool

        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.CALLING

        with patch("shared.network_operations._get_ec2_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.authorize_security_group_ingress = MagicMock(return_value={})
            mock_get_client.return_value = mock_client

            result = await execute_tool("apply_network_fix", {"service": "aurora-db"})

            assert result["status"] == "success"
            assert "fix applied" in result["message"].lower()
            assert demo_state.phase == Phase.RECOVERING
            mock_client.authorize_security_group_ingress.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_network_fix_works_even_if_aws_fails(self):
        from voice.voice_tools import execute_tool

        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.CALLING

        with patch("shared.network_operations._get_ec2_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.authorize_security_group_ingress = MagicMock(side_effect=Exception("network error"))
            mock_get_client.return_value = mock_client

            result = await execute_tool("apply_network_fix", {"service": "aurora-db"})

            assert result["status"] == "success"
            assert demo_state.phase == Phase.RECOVERING

    @pytest.mark.asyncio
    async def test_apply_network_fix_not_in_calling_phase(self):
        from voice.voice_tools import execute_tool

        demo_state.trigger_incident("aurora-db")
        demo_state.phase = Phase.DIAGNOSING

        with patch("shared.network_operations._get_ec2_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.authorize_security_group_ingress = MagicMock(return_value={})
            mock_get_client.return_value = mock_client

            result = await execute_tool("apply_network_fix", {"service": "aurora-db"})

            assert result["status"] == "success"
            assert demo_state.phase == Phase.DIAGNOSING
            mock_client.authorize_security_group_ingress.assert_called_once()


class TestIdempotency:
    """Verify that revoke/restore can be called multiple times without errors."""

    @pytest.mark.asyncio
    async def test_revoke_twice_is_idempotent(self):
        from botocore.exceptions import ClientError
        from shared.network_operations import revoke_db_access

        mock_client = MagicMock()
        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {}
            raise ClientError(
                {"Error": {"Code": "InvalidPermission.NotFound", "Message": "rule not found"}},
                "RevokeSecurityGroupIngress",
            )

        mock_client.revoke_security_group_ingress = MagicMock(side_effect=side_effect)

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            r1 = await revoke_db_access()
            r2 = await revoke_db_access()

        assert r1["status"] == "success"
        assert r2["status"] == "already_revoked"

    @pytest.mark.asyncio
    async def test_restore_twice_is_idempotent(self):
        from botocore.exceptions import ClientError
        from shared.network_operations import restore_db_access

        mock_client = MagicMock()
        call_count = [0]

        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {}
            raise ClientError(
                {"Error": {"Code": "InvalidPermission.Duplicate", "Message": "rule exists"}},
                "AuthorizeSecurityGroupIngress",
            )

        mock_client.authorize_security_group_ingress = MagicMock(side_effect=side_effect)

        with patch("shared.network_operations._get_ec2_client", return_value=mock_client):
            r1 = await restore_db_access()
            r2 = await restore_db_access()

        assert r1["status"] == "success"
        assert r2["status"] == "already_present"
