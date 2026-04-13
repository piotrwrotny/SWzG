from __future__ import annotations

import json
import logging
from pathlib import Path

from swzg_instagram.adapters.base import InstagramAdapter
from swzg_instagram.io.exporter import export_accounts
from swzg_instagram.io.parser import parse_username_file
from swzg_instagram.models.account import AccountInfo
from swzg_instagram.utils.delay import random_delay

logger = logging.getLogger(__name__)
actions_logger = logging.getLogger("actions")

CHECKPOINT_INTERVAL = 25


class ExportService:
    def __init__(
        self,
        adapter: InstagramAdapter,
        outputs_dir: Path,
        state_dir: Path | None = None,
        min_delay: float = 3.0,
        max_delay: float = 7.0,
    ) -> None:
        self._adapter = adapter
        self._outputs_dir = outputs_dir
        self._state_dir = state_dir
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._dm_index: dict[str, AccountInfo] | None = None

    # ── checkpoint helpers ──────────────────────────────────────────

    def _checkpoint_path(self, tag: str) -> Path | None:
        if not self._state_dir:
            return None
        self._state_dir.mkdir(parents=True, exist_ok=True)
        return self._state_dir / f"checkpoint_{tag}.json"

    @staticmethod
    def _save_checkpoint(path: Path, accounts: list[AccountInfo], done: int) -> None:
        data = {
            "done": done,
            "accounts": [a.to_checkpoint_dict() for a in accounts],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    @staticmethod
    def _load_checkpoint(path: Path) -> tuple[int, list[AccountInfo]]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        accounts = [AccountInfo.from_checkpoint_dict(d) for d in raw["accounts"]]
        return raw["done"], accounts

    def _clear_checkpoint(self, tag: str) -> None:
        cp = self._checkpoint_path(tag)
        if cp and cp.exists():
            cp.unlink()

    # ── enrichment ──────────────────────────────────────────────────

    def _enrich_accounts(
        self,
        accounts: list[AccountInfo],
        source: str,
        checkpoint_tag: str = "",
    ) -> list[AccountInfo]:
        total = len(accounts)
        enriched: list[AccountInfo] = []
        failed = 0
        session_checks = 0
        start_from = 0

        # ── try to resume from checkpoint ──
        cp = self._checkpoint_path(checkpoint_tag) if checkpoint_tag else None
        if cp and cp.exists():
            try:
                start_from, enriched = self._load_checkpoint(cp)
                print(
                    f"\n  ✓ Znaleziono checkpoint — wznawiam od pozycji"
                    f" {start_from + 1}/{total}"
                    f" ({start_from} już wzbogaconych)"
                )
                actions_logger.info(
                    "WZNOWIENIE z checkpointu: %d/%d już gotowych", start_from, total,
                )
            except Exception as exc:
                logger.warning("Checkpoint uszkodzony, zaczynam od nowa: %s", exc)
                start_from = 0
                enriched = []

        actions_logger.info("=" * 60)
        actions_logger.info(
            "WZBOGACANIE PROFILI — źródło: %s, liczba kont: %d (start=%d)",
            source, total, start_from,
        )
        actions_logger.info(
            "Pobieranie pełnych danych profilu (bio, imię) dla każdego konta"
        )
        actions_logger.info("=" * 60)

        for i in range(start_from, total):
            account = accounts[i]
            pos = i + 1  # human-readable 1-based

            if account.user_id:
                # Check session every 100 accounts
                if session_checks % 100 == 0 and session_checks > 0:
                    actions_logger.info(
                        "--- Sprawdzanie sesji (co 100 kont, pozycja %d/%d) ---",
                        pos, total,
                    )
                    if not self._adapter.check_session():
                        logger.warning(
                            "Session expired during enrichment at %d/%d", pos, total,
                        )
                        actions_logger.warning(
                            "SESJA WYGASŁA na pozycji %d/%d — proszę o nowe sessionid",
                            pos, total,
                        )
                        self._adapter.request_new_session()
                        actions_logger.info("Nowa sesja uzyskana — kontynuuję wzbogacanie")
                session_checks += 1

                actions_logger.info(
                    "[%d/%d] Pobieram profil: @%s (user_id=%s)",
                    pos, total, account.username, account.user_id,
                )
                detail = self._adapter.enrich_by_user_id(account.user_id)
                if detail:
                    detail.source_list = source
                    detail.user_id = account.user_id
                    account = detail
                    actions_logger.info(
                        "[%d/%d] OK @%s → imię='%s', bio='%s' (%d zn.)",
                        pos, total,
                        account.username,
                        account.full_name or "(brak)",
                        (account.bio[:60] + "...") if account.bio and len(account.bio) > 60
                        else (account.bio or "(brak)"),
                        len(account.bio) if account.bio else 0,
                    )
                else:
                    failed += 1
                    actions_logger.warning(
                        "[%d/%d] BŁĄD @%s (user_id=%s) — nie udało się pobrać profilu",
                        pos, total, account.username, account.user_id,
                    )

                if pos < total:
                    random_delay(self._min_delay, self._max_delay)

            account.source_list = source
            enriched.append(account)

            # ── periodic checkpoint + progress ──
            if pos % CHECKPOINT_INTERVAL == 0:
                if cp:
                    self._save_checkpoint(cp, enriched, pos)
                actions_logger.info(
                    "--- POSTĘP: %d/%d gotowych, %d błędów (checkpoint zapisany) ---",
                    pos, total, failed,
                )
                print(f"  Postęp: {pos}/{total} (błędów: {failed})")

        # ── done — clean up checkpoint ──
        if cp and cp.exists():
            cp.unlink()

        actions_logger.info("=" * 60)
        actions_logger.info(
            "WZBOGACANIE ZAKOŃCZONE: %d/%d pomyślnie, %d błędów",
            total - failed, total, failed,
        )
        actions_logger.info("=" * 60)
        logger.info(
            "Wzbogacanie zakończone: %d/%d pomyślnie, %d błędów",
            total - failed, total, failed,
        )
        return enriched

    def export_following(self, enrich: bool = True, limit: int = 0) -> dict[str, Path]:
        actions_logger.info("=" * 60)
        actions_logger.info("EKSPORT OBSERWOWANYCH — rozpoczęto%s",
                           f" (PRÓBNIE, limit={limit})" if limit else "")
        actions_logger.info("Krok 1: Pobieranie listy obserwowanych z API Instagram")
        accounts = self._adapter.get_following()
        actions_logger.info(
            "Krok 1 zakończony: pobrano %d obserwowanych kont", len(accounts)
        )

        if limit:
            accounts = accounts[:limit]
            actions_logger.info(
                "Tryb próbny: ograniczono do %d kont", len(accounts)
            )
            print(f"  Tryb próbny — wybranych {len(accounts)} z pełnej listy.")

        tag = "obserwowani_probne" if limit else "obserwowani"

        if enrich:
            print(f"\n  Pobrano {len(accounts)} obserwowanych. Rozpoczynam wzbogacanie profili...")
            print("  (pobieranie bio — to może potrwać długo)\n")
            actions_logger.info(
                "Krok 2: Wzbogacanie profili — pobieranie bio"
            )
            accounts = self._enrich_accounts(accounts, source="following",
                                              checkpoint_tag=tag)
            actions_logger.info(
                "Krok 2 zakończony: wzbogacono %d kont", len(accounts)
            )

        actions_logger.info("Krok 3: Zapisywanie plików eksportu")
        paths = export_accounts(accounts, self._outputs_dir, tag)
        actions_logger.info(
            "Krok 3 zakończony. Pliki:\n  CSV: %s\n  Tabela: %s\n  Nazwy: %s",
            paths.get("csv", "?"), paths.get("table", "?"), paths.get("usernames", "?"),
        )
        actions_logger.info("EKSPORT OBSERWOWANYCH — zakończony pomyślnie")
        actions_logger.info("=" * 60)
        return paths

    def export_followers(self, enrich: bool = True) -> dict[str, Path]:
        actions_logger.info("=" * 60)
        actions_logger.info("EKSPORT OBSERWUJĄCYCH — rozpoczęto")
        actions_logger.info("Krok 1: Pobieranie listy obserwujących z API Instagram")
        accounts = self._adapter.get_followers()
        actions_logger.info(
            "Krok 1 zakończony: pobrano %d obserwujących kont", len(accounts)
        )

        if enrich:
            print(f"\n  Pobrano {len(accounts)} obserwujących. Rozpoczynam wzbogacanie profili...")
            print("  (pobieranie bio — to może potrwać długo)\n")
            actions_logger.info(
                "Krok 2: Wzbogacanie profili — pobieranie bio"
            )
            accounts = self._enrich_accounts(accounts, source="followers",
                                              checkpoint_tag="obserwujacy")
            actions_logger.info(
                "Krok 2 zakończony: wzbogacono %d kont", len(accounts)
            )

        actions_logger.info("Krok 3: Zapisywanie plików eksportu")
        paths = export_accounts(accounts, self._outputs_dir, "obserwujacy")
        actions_logger.info(
            "Krok 3 zakończony. Pliki:\n  CSV: %s\n  Tabela: %s\n  Nazwy: %s",
            paths.get("csv", "?"), paths.get("table", "?"), paths.get("usernames", "?"),
        )
        actions_logger.info("EKSPORT OBSERWUJĄCYCH — zakończony pomyślnie")
        actions_logger.info("=" * 60)
        return paths

    def export_dm_contacts(self) -> dict[str, Path]:
        actions_logger.info("=" * 60)
        actions_logger.info("EKSPORT KONTAKTÓW DM — rozpoczęto")
        actions_logger.info("Krok 1: Pobieranie wątków DM z API Instagram")
        accounts = self._adapter.get_dm_contacts()
        actions_logger.info(
            "Krok 1 zakończony: znaleziono %d kontaktów DM", len(accounts)
        )
        actions_logger.info("Krok 2: Zapisywanie plików eksportu")
        paths = export_accounts(accounts, self._outputs_dir, "kontakty_dm")
        actions_logger.info(
            "Krok 2 zakończony. Pliki:\n  CSV: %s\n  Tabela: %s\n  Nazwy: %s",
            paths.get("csv", "?"), paths.get("table", "?"), paths.get("usernames", "?"),
        )
        actions_logger.info("EKSPORT KONTAKTÓW DM — zakończony pomyślnie")
        actions_logger.info("=" * 60)
        return paths

    def export_from_file(self, input_file: Path) -> dict[str, Path]:
        actions_logger.info("=" * 60)
        actions_logger.info(
            "EKSPORT Z PLIKU — plik: %s", input_file.name
        )
        actions_logger.info("Krok 1: Odczytywanie listy nazw użytkowników z pliku")
        usernames = parse_username_file(input_file)
        if not usernames:
            actions_logger.warning("Plik %s jest pusty — brak nazw użytkowników", input_file.name)
            return {}

        actions_logger.info(
            "Krok 1 zakończony: znaleziono %d nazw użytkowników", len(usernames)
        )
        actions_logger.info(
            "Krok 2: Wzbogacanie profili — pobieranie pełnych danych z API"
        )

        accounts: list[AccountInfo] = []
        for i, username in enumerate(usernames, 1):
            actions_logger.info(
                "[%d/%d] Rozwiązywanie i pobieranie profilu: @%s",
                i, len(usernames), username,
            )
            account = self._adapter.enrich_account(username)
            account.source_list = input_file.stem
            actions_logger.info(
                "[%d/%d] @%s → imię='%s', bio='%s' (%d zn.)",
                i, len(usernames),
                account.username,
                account.full_name or "(brak)",
                (account.bio[:60] + "...") if account.bio and len(account.bio) > 60
                else (account.bio or "(brak)"),
                len(account.bio) if account.bio else 0,
            )
            accounts.append(account)
            if i < len(usernames):
                random_delay(self._min_delay, self._max_delay)

        actions_logger.info("Krok 3: Zapisywanie plików eksportu")
        prefix = f"lista_{input_file.stem}"
        paths = export_accounts(accounts, self._outputs_dir, prefix)
        actions_logger.info(
            "Krok 3 zakończony. Pliki:\n  CSV: %s\n  Tabela: %s\n  Nazwy: %s",
            paths.get("csv", "?"), paths.get("table", "?"), paths.get("usernames", "?"),
        )
        actions_logger.info("EKSPORT Z PLIKU — zakończony pomyślnie")
        actions_logger.info("=" * 60)
        return paths
