from __future__ import annotations

from abc import ABC, abstractmethod

from swzg_instagram.models.account import AccountInfo


class InstagramAdapter(ABC):
    @abstractmethod
    def login(self) -> None: ...

    @abstractmethod
    def check_session(self) -> bool: ...

    @abstractmethod
    def request_new_session(self) -> None: ...

    @abstractmethod
    def get_following(self) -> list[AccountInfo]: ...

    @abstractmethod
    def get_followers(self) -> list[AccountInfo]: ...

    @abstractmethod
    def get_dm_contacts(self) -> list[AccountInfo]: ...

    @abstractmethod
    def build_dm_index(self) -> dict[str, AccountInfo]: ...

    @abstractmethod
    def enrich_account(self, username: str) -> AccountInfo: ...

    @abstractmethod
    def enrich_by_user_id(self, user_id: str) -> AccountInfo | None: ...

    @abstractmethod
    def unfollow(self, username: str) -> bool: ...

    @abstractmethod
    def unfollow_by_user_id(self, user_id: str) -> bool: ...

    @abstractmethod
    def block(self, username: str) -> bool: ...

    @abstractmethod
    def unblock(self, username: str) -> bool: ...

    @abstractmethod
    def delete_chat(self, username: str) -> bool: ...

    @abstractmethod
    def resolve_user_id(self, username: str) -> str | None: ...
