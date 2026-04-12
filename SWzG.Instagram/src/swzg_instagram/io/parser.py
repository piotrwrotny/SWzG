from __future__ import annotations

from pathlib import Path


def parse_username_file(path: Path) -> list[str]:
    if not path.exists():
        return []

    seen: set[str] = set()
    result: list[str] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            username = stripped.lstrip("@").strip()
            if not username:
                continue
            lower = username.lower()
            if lower not in seen:
                seen.add(lower)
                result.append(username)

    return result
