from __future__ import annotations

import logging
from pathlib import Path

from swzg_instagram.adapters.base import InstagramAdapter
from swzg_instagram.io.exporter import export_accounts
from swzg_instagram.io.parser import parse_username_file
from swzg_instagram.models.account import AccountInfo
from swzg_instagram.utils.delay import random_delay

logger = logging.getLogger(__name__)
actions_logger = logging.getLogger("actions")


class ExportService:
    def __init__(
        self,
        adapter: InstagramAdapter,
        outputs_dir: Path,
        min_delay: float = 3.0,
        max_delay: float = 7.0,
    ) -> None:
        self._adapter = adapter
        self._outputs_dir = outputs_dir
        self._min_delay = min_delay
        self._max_delay = max_delay

    def export_following(self) -> dict[str, Path]:
        logger.info("Exporting following list")
        actions_logger.info("operation=export_following step=start")
        accounts = self._adapter.get_following()
        actions_logger.info(
            "operation=export_following step=fetched count=%d", len(accounts)
        )
        paths = export_accounts(accounts, self._outputs_dir, "obserwowani")
        actions_logger.info(
            "operation=export_following step=exported csv=%s", paths["csv"]
        )
        return paths

    def export_followers(self) -> dict[str, Path]:
        logger.info("Exporting followers list")
        actions_logger.info("operation=export_followers step=start")
        accounts = self._adapter.get_followers()
        actions_logger.info(
            "operation=export_followers step=fetched count=%d", len(accounts)
        )
        paths = export_accounts(accounts, self._outputs_dir, "obserwujacy")
        actions_logger.info(
            "operation=export_followers step=exported csv=%s", paths["csv"]
        )
        return paths

    def export_dm_contacts(self) -> dict[str, Path]:
        logger.info("Exporting DM contacts")
        actions_logger.info("operation=export_dm_contacts step=start")
        accounts = self._adapter.get_dm_contacts()
        actions_logger.info(
            "operation=export_dm_contacts step=fetched count=%d", len(accounts)
        )
        paths = export_accounts(accounts, self._outputs_dir, "kontakty_dm")
        actions_logger.info(
            "operation=export_dm_contacts step=exported csv=%s", paths["csv"]
        )
        return paths

    def export_from_file(self, input_file: Path) -> dict[str, Path]:
        logger.info("Exporting accounts from file: %s", input_file.name)
        actions_logger.info(
            "operation=export_from_file step=start file=%s", input_file.name
        )
        usernames = parse_username_file(input_file)
        if not usernames:
            logger.warning("No usernames found in %s", input_file.name)
            return {}

        accounts: list[AccountInfo] = []
        for i, username in enumerate(usernames, 1):
            logger.info("Enriching %d/%d: %s", i, len(usernames), username)
            actions_logger.info(
                "operation=export_from_file step=enrich username=%s index=%d/%d",
                username, i, len(usernames),
            )
            account = self._adapter.enrich_account(username)
            account.source_list = input_file.stem
            accounts.append(account)
            if i < len(usernames):
                random_delay(self._min_delay, self._max_delay)

        prefix = f"lista_{input_file.stem}"
        paths = export_accounts(accounts, self._outputs_dir, prefix)
        actions_logger.info(
            "operation=export_from_file step=exported csv=%s", paths["csv"]
        )
        return paths
