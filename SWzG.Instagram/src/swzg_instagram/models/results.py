from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ActionStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class ActionResult:
    username: str
    status: ActionStatus
    message: str = ""
    step: str = ""
