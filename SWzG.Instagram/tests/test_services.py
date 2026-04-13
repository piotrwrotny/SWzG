from pathlib import Path
from unittest.mock import MagicMock

import pytest

from swzg_instagram.models.account import AccountInfo
from swzg_instagram.models.results import ActionResult, ActionStatus
from swzg_instagram.services.action_service import ActionService
from swzg_instagram.services.export_service import ExportService


@pytest.fixture
def mock_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.get_following.return_value = [
        AccountInfo(username="alice", full_name="Alice", user_id="1", source_list="following"),
        AccountInfo(username="bob", user_id="2", source_list="following"),
    ]
    adapter.get_followers.return_value = [
        AccountInfo(username="charlie", user_id="3", source_list="followers"),
    ]
    adapter.get_dm_contacts.return_value = [
        AccountInfo(username="dave", has_chat_history=True, source_list="dm_contacts"),
    ]
    adapter.enrich_account.side_effect = lambda u: AccountInfo(username=u, source_list="input_list")
    adapter.enrich_by_user_id.side_effect = lambda uid: AccountInfo(
        username=f"user_{uid}", bio="test bio", user_id=uid, source_list="enriched",
    )
    adapter.build_dm_index.return_value = {}
    adapter.check_session.return_value = True
    adapter.unfollow.return_value = True
    adapter.unfollow_by_user_id.return_value = True
    adapter.block.return_value = True
    adapter.unblock.return_value = True
    adapter.delete_chat.return_value = True
    return adapter


class TestExportService:
    def test_export_following(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        svc = ExportService(adapter=mock_adapter, outputs_dir=tmp_path, state_dir=tmp_path / "state", min_delay=0, max_delay=0)
        paths = svc.export_following()
        assert paths["csv"].exists()
        mock_adapter.get_following.assert_called_once()
        # Should enrich each account by user_id
        assert mock_adapter.enrich_by_user_id.call_count == 2

    def test_export_following_no_enrich(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        svc = ExportService(adapter=mock_adapter, outputs_dir=tmp_path, min_delay=0, max_delay=0)
        paths = svc.export_following(enrich=False)
        assert paths["csv"].exists()
        mock_adapter.enrich_by_user_id.assert_not_called()

    def test_export_followers(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        svc = ExportService(adapter=mock_adapter, outputs_dir=tmp_path, state_dir=tmp_path / "state", min_delay=0, max_delay=0)
        paths = svc.export_followers()
        assert paths["csv"].exists()
        mock_adapter.get_followers.assert_called_once()
        assert mock_adapter.enrich_by_user_id.call_count == 1

    def test_export_dm_contacts(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        svc = ExportService(adapter=mock_adapter, outputs_dir=tmp_path, min_delay=0, max_delay=0)
        paths = svc.export_dm_contacts()
        assert paths["csv"].exists()
        mock_adapter.get_dm_contacts.assert_called_once()

    def test_export_from_file(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        input_file = tmp_path / "test_list.txt"
        input_file.write_text("alice\nbob\n")
        svc = ExportService(adapter=mock_adapter, outputs_dir=tmp_path, min_delay=0, max_delay=0)
        paths = svc.export_from_file(input_file)
        assert paths["csv"].exists()
        assert mock_adapter.enrich_account.call_count == 2

    def test_export_from_empty_file(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        input_file = tmp_path / "empty.txt"
        input_file.write_text("")
        svc = ExportService(adapter=mock_adapter, outputs_dir=tmp_path, min_delay=0, max_delay=0)
        paths = svc.export_from_file(input_file)
        assert paths == {}

    def test_checkpoint_resume(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        """Enrichment resumes from checkpoint after crash."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Simulate a checkpoint where first account was already enriched
        import json
        cp_data = {
            "done": 1,
            "accounts": [
                {"username": "alice", "full_name": "Alice", "bio": "saved bio",
                 "profile_url": "https://www.instagram.com/alice/",
                 "user_id": "1", "source_list": "following"},
            ],
        }
        (state_dir / "checkpoint_obserwowani.json").write_text(
            json.dumps(cp_data), encoding="utf-8",
        )

        svc = ExportService(
            adapter=mock_adapter, outputs_dir=tmp_path,
            state_dir=state_dir, min_delay=0, max_delay=0,
        )
        paths = svc.export_following()
        assert paths["csv"].exists()
        # Only bob (2nd account) should be enriched — alice was in checkpoint
        assert mock_adapter.enrich_by_user_id.call_count == 1
        # Checkpoint should be cleaned up
        assert not (state_dir / "checkpoint_obserwowani.json").exists()


class TestActionService:
    def test_plan_unfollow(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        (tmp_path / "unfollow_targets.txt").write_text("alice\nbob\n")
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        plan = svc.plan_unfollow()
        assert plan == ["alice", "bob"]

    def test_plan_softblock(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        (tmp_path / "softblock_targets.txt").write_text("charlie\n")
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        plan = svc.plan_softblock()
        assert plan == ["charlie"]

    def test_plan_delete_chats(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        (tmp_path / "delete_chat_targets.txt").write_text("dave\n")
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        plan = svc.plan_delete_chats()
        assert plan == ["dave"]

    def test_execute_unfollow_success(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        results = svc.execute_unfollow(["alice", "bob"])
        assert len(results) == 2
        assert all(r.status == ActionStatus.SUCCESS for r in results)

    def test_execute_unfollow_partial_failure(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        mock_adapter.unfollow_by_user_id.side_effect = [True, False]
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        results = svc.execute_unfollow(["alice", "bob"])
        assert results[0].status == ActionStatus.SUCCESS
        assert results[1].status == ActionStatus.FAILED

    def test_execute_softblock_success(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        results = svc.execute_softblock(["alice"])
        assert len(results) == 1
        assert results[0].status == ActionStatus.SUCCESS

    def test_execute_softblock_block_fails(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        mock_adapter.block.return_value = False
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        results = svc.execute_softblock(["alice"])
        assert results[0].status == ActionStatus.FAILED

    def test_execute_softblock_unblock_fails(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        mock_adapter.unblock.return_value = False
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        results = svc.execute_softblock(["alice"])
        assert results[0].status == ActionStatus.PARTIAL

    def test_execute_delete_chats_success(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        results = svc.execute_delete_chats(["alice"])
        assert results[0].status == ActionStatus.SUCCESS

    def test_execute_unfollow_exception_continues(self, tmp_path: Path, mock_adapter: MagicMock) -> None:
        mock_adapter.unfollow_by_user_id.side_effect = [Exception("network error"), True]
        svc = ActionService(adapter=mock_adapter, inputs_dir=tmp_path, min_delay=0, max_delay=0)
        results = svc.execute_unfollow(["alice", "bob"])
        assert len(results) == 2
        assert results[0].status == ActionStatus.FAILED
        assert results[1].status == ActionStatus.SUCCESS
