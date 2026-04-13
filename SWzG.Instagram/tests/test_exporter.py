import csv
from pathlib import Path

import pytest

from swzg_instagram.io.exporter import export_accounts
from swzg_instagram.models.account import AccountInfo, UNAVAILABLE


@pytest.fixture
def sample_accounts() -> list[AccountInfo]:
    return [
        AccountInfo(
            username="alice",
            full_name="Alice Smith",
            bio="Hello world",
            profile_url="https://www.instagram.com/alice/",
            has_chat_history=True,
            last_chat_date="2025-01-15T10:30:00+00:00",
            source_list="following",
        ),
        AccountInfo(
            username="bob",
            full_name=None,
            bio=None,
            has_chat_history=None,
            source_list="following",
        ),
    ]


class TestExportAccounts:
    def test_creates_four_files(self, tmp_path: Path, sample_accounts: list[AccountInfo]) -> None:
        paths = export_accounts(sample_accounts, tmp_path, "test_export")
        assert "csv" in paths
        assert "table" in paths
        assert "md" in paths
        assert "usernames" in paths
        assert paths["csv"].exists()
        assert paths["table"].exists()
        assert paths["md"].exists()
        assert paths["usernames"].exists()

    def test_csv_contents(self, tmp_path: Path, sample_accounts: list[AccountInfo]) -> None:
        paths = export_accounts(sample_accounts, tmp_path, "test_export")
        with paths["csv"].open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["username"] == "alice"
        assert rows[0]["full_name"] == "Alice Smith"
        assert rows[1]["full_name"] == UNAVAILABLE
        assert rows[1]["bio"] == UNAVAILABLE

    def test_usernames_only(self, tmp_path: Path, sample_accounts: list[AccountInfo]) -> None:
        paths = export_accounts(sample_accounts, tmp_path, "test_export")
        content = paths["usernames"].read_text(encoding="utf-8").strip()
        lines = content.split("\n")
        assert lines == ["alice", "bob"]

    def test_niedostepne_for_missing_values(self, tmp_path: Path) -> None:
        accounts = [AccountInfo(username="empty_user")]
        paths = export_accounts(accounts, tmp_path, "test_export")
        with paths["csv"].open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
        assert row["full_name"] == UNAVAILABLE
        assert row["bio"] == UNAVAILABLE
        assert row["has_chat_history"] == UNAVAILABLE
        assert row["last_chat_date"] == UNAVAILABLE
        assert row["source_list"] == UNAVAILABLE

    def test_table_file_is_readable(self, tmp_path: Path, sample_accounts: list[AccountInfo]) -> None:
        paths = export_accounts(sample_accounts, tmp_path, "test_export")
        content = paths["table"].read_text(encoding="utf-8")
        assert "alice" in content
        assert "bob" in content
        # Verify Polish header presence
        assert "Nazwa użytkownika" in content

    def test_md_file_is_valid_markdown(self, tmp_path: Path, sample_accounts: list[AccountInfo]) -> None:
        paths = export_accounts(sample_accounts, tmp_path, "test_export")
        content = paths["md"].read_text(encoding="utf-8")
        assert paths["md"].suffix == ".md"
        assert "alice" in content
        assert "Nazwa użytkownika" in content
        # GitHub-flavored markdown uses pipes
        assert "|" in content
