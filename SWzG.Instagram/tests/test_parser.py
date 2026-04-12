from pathlib import Path

import pytest

from swzg_instagram.io.parser import parse_username_file


@pytest.fixture
def tmp_input_file(tmp_path: Path) -> Path:
    return tmp_path / "test_input.txt"


class TestParseUsernameFile:
    def test_empty_file(self, tmp_input_file: Path) -> None:
        tmp_input_file.write_text("")
        assert parse_username_file(tmp_input_file) == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert parse_username_file(tmp_path / "missing.txt") == []

    def test_basic_usernames(self, tmp_input_file: Path) -> None:
        tmp_input_file.write_text("alice\nbob\ncharlie\n")
        result = parse_username_file(tmp_input_file)
        assert result == ["alice", "bob", "charlie"]

    def test_strips_at_prefix(self, tmp_input_file: Path) -> None:
        tmp_input_file.write_text("@alice\n@bob\n")
        result = parse_username_file(tmp_input_file)
        assert result == ["alice", "bob"]

    def test_ignores_comments(self, tmp_input_file: Path) -> None:
        tmp_input_file.write_text("# comment\nalice\n# another\nbob\n")
        result = parse_username_file(tmp_input_file)
        assert result == ["alice", "bob"]

    def test_ignores_blank_lines(self, tmp_input_file: Path) -> None:
        tmp_input_file.write_text("alice\n\n\nbob\n   \ncharlie\n")
        result = parse_username_file(tmp_input_file)
        assert result == ["alice", "bob", "charlie"]

    def test_trims_whitespace(self, tmp_input_file: Path) -> None:
        tmp_input_file.write_text("  alice  \n  @ bob  \n")
        result = parse_username_file(tmp_input_file)
        assert result == ["alice", "bob"]

    def test_deduplication_preserves_order(self, tmp_input_file: Path) -> None:
        tmp_input_file.write_text("alice\nbob\nAlice\ncharlie\nBOB\n")
        result = parse_username_file(tmp_input_file)
        assert result == ["alice", "bob", "charlie"]

    def test_mixed_at_and_no_at(self, tmp_input_file: Path) -> None:
        tmp_input_file.write_text("@alice\nalice\n")
        result = parse_username_file(tmp_input_file)
        assert result == ["alice"]
