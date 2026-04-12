from __future__ import annotations

from dataclasses import dataclass, field

UNAVAILABLE = "niedostępne"


@dataclass
class AccountInfo:
    username: str
    full_name: str | None = None
    bio: str | None = None
    profile_url: str | None = None
    has_chat_history: bool | None = None
    chat_count: int | None = None
    last_chat_date: str | None = None
    source_list: str | None = None
    user_id: str | None = None

    def profile_url_or_default(self) -> str:
        if self.profile_url:
            return self.profile_url
        return f"https://www.instagram.com/{self.username}/"

    def display_value(self, value: str | int | bool | None) -> str:
        if value is None:
            return UNAVAILABLE
        if isinstance(value, bool):
            return "tak" if value else "nie"
        return str(value)

    def to_export_dict(self) -> dict[str, str]:
        return {
            "username": self.username,
            "full_name": self.display_value(self.full_name),
            "bio": self.display_value(self.bio),
            "profile_url": self.profile_url_or_default(),
            "has_chat_history": self.display_value(self.has_chat_history),
            "chat_count": self.display_value(self.chat_count),
            "last_chat_date": self.display_value(self.last_chat_date),
            "source_list": self.display_value(self.source_list),
        }
