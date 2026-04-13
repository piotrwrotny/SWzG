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
        total = len(usernames)
        actions_logger.info("=" * 60)
        actions_logger.info(
            "AKCJA: PRZESTAŃ OBSERWOWAĆ — %d kont do przetworzenia", total
        )
        actions_logger.info("=" * 60)

        # Pre-build username→user_id map from following list (1 bulk request)
        actions_logger.info("Pobieram listę obserwowanych aby uniknąć pojedynczych zapytań...")
        pk_map: dict[str, str] = {}
        try:
            following = self._adapter.get_following()
            pk_map = {
                a.username.lower(): a.user_id
                for a in following
                if a.username and a.user_id
            }
            actions_logger.info(
                "Mapa obserwowanych gotowa: %d kont", len(pk_map)
            )
        except Exception as exc:
            actions_logger.warning(
                "Nie udało się pobrać listy obserwowanych — będę szukać po nazwie: %s",
                exc,
            )

        rate_limit_consecutive = 0
        RATE_LIMIT_PAUSE = 120  # seconds
        RATE_LIMIT_MAX = 3  # stop after N consecutive rate limits

        for i, username in enumerate(usernames, 1):
            actions_logger.info(
                "[%d/%d] Usuwam obserwowanie: @%s", i, total, username,
            )
            try:
                uid = pk_map.get(username.lower())
                if uid:
                    ok = self._adapter.unfollow_by_user_id(uid)
                else:
                    actions_logger.info(
                        "[%d/%d] @%s nie znaleziony w mapie — szukam po nazwie",
                        i, total, username,
                    )
                    ok = self._adapter.unfollow(username)

                status = ActionStatus.SUCCESS if ok else ActionStatus.FAILED
                msg = "Usunięto obserwowanie" if ok else "Nie udało się usunąć obserwowania"
                results.append(ActionResult(username=username, status=status, message=msg, step="unfollow"))
                if ok:
                    actions_logger.info(
                        "[%d/%d] OK — usunięto obserwowanie @%s", i, total, username
                    )
                    rate_limit_consecutive = 0
                else:
                    actions_logger.warning(
                        "[%d/%d] NIEPOWODZENIE — nie udało się usunąć obserwowania @%s",
                        i, total, username,
                    )
            except Exception as exc:
                exc_str = str(exc).lower()
                is_rate_limit = (
                    "please wait" in exc_str
                    or "feedback_required" in exc_str
                    or "429" in exc_str
                    or "too many" in exc_str
                )
                if is_rate_limit:
                    rate_limit_consecutive += 1
                    actions_logger.warning(
                        "[%d/%d] RATE LIMIT @%s (próba %d/%d) — czekam %ds...",
                        i, total, username,
                        rate_limit_consecutive, RATE_LIMIT_MAX, RATE_LIMIT_PAUSE,
                    )
                    if rate_limit_consecutive >= RATE_LIMIT_MAX:
                        actions_logger.error(
                            "Zbyt wiele rate limitów z rzędu (%d) — przerywam.",
                            RATE_LIMIT_MAX,
                        )
                        results.append(ActionResult(
                            username=username, status=ActionStatus.FAILED,
                            message="Rate limit — przerwano", step="unfollow",
                        ))
                        break
                    try:
                        print(
                            f"\n  ⏳ Rate limit — czekam {RATE_LIMIT_PAUSE}s"
                            f" (Ctrl+C aby przerwać)..."
                        )
                        time.sleep(RATE_LIMIT_PAUSE)
                    except KeyboardInterrupt:
                        actions_logger.info("Przerwano przez użytkownika podczas oczekiwania")
                        results.append(ActionResult(
                            username=username, status=ActionStatus.FAILED,
                            message="Przerwano", step="unfollow",
                        ))
                        break
                    # Retry the same account after pause
                    results.append(ActionResult(
                        username=username, status=ActionStatus.FAILED,
                        message=f"Rate limit — pomijam", step="unfollow",
                    ))
                else:
                    logger.error("Unfollow failed for %s: %s", username, exc)
                    actions_logger.error(
                        "[%d/%d] BŁĄD @%s: %s", i, total, username, exc
                    )
                    results.append(ActionResult(
                        username=username, status=ActionStatus.FAILED,
                        message=str(exc), step="unfollow",
                    ))

            if i < total:
                random_delay(self._min_delay, self._max_delay)

        ok_count = sum(1 for r in results if r.status == ActionStatus.SUCCESS)
        actions_logger.info("=" * 60)
        actions_logger.info(
            "ZAKOŃCZONO: %d/%d pomyślnie usunięto obserwowanie", ok_count, total,
        )
        actions_logger.info("=" * 60)
        return results

    def execute_softblock(self, usernames: list[str]) -> list[ActionResult]:
        results: list[ActionResult] = []
        total = len(usernames)
        actions_logger.info("=" * 60)
        actions_logger.info(
            "AKCJA: SOFTBLOCK — %d kont do przetworzenia", total
        )
        actions_logger.info(
            "Etapy na konto: 1) Zablokuj → 2) Odczekaj → 3) Odblokuj"
        )
        actions_logger.info("=" * 60)

        for i, username in enumerate(usernames, 1):
            actions_logger.info(
                "[%d/%d] Rozpoczynam softblock: @%s", i, total, username,
            )
            try:
                # Step 1: Block
                actions_logger.info(
                    "[%d/%d] Krok 1/2: Blokuję @%s...", i, total, username
                )
                blocked = self._adapter.block(username)
                if not blocked:
                    results.append(ActionResult(
                        username=username, status=ActionStatus.FAILED,
                        message="Nie udało się zablokować", step="block",
                    ))
                    actions_logger.warning(
                        "[%d/%d] NIEPOWODZENIE — nie udało się zablokować @%s",
                        i, total, username,
                    )
                    continue

                actions_logger.info(
                    "[%d/%d] Krok 1/2 OK: @%s zablokowany, czekam przed odblokowaniem...",
                    i, total, username,
                )
                random_delay(self._min_delay, self._max_delay)

                # Step 2: Unblock
                actions_logger.info(
                    "[%d/%d] Krok 2/2: Odblokowuję @%s...", i, total, username
                )
                unblocked = self._adapter.unblock(username)
                if not unblocked:
                    results.append(ActionResult(
                        username=username, status=ActionStatus.PARTIAL,
                        message="Zablokowano, ale nie udało się odblokować", step="unblock",
                    ))
                    actions_logger.warning(
                        "[%d/%d] CZĘŚCIOWO — @%s zablokowany, ale odblokowanie nie powiodło się!",
                        i, total, username,
                    )
                    continue

                results.append(ActionResult(
                    username=username, status=ActionStatus.SUCCESS,
                    message="Softblock wykonany", step="softblock",
                ))
                actions_logger.info(
                    "[%d/%d] OK — softblock @%s zakończony (zablokowano → odblokowano)",
                    i, total, username,
                )

            except Exception as exc:
                logger.error("Softblock failed for %s: %s", username, exc)
                actions_logger.error(
                    "[%d/%d] BŁĄD @%s: %s", i, total, username, exc
                )
                results.append(ActionResult(
                    username=username, status=ActionStatus.FAILED,
                    message=str(exc), step="softblock",
                ))

            if i < total:
                random_delay(self._min_delay, self._max_delay)

        ok_count = sum(1 for r in results if r.status == ActionStatus.SUCCESS)
        actions_logger.info("=" * 60)
        actions_logger.info(
            "ZAKOŃCZONO SOFTBLOCK: %d/%d pomyślnie", ok_count, total,
        )
        actions_logger.info("=" * 60)
        return results

    def execute_delete_chats(self, usernames: list[str]) -> list[ActionResult]:
        results: list[ActionResult] = []
        total = len(usernames)
        actions_logger.info("=" * 60)
        actions_logger.info(
            "AKCJA: USUWANIE CZATÓW — %d kont do przetworzenia", total
        )
        actions_logger.info("=" * 60)

        for i, username in enumerate(usernames, 1):
            actions_logger.info(
                "[%d/%d] Usuwam czat z: @%s", i, total, username,
            )
            try:
                ok = self._adapter.delete_chat(username)
                status = ActionStatus.SUCCESS if ok else ActionStatus.FAILED
                msg = "Czat usunięty" if ok else "Nie znaleziono czatu"
                results.append(ActionResult(username=username, status=status, message=msg, step="delete_chat"))
                if ok:
                    actions_logger.info(
                        "[%d/%d] OK — czat z @%s usunięty (ukryty)", i, total, username
                    )
                else:
                    actions_logger.warning(
                        "[%d/%d] POMINIĘTO — nie znaleziono wątku czatu z @%s",
                        i, total, username,
                    )
            except CapabilityError as exc:
                logger.error(
                    "Trwałe usunięcie czatu niedostępne dla %s: %s", username, exc
                )
                actions_logger.error(
                    "[%d/%d] BŁĄD MOŻLIWOŚCI — trwałe usunięcie czatu z @%s niedostępne: %s",
                    i, total, username, exc,
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
                    "[%d/%d] BŁĄD @%s: %s", i, total, username, exc
                )
                results.append(ActionResult(
                    username=username, status=ActionStatus.FAILED,
                    message=str(exc), step="delete_chat",
                ))

            if i < total:
                random_delay(self._min_delay, self._max_delay)

        ok_count = sum(1 for r in results if r.status == ActionStatus.SUCCESS)
        actions_logger.info("=" * 60)
        actions_logger.info(
            "ZAKOŃCZONO USUWANIE CZATÓW: %d/%d pomyślnie", ok_count, total,
        )
        actions_logger.info("=" * 60)
        return results
