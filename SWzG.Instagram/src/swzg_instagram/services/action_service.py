from __future__ import annotations

import logging
import time
from pathlib import Path

from swzg_instagram.adapters.base import InstagramAdapter
from swzg_instagram.adapters.instagrapi_adapter import CapabilityError
from swzg_instagram.io.parser import parse_username_file
from swzg_instagram.models.results import ActionResult, ActionStatus
from swzg_instagram.utils.delay import random_delay

logger = logging.getLogger(__name__)
actions_logger = logging.getLogger("actions")

CHAT_DELETE_ERROR_PAUSE = 10


class ActionService:
    def __init__(
        self,
        adapter: InstagramAdapter,
        inputs_dir: Path,
        min_delay: float = 3.0,
        max_delay: float = 7.0,
    ) -> None:
        self._adapter = adapter
        self._inputs_dir = inputs_dir
        self._min_delay = min_delay
        self._max_delay = max_delay

    # --- Planning / Preview ---

    def plan_unfollow(self) -> list[str]:
        return parse_username_file(self._inputs_dir / "unfollow_targets.txt")

    def plan_softblock(self) -> list[str]:
        return parse_username_file(self._inputs_dir / "softblock_targets.txt")

    def plan_delete_chats(self) -> list[str]:
        return parse_username_file(self._inputs_dir / "delete_chat_targets.txt")

    # --- Execution ---

    def execute_unfollow(self, usernames: list[str]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for i, username in enumerate(usernames, 1):
            actions_logger.info(
                "operation=unfollow step=start username=%s index=%d/%d",
                username, i, len(usernames),
            )
            try:
                ok = self._adapter.unfollow(username)
                status = ActionStatus.SUCCESS if ok else ActionStatus.FAILED
                msg = "Usunięto obserwowanie" if ok else "Nie udało się usunąć obserwowania"
                results.append(ActionResult(username=username, status=status, message=msg, step="unfollow"))
                actions_logger.info(
                    "operation=unfollow step=done username=%s result=%s", username, status.value
                )
            except Exception as exc:
                logger.error("Unfollow failed for %s: %s", username, exc)
                actions_logger.error(
                    "operation=unfollow step=error username=%s error=%s", username, exc
                )
                results.append(ActionResult(
                    username=username, status=ActionStatus.FAILED,
                    message=str(exc), step="unfollow",
                ))

            if i < len(usernames):
                random_delay(self._min_delay, self._max_delay)

        return results

    def execute_softblock(self, usernames: list[str]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for i, username in enumerate(usernames, 1):
            actions_logger.info(
                "operation=softblock step=start username=%s index=%d/%d",
                username, i, len(usernames),
            )
            try:
                # Step 1: Block
                actions_logger.info("operation=softblock step=block username=%s", username)
                blocked = self._adapter.block(username)
                if not blocked:
                    results.append(ActionResult(
                        username=username, status=ActionStatus.FAILED,
                        message="Nie udało się zablokować", step="block",
                    ))
                    actions_logger.warning(
                        "operation=softblock step=block_failed username=%s", username
                    )
                    continue

                random_delay(self._min_delay, self._max_delay)

                # Step 2: Unblock
                actions_logger.info("operation=softblock step=unblock username=%s", username)
                unblocked = self._adapter.unblock(username)
                if not unblocked:
                    results.append(ActionResult(
                        username=username, status=ActionStatus.PARTIAL,
                        message="Zablokowano, ale nie udało się odblokować", step="unblock",
                    ))
                    actions_logger.warning(
                        "operation=softblock step=unblock_failed username=%s", username
                    )
                    continue

                results.append(ActionResult(
                    username=username, status=ActionStatus.SUCCESS,
                    message="Softblock wykonany", step="softblock",
                ))
                actions_logger.info(
                    "operation=softblock step=done username=%s result=success", username
                )

            except Exception as exc:
                logger.error("Softblock failed for %s: %s", username, exc)
                actions_logger.error(
                    "operation=softblock step=error username=%s error=%s", username, exc
                )
                results.append(ActionResult(
                    username=username, status=ActionStatus.FAILED,
                    message=str(exc), step="softblock",
                ))

            if i < len(usernames):
                random_delay(self._min_delay, self._max_delay)

        return results

    def execute_delete_chats(self, usernames: list[str]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for i, username in enumerate(usernames, 1):
            actions_logger.info(
                "operation=delete_chat step=start username=%s index=%d/%d",
                username, i, len(usernames),
            )
            try:
                ok = self._adapter.delete_chat(username)
                status = ActionStatus.SUCCESS if ok else ActionStatus.FAILED
                msg = "Czat usunięty" if ok else "Nie znaleziono czatu"
                results.append(ActionResult(username=username, status=status, message=msg, step="delete_chat"))
                actions_logger.info(
                    "operation=delete_chat step=done username=%s result=%s", username, status.value
                )
            except CapabilityError as exc:
                logger.error(
                    "Trwałe usunięcie czatu niedostępne dla %s: %s", username, exc
                )
                actions_logger.error(
                    "operation=delete_chat step=capability_error username=%s error=%s",
                    username, exc,
                )
                results.append(ActionResult(
                    username=username, status=ActionStatus.FAILED,
                    message=str(exc), step="delete_chat",
                ))
                print(
                    f"\n  [BŁĄD] Trwałe usunięcie czatu niedostępne dla {username}."
                    f"\n  Oczekiwanie {CHAT_DELETE_ERROR_PAUSE}s — naciśnij Ctrl+C aby przerwać..."
                )
                try:
                    time.sleep(CHAT_DELETE_ERROR_PAUSE)
                except KeyboardInterrupt:
                    print("\n  Przerwano przez użytkownika.")
                    break
            except Exception as exc:
                logger.error("Delete chat failed for %s: %s", username, exc)
                actions_logger.error(
                    "operation=delete_chat step=error username=%s error=%s", username, exc
                )
                results.append(ActionResult(
                    username=username, status=ActionStatus.FAILED,
                    message=str(exc), step="delete_chat",
                ))

            if i < len(usernames):
                random_delay(self._min_delay, self._max_delay)

        return results
