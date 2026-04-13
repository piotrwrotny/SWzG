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
            "last_chat_date": self.display_value(self.last_chat_date),
            "source_list": self.display_value(self.source_list),
        }

    def to_checkpoint_dict(self) -> dict[str, str | bool | None]:
        return {
            "username": self.username,
            "full_name": self.full_name,
            "bio": self.bio,
            "profile_url": self.profile_url,
            "has_chat_history": self.has_chat_history,
            "last_chat_date": self.last_chat_date,
            "source_list": self.source_list,
            "user_id": self.user_id,
        }

    @classmethod
    def from_checkpoint_dict(cls, d: dict) -> AccountInfo:
        return cls(
            username=d["username"],
            full_name=d.get("full_name"),
            bio=d.get("bio"),
            profile_url=d.get("profile_url"),
            has_chat_history=d.get("has_chat_history"),
            last_chat_date=d.get("last_chat_date"),
            source_list=d.get("source_list"),
            user_id=d.get("user_id"),
        )
