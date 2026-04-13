from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from swzg_instagram.models.results import ActionStatus
from swzg_instagram.services.browser_unfollow import BrowserUnfollowService


class TestBrowserUnfollowPlan:
    def test_plan_reads_unfollow_targets(self, tmp_path: Path) -> None:
        (tmp_path / "unfollow_targets.txt").write_text("alice\nbob\n# comment\n")
        svc = BrowserUnfollowService(
            inputs_dir=tmp_path,
            state_dir=tmp_path / "state",
            instagram_username="testuser",
        )
        plan = svc.plan()
        assert plan == ["alice", "bob"]

    def test_plan_empty_file(self, tmp_path: Path) -> None:
        (tmp_path / "unfollow_targets.txt").write_text("")
        svc = BrowserUnfollowService(
            inputs_dir=tmp_path,
            state_dir=tmp_path / "state",
            instagram_username="testuser",
        )
        plan = svc.plan()
        assert plan == []

    def test_plan_no_file(self, tmp_path: Path) -> None:
        svc = BrowserUnfollowService(
            inputs_dir=tmp_path,
            state_dir=tmp_path / "state",
            instagram_username="testuser",
        )
        plan = svc.plan()
        assert plan == []

    def test_run_empty_targets_returns_empty(self, tmp_path: Path) -> None:
        svc = BrowserUnfollowService(
            inputs_dir=tmp_path,
            state_dir=tmp_path / "state",
            instagram_username="testuser",
        )
        results = svc.run([])
        assert results == []
