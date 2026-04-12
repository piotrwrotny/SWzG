from __future__ import annotations

import logging
from pathlib import Path

from swzg_instagram.adapters.base import InstagramAdapter
from swzg_instagram.cli.display import (
    confirm_action,
    print_export_paths,
    print_header,
    print_preview,
    print_results_summary,
)
from swzg_instagram.services.action_service import ActionService
from swzg_instagram.services.export_service import ExportService
from swzg_instagram.utils.config import Settings

logger = logging.getLogger(__name__)

MENU_TEXT = """
  ╔══════════════════════════════════════════════╗
  ║        SWzG Instagram — Menu główne          ║
  ╠══════════════════════════════════════════════╣
  ║  EKSPORT (tylko odczyt)                      ║
  ║  1. Eksportuj obserwowanych                  ║
  ║  2. Eksportuj obserwujących                  ║
  ║  3. Eksportuj kontakty z wiadomości (DM)     ║
  ║  4. Eksportuj konta z pliku wejściowego      ║
  ╠══════════════════════════════════════════════╣
  ║  AKCJE (destrukcyjne)                        ║
  ║  5. Przestań obserwować (z pliku)            ║
  ║  6. Softblock (z pliku)                      ║
  ║  7. Usuń czaty (z pliku)                     ║
  ╠══════════════════════════════════════════════╣
  ║  0. Wyjście                                  ║
  ╚══════════════════════════════════════════════╝
"""


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
                print_header("Eksport obserwowanych")
                paths = export_svc.export_following()
                print_export_paths(paths)

            elif choice == "2":
                print_header("Eksport obserwujących")
                paths = export_svc.export_followers()
                print_export_paths(paths)

            elif choice == "3":
                print_header("Eksport kontaktów DM")
                paths = export_svc.export_dm_contacts()
                print_export_paths(paths)

            elif choice == "4":
                print_header("Eksport kont z pliku")
                file_path = _select_input_file(settings.inputs_dir)
                if file_path:
                    paths = export_svc.export_from_file(file_path)
                    print_export_paths(paths)

            elif choice == "5":
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

            else:
                print("  Nieprawidłowa opcja. Spróbuj ponownie.")

        except KeyboardInterrupt:
            print("\n\n  Przerwano przez użytkownika.")
            break
        except Exception as exc:
            logger.error("Unexpected error: %s", exc, exc_info=True)
            print(f"\n  [BŁĄD] {exc}")
