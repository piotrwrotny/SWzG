from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    ChallengeRequired,
    LoginRequired,
    PleaseWaitFewMinutes,
    TwoFactorRequired,
    UserNotFound,
)
from instagrapi.types import DirectThread, User, UserShort

from swzg_instagram.adapters.base import InstagramAdapter
from swzg_instagram.models.account import AccountInfo

logger = logging.getLogger(__name__)


class CapabilityError(Exception):
    pass


class InstagrapiAdapter(InstagramAdapter):
    def __init__(
        self,
        username: str,
        password: str,
        session_file: Path,
    ) -> None:
        self._username = username
        self._password = password
        self._session_file = session_file
        self._client = Client()
        self._client.delay_range = [2, 5]

    def login(self) -> None:
        self._session_file.parent.mkdir(parents=True, exist_ok=True)

        if self._session_file.exists():
            logger.info("Loading existing session from %s", self._session_file.name)
            try:
                settings = json.loads(self._session_file.read_text(encoding="utf-8"))
                self._client.set_settings(settings)
                self._client.login(self._username, self._password)
                logger.info("Session restored successfully")
                return
            except (LoginRequired, KeyError, json.JSONDecodeError):
                logger.warning("Saved session invalid, performing fresh login")

        try:
            self._client.login(self._username, self._password)
        except TwoFactorRequired:
            raise SystemExit(
                "Wymagana weryfikacja dwuetapowa (2FA). "
                "Zaloguj się ręcznie i spróbuj ponownie."
            )
        except ChallengeRequired:
            raise SystemExit(
                "Instagram wymaga weryfikacji tożsamości (challenge). "
                "Zaloguj się ręcznie przez przeglądarkę i spróbuj ponownie."
            )
        except BadPassword:
            raise SystemExit(
                "Nieprawidłowe hasło. Sprawdź plik .env."
            )
        except PleaseWaitFewMinutes:
            raise SystemExit(
                "Instagram wymaga odczekania kilku minut. Spróbuj później."
            )

        self._save_session()
        logger.info("Login successful, session saved")

    def _save_session(self) -> None:
        self._session_file.parent.mkdir(parents=True, exist_ok=True)
        settings = self._client.get_settings()
        self._session_file.write_text(
            json.dumps(settings, indent=2, default=str), encoding="utf-8"
        )

    def _user_short_to_account(self, u: UserShort, source: str = "") -> AccountInfo:
        return AccountInfo(
            username=u.username,
            full_name=u.full_name or None,
            user_id=str(u.pk),
            profile_url=f"https://www.instagram.com/{u.username}/",
            source_list=source or None,
        )

    def _user_to_account(self, u: User, source: str = "") -> AccountInfo:
        return AccountInfo(
            username=u.username,
            full_name=u.full_name or None,
            bio=u.biography or None,
            user_id=str(u.pk),
            profile_url=f"https://www.instagram.com/{u.username}/",
            source_list=source or None,
        )

    def get_following(self) -> list[AccountInfo]:
        user_id = self._client.user_id
        following = self._client.user_following(user_id, amount=0)
        return [
            self._user_short_to_account(u, source="following")
            for u in following.values()
        ]

    def get_followers(self) -> list[AccountInfo]:
        user_id = self._client.user_id
        followers = self._client.user_followers(user_id, amount=0)
        return [
            self._user_short_to_account(u, source="followers")
            for u in followers.values()
        ]

    def get_dm_contacts(self) -> list[AccountInfo]:
        threads: list[DirectThread] = self._client.direct_threads(amount=0)
        contacts: list[AccountInfo] = []
        seen: set[str] = set()

        for thread in threads:
            for user in thread.users:
                if user.username in seen:
                    continue
                seen.add(user.username)

                last_date: str | None = None
                if thread.messages:
                    last_msg = thread.messages[0]
                    if last_msg.timestamp:
                        last_date = last_msg.timestamp.isoformat()

                contacts.append(AccountInfo(
                    username=user.username,
                    full_name=user.full_name or None,
                    user_id=str(user.pk),
                    profile_url=f"https://www.instagram.com/{user.username}/",
                    has_chat_history=True,
                    chat_count=len(thread.messages) if thread.messages else None,
                    last_chat_date=last_date,
                    source_list="dm_contacts",
                ))

        return contacts

    def enrich_account(self, username: str) -> AccountInfo:
        try:
            user_id = self._client.user_id_from_username(username)
            info = self._client.user_info(user_id)
            return self._user_to_account(info, source="input_list")
        except UserNotFound:
            logger.warning("User not found: %s", username)
            return AccountInfo(username=username, source_list="input_list")
        except Exception as exc:
            logger.error("Failed to enrich %s: %s", username, exc)
            return AccountInfo(username=username, source_list="input_list")

    def resolve_user_id(self, username: str) -> str | None:
        try:
            uid = self._client.user_id_from_username(username)
            return str(uid)
        except UserNotFound:
            return None
        except Exception as exc:
            logger.error("Failed to resolve user_id for %s: %s", username, exc)
            return None

    def unfollow(self, username: str) -> bool:
        uid = self.resolve_user_id(username)
        if not uid:
            return False
        return self._client.user_unfollow(int(uid))

    def block(self, username: str) -> bool:
        uid = self.resolve_user_id(username)
        if not uid:
            return False
        return self._client.user_block(int(uid))

    def unblock(self, username: str) -> bool:
        uid = self.resolve_user_id(username)
        if not uid:
            return False
        return self._client.user_unblock(int(uid))

    def delete_chat(self, username: str) -> bool:
        uid = self.resolve_user_id(username)
        if not uid:
            raise CapabilityError(f"Cannot resolve user ID for {username}")

        threads = self._client.direct_threads(amount=20)
        target_thread = None
        for thread in threads:
            for user in thread.users:
                if str(user.pk) == uid:
                    target_thread = thread
                    break
            if target_thread:
                break

        if not target_thread:
            logger.warning("No chat thread found for %s", username)
            return False

        try:
            # Attempt to hide/delete the thread
            result = self._client.direct_thread_hide(target_thread.id)
            return bool(result)
        except Exception as exc:
            raise CapabilityError(
                f"Permanent chat deletion unavailable for {username}: {exc}"
            ) from exc
