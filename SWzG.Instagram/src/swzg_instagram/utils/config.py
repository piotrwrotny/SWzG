from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # SWzG.Instagram/


@dataclass(frozen=True)
class Settings:
    instagram_username: str
    instagram_password: str
    session_file: Path
    min_delay: float
    max_delay: float
    log_level: str
    base_dir: Path

    @property
    def inputs_dir(self) -> Path:
        return self.base_dir / "lists" / "inputs"

    @property
    def outputs_dir(self) -> Path:
        return self.base_dir / "lists" / "outputs"

    @property
    def syslog_dir(self) -> Path:
        return self.base_dir / "log" / "syslog"

    @property
    def errors_dir(self) -> Path:
        return self.base_dir / "log" / "errors"

    @property
    def actions_dir(self) -> Path:
        return self.base_dir / "log" / "actions_steps"

    @property
    def state_dir(self) -> Path:
        return self.base_dir / "state"


def load_settings(base_dir: Path | None = None) -> Settings:
    bd = base_dir or BASE_DIR
    env_path = bd / ".env"
    load_dotenv(env_path)

    username = os.getenv("INSTAGRAM_USERNAME", "")
    password = os.getenv("INSTAGRAM_PASSWORD", "")
    session_file_str = os.getenv("INSTAGRAM_SESSION_FILE", str(bd / "state" / "session.json"))
    min_delay = float(os.getenv("ACTION_MIN_DELAY_SECONDS", "3"))
    max_delay = float(os.getenv("ACTION_MAX_DELAY_SECONDS", "7"))
    log_level = os.getenv("LOG_LEVEL", "INFO")

    if not username or not password:
        raise ValueError(
            "Brak danych logowania. Ustaw INSTAGRAM_USERNAME i INSTAGRAM_PASSWORD w pliku .env"
        )

    return Settings(
        instagram_username=username,
        instagram_password=password,
        session_file=Path(session_file_str),
        min_delay=min_delay,
        max_delay=max_delay,
        log_level=log_level,
        base_dir=bd,
    )
