from pathlib import Path

import pytest

from swzg_instagram.utils.config import Settings, load_settings


class TestSettings:
    def test_settings_properties(self, tmp_path: Path) -> None:
        s = Settings(
            instagram_username="user",
            instagram_password="pass",
            session_file=tmp_path / "session.json",
            min_delay=1.0,
            max_delay=3.0,
            log_level="INFO",
            base_dir=tmp_path,
        )
        assert s.inputs_dir == tmp_path / "lists" / "inputs"
        assert s.outputs_dir == tmp_path / "lists" / "outputs"
        assert s.syslog_dir == tmp_path / "log" / "syslog"
        assert s.errors_dir == tmp_path / "log" / "errors"
        assert s.actions_dir == tmp_path / "log" / "actions_steps"
        assert s.state_dir == tmp_path / "state"

    def test_load_settings_missing_credentials(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("")
        with pytest.raises(ValueError, match="Brak danych logowania"):
            load_settings(tmp_path)

    def test_load_settings_with_credentials(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "INSTAGRAM_USERNAME=testuser\nINSTAGRAM_PASSWORD=testpass\n"
        )
        settings = load_settings(tmp_path)
        assert settings.instagram_username == "testuser"
        assert settings.instagram_password == "testpass"
