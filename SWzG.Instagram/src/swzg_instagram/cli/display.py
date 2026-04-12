from __future__ import annotations

from swzg_instagram.models.results import ActionResult, ActionStatus


def print_header(title: str) -> None:
    width = 50
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_export_paths(paths: dict[str, object]) -> None:
    if not paths:
        print("  Brak wyników do wyeksportowania.")
        return
    print("\n  Zapisano pliki:")
    for label, path in paths.items():
        print(f"    {label}: {path}")


def print_preview(usernames: list[str], action_name: str) -> None:
    print(f"\n  Podgląd — {action_name}")
    print(f"  Liczba kont: {len(usernames)}")
    if usernames:
        print("  Lista kont:")
        for i, u in enumerate(usernames, 1):
            print(f"    {i}. {u}")


def confirm_action(action_name: str) -> bool:
    answer = input(f"\n  Czy na pewno chcesz wykonać: {action_name}? (tak/nie): ").strip().lower()
    return answer in ("tak", "t", "yes", "y")


def print_results_summary(results: list[ActionResult]) -> None:
    if not results:
        print("  Brak wyników.")
        return

    counts = {s: 0 for s in ActionStatus}
    for r in results:
        counts[r.status] += 1

    print("\n  Podsumowanie:")
    print(f"    Sukces:    {counts[ActionStatus.SUCCESS]}")
    print(f"    Pominięto: {counts[ActionStatus.SKIPPED]}")
    print(f"    Częściowo: {counts[ActionStatus.PARTIAL]}")
    print(f"    Błąd:      {counts[ActionStatus.FAILED]}")

    failed = [r for r in results if r.status in (ActionStatus.FAILED, ActionStatus.PARTIAL)]
    if failed:
        print("\n  Szczegóły błędów:")
        for r in failed:
            print(f"    - {r.username}: [{r.status.value}] {r.message}")
