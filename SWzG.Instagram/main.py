#!/usr/bin/env python3
"""SWzG Instagram — local cleanup tool entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure src/ is on the import path when running from SWzG.Instagram/
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from swzg_instagram.adapters.instagrapi_adapter import InstagrapiAdapter
from swzg_instagram.cli.menu import run_menu
from swzg_instagram.utils.config import load_settings
from swzg_instagram.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"[BŁĄD] {exc}")
        sys.exit(1)

    setup_logging(
        syslog_dir=settings.syslog_dir,
        errors_dir=settings.errors_dir,
        actions_dir=settings.actions_dir,
        log_level=settings.log_level,
    )

    logger.info("Starting SWzG Instagram cleanup tool")

    adapter = InstagrapiAdapter(
        username=settings.instagram_username,
        password=settings.instagram_password,
        session_file=settings.session_file,
    )

    print("\n  Logowanie do Instagram...")
    try:
        adapter.login()
        print("  Zalogowano pomyślnie.\n")
    except SystemExit as exc:
        print(f"\n  [BŁĄD] {exc}")
        sys.exit(1)
    except Exception as exc:
        logger.error("Login failed: %s", exc, exc_info=True)
        print(f"\n  [BŁĄD] Logowanie nie powiodło się: {exc}")
        sys.exit(1)

    try:
        run_menu(adapter, settings)
    except KeyboardInterrupt:
        print("\n\n  Przerwano przez użytkownika.")
    finally:
        logging.shutdown()


if __name__ == "__main__":
    main()
