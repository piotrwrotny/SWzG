from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from tabulate import tabulate

from swzg_instagram.models.account import AccountInfo

POLISH_HEADERS = {
    "username": "Nazwa użytkownika",
    "full_name": "Imię i nazwisko",
    "bio": "Bio",
    "profile_url": "URL profilu",
    "has_chat_history": "Historia czatów",
    "chat_count": "Liczba wiadomości",
    "last_chat_date": "Data ostatniego czatu",
    "source_list": "Lista źródłowa",
}

CSV_FIELDS = list(POLISH_HEADERS.keys())


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def export_accounts(
    accounts: list[AccountInfo],
    output_dir: Path,
    prefix: str,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()

    csv_path = output_dir / f"{prefix}_{ts}.csv"
    txt_table_path = output_dir / f"{prefix}_{ts}_tabela.txt"
    txt_usernames_path = output_dir / f"{prefix}_{ts}_nazwy.txt"

    rows = [a.to_export_dict() for a in accounts]

    # CSV
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    # TXT table with Polish headers
    table_data = []
    for row in rows:
        table_data.append([row[k] for k in CSV_FIELDS])
    polish_cols = [POLISH_HEADERS[k] for k in CSV_FIELDS]
    table_str = tabulate(table_data, headers=polish_cols, tablefmt="grid")
    txt_table_path.write_text(table_str + "\n", encoding="utf-8")

    # Usernames only
    usernames = [a.username for a in accounts]
    txt_usernames_path.write_text("\n".join(usernames) + "\n", encoding="utf-8")

    return {
        "csv": csv_path,
        "table": txt_table_path,
        "usernames": txt_usernames_path,
    }
