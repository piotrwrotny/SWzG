from __future__ import annotations

import logging
from pathlib import Path

from swzg_instagram.adapters.base import InstagramAdapter
from swzg_instagram.adapters.instagrapi_adapter import CapabilityError
from swzg_instagram.cli.display import (
    confirm_action,
    print_export_paths,
    print_header,
    print_preview,
    print_results_summary,
)
from swzg_instagram.services.action_service import ActionService
from swzg_instagram.services.browser_unfollow import BrowserUnfollowService
from swzg_instagram.services.export_service import ExportService
from swzg_instagram.utils.config import Settings

logger = logging.getLogger(__name__)

MENU_TEXT = """
  ╔══════════════════════════════════════════════╗
  ║        SWzG Instagram — Menu główne          ║
  ╠══════════════════════════════════════════════╣
  ║  EKSPORT (tylko odczyt)                      ║
  ║  1. Eksportuj obserwowanych (z bio)          ║
  ║  2. Eksportuj obserwujących (z bio)          ║
  ║  3. Eksportuj kontakty z wiadomości (DM)     ║
  ║  4. Eksportuj konta z pliku wejściowego      ║
  ╠══════════════════════════════════════════════╣
  ║  SZYBKI EKSPORT (bez bio — sekundy)          ║
  ║  11. Eksportuj obserwowanych (bez bio)       ║
  ║  12. Eksportuj obserwujących (bez bio)       ║
  ║  19. Eksportuj obserwowanych PRÓBNIE (10)    ║
  ╠══════════════════════════════════════════════╣
  ║  AKCJE (destrukcyjne)                        ║
  ║  5. Przestań obserwować (z pliku — API)      ║
  ║  6. Softblock (z pliku)                      ║
  ║  7. Usuń czaty (z pliku)                     ║
  ╠══════════════════════════════════════════════╣
  ║  PRZEGLĄDARKA                                ║
  ║  8. Przestań obserwować (przeglądarka)       ║
  ╠══════════════════════════════════════════════╣
  ║  0. Wyjście                                  ║
  ╚══════════════════════════════════════════════╝
"""


def _check_session(adapter: InstagramAdapter) -> bool:
    if not adapter.check_session():
        adapter.request_new_session()
    return True


def _select_input_file(inputs_dir: Path) -> Path | None:
    files = sorted(inputs_dir.glob("*.txt"))
    if not files:
        print("  Brak plików wejściowych w katalogu lists/inputs/")
        return None

    print("\n  Dostępne pliki wejściowe:")
    for i, f in enumerate(files, 1):
        print(f"    {i}. {f.name}")

    choice = input("  Wybierz numer pliku: ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            return files[idx]
    except ValueError:
        pass

    print("  Nieprawidłowy wybór.")
    return None


def run_menu(adapter: InstagramAdapter, settings: Settings) -> None:
    export_svc = ExportService(
        adapter=adapter,
        outputs_dir=settings.outputs_dir,
        state_dir=settings.state_dir,
        min_delay=settings.min_delay,
        max_delay=settings.max_delay,
    )
    action_svc = ActionService(
        adapter=adapter,
        inputs_dir=settings.inputs_dir,
        min_delay=settings.min_delay,
        max_delay=settings.max_delay,
    )

    while True:
        print(MENU_TEXT)
        choice = input("  Wybierz opcję: ").strip()

        try:
            if choice == "0":
                print("\n  Do widzenia!")
                break

            elif choice == "1":
                _check_session(adapter)
                print_header("Eksport obserwowanych (z bio)")
                paths = export_svc.export_following(enrich=True)
                print_export_paths(paths)

            elif choice == "11":
                _check_session(adapter)
                print_header("Szybki eksport obserwowanych (bez bio)")
                paths = export_svc.export_following(enrich=False)
                print_export_paths(paths)

            elif choice == "19":
                _check_session(adapter)
                print_header("Eksport obserwowanych — PRÓBNIE (10 kont)")
                paths = export_svc.export_following(enrich=True, limit=10)
                print_export_paths(paths)

            elif choice == "2":
                _check_session(adapter)
                print_header("Eksport obserwujących (z bio)")
                paths = export_svc.export_followers(enrich=True)
                print_export_paths(paths)

            elif choice == "12":
                _check_session(adapter)
                print_header("Szybki eksport obserwujących (bez bio)")
                paths = export_svc.export_followers(enrich=False)
                print_export_paths(paths)

            elif choice == "3":
                _check_session(adapter)
                print_header("Eksport kontaktów DM")
                paths = export_svc.export_dm_contacts()
                print_export_paths(paths)

            elif choice == "4":
                _check_session(adapter)
                print_header("Eksport kont z pliku")
                file_path = _select_input_file(settings.inputs_dir)
                if file_path:
                    paths = export_svc.export_from_file(file_path)
                    print_export_paths(paths)

            elif choice == "5":
                _check_session(adapter)
                print_header("Przestań obserwować")
                usernames = action_svc.plan_unfollow()
                if not usernames:
                    print("  Brak kont w pliku unfollow_targets.txt")
                    continue
                print_preview(usernames, "Przestań obserwować")
                if confirm_action("Przestań obserwować"):
                    results = action_svc.execute_unfollow(usernames)
                    print_results_summary(results)
                else:
                    print("  Anulowano.")

            elif choice == "6":
                _check_session(adapter)
                print_header("Softblock")
                usernames = action_svc.plan_softblock()
                if not usernames:
                    print("  Brak kont w pliku softblock_targets.txt")
                    continue
                print_preview(usernames, "Softblock")
                if confirm_action("Softblock"):
                    results = action_svc.execute_softblock(usernames)
                    print_results_summary(results)
                else:
                    print("  Anulowano.")

            elif choice == "7":
                _check_session(adapter)
                print_header("Usuwanie czatów")
                usernames = action_svc.plan_delete_chats()
                if not usernames:
                    print("  Brak kont w pliku delete_chat_targets.txt")
                    continue
                print_preview(usernames, "Usuwanie czatów")
                if confirm_action("Usuwanie czatów"):
                    results = action_svc.execute_delete_chats(usernames)
                    print_results_summary(results)
                else:
                    print("  Anulowano.")

            elif choice == "8":
                print_header("Odobserwowywanie przez przeglądarkę")
                browser_svc = BrowserUnfollowService(
                    inputs_dir=settings.inputs_dir,
                    state_dir=settings.state_dir,
                    instagram_username=settings.instagram_username,
                    min_delay=settings.min_delay,
                    max_delay=settings.max_delay,
                )
                usernames = browser_svc.plan()
                if not usernames:
                    print("  Brak kont w pliku unfollow_targets.txt")
                    continue
                print_preview(usernames, "Odobserwowywanie (przeglądarka)")
                if confirm_action("Odobserwowywanie przez przeglądarkę"):
                    results = browser_svc.run(usernames)
                    print_results_summary(results)
                else:
                    print("  Anulowano.")

            else:
                print("  Nieprawidłowa opcja. Spróbuj ponownie.")

        except KeyboardInterrupt:
            print("\n\n  Przerwano przez użytkownika.")
            break
        except Exception as exc:
            exc_name = type(exc).__name__
            if "PleaseWaitFewMinutes" in exc_name or "429" in str(exc):
                logger.warning("Rate limited: %s", exc)
                print(
                    "\n  ⏳ Instagram wymaga odczekania — za dużo zapytań."
                    "\n  Poczekaj kilka minut i spróbuj ponownie."
                )
            else:
                logger.error("Unexpected error: %s", exc, exc_info=True)
                print(f"\n  [BŁĄD] {exc}")
