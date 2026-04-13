from __future__ import annotations

import json
import logging
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
from instagrapi.types import User, UserShort

from swzg_instagram.adapters.base import InstagramAdapter
from swzg_instagram.models.account import AccountInfo

logger = logging.getLogger(__name__)

# Default client delay between requests (seconds)
CLIENT_DELAY_RANGE = [3, 6]


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
        self._client.delay_range = CLIENT_DELAY_RANGE

    def _login_by_session_id(self, session_id: str) -> bool:
        import re
        from urllib.parse import unquote

        decoded_sid = unquote(session_id)
        match = re.match(r"^(\d+)", decoded_sid)
        if not match:
            logger.error("Invalid session ID format — cannot extract user_id")
            return False
        user_id = match.group(1)

        old_client = self._client

        # --- Attempt 1: standard login_by_sessionid (creates new device) ---
        try:
            self._client = Client()
            self._client.delay_range = CLIENT_DELAY_RANGE
            self._client.login_by_sessionid(decoded_sid)
            logger.info("Logged in via session ID as %s", self._client.username)
            return True
        except Exception as exc:
            logger.debug("login_by_sessionid standard path failed: %s", exc)
            # Maybe session works despite user_info parsing crash
            try:
                if self._client.user_id and self._check_session_raw():
                    logger.info(
                        "Session valid despite login_by_sessionid parsing error"
                    )
                    return True
            except Exception:
                pass

        # --- Attempt 2: inject session into old client (preserves device) ---
        self._client = old_client
        try:
            auth = getattr(self._client, "authorization_data", None) or {}
            auth["ds_user_id"] = user_id
            auth["sessionid"] = decoded_sid
            self._client.authorization_data = auth

            # Set cookies — user_id is a read-only property derived from these
            http_session = getattr(self._client, "private", None)
            if http_session and hasattr(http_session, "cookies"):
                http_session.cookies.set(
                    "sessionid", decoded_sid, domain=".instagram.com"
                )
                http_session.cookies.set(
                    "ds_user_id", user_id, domain=".instagram.com"
                )

            if self._check_session_raw():
                logger.info(
                    "Session ID accepted via cookie injection (user %s)", user_id
                )
                self._save_session()
                return True
        except Exception as exc:
            logger.debug("Cookie injection fallback failed: %s", exc)

        logger.error("Session ID login failed — all approaches exhausted")
        return False

    def _handle_two_factor(self) -> None:
        two_factor_info = getattr(self._client, "last_json", {}).get("two_factor_info", {})
        logger.info(
            "2FA info: totp=%s, sms=%s, methods=%s",
            two_factor_info.get("totp_two_factor_on"),
            two_factor_info.get("sms_two_factor_on"),
            [m.get("label") for m in two_factor_info.get("two_factor_methods", [])],
        )

        print(
            "\n  ╔════════════════════════════════════════════════════════════════╗"
            "\n  ║  Wymagana weryfikacja dwuetapowa (2FA)                        ║"
            "\n  ╠════════════════════════════════════════════════════════════════╣"
            "\n  ║                                                                ║"
            "\n  ║  UWAGA: Zatwierdzanie powiadomień push w aplikacji Instagram  ║"
            "\n  ║  NIE działa przez API — potrzebny jest kod lub sesja.         ║"
            "\n  ║                                                                ║"
            "\n  ║  Opcje:                                                        ║"
            "\n  ║  1. Wpisz kod 2FA (SMS / Google Authenticator / itp.)          ║"
            "\n  ║  2. Zaloguj się przez Session ID z przeglądarki               ║"
            "\n  ║                                                                ║"
            "\n  ╚════════════════════════════════════════════════════════════════╝"
        )

        choice = input("\n  Wybierz opcję (1 lub 2): ").strip()

        if choice == "1":
            code = input("  Wpisz kod 2FA: ").strip()
            if not code:
                raise SystemExit("Nie podano kodu 2FA.")
            try:
                saved = self._client.get_settings()
                self._client = Client()
                self._client.delay_range = CLIENT_DELAY_RANGE
                self._client.set_settings(saved)
                self._client.login(
                    self._username, self._password, verification_code=code
                )
                return
            except (TwoFactorRequired, ChallengeRequired, LoginRequired) as exc:
                logger.error("2FA code rejected: %s", exc)
                raise SystemExit("Kod 2FA odrzucony. Spróbuj ponownie.")

        if choice == "2":
            self._prompt_session_id_login()
            return

        raise SystemExit("Nieprawidłowy wybór.")

    def _prompt_session_id_login(self) -> None:
        print(
            "\n  ╔════════════════════════════════════════════════════════════════╗"
            "\n  ║  Logowanie przez Session ID                                   ║"
            "\n  ╠════════════════════════════════════════════════════════════════╣"
            "\n  ║                                                                ║"
            "\n  ║  1. Otwórz przeglądarkę i zaloguj się na instagram.com         ║"
            "\n  ║  2. Naciśnij F12 (narzędzia deweloperskie)                     ║"
            "\n  ║  3. Przejdź do: Application → Cookies → instagram.com         ║"
            "\n  ║  4. Znajdź cookie o nazwie  sessionid                         ║"
            "\n  ║  5. Skopiuj całą wartość i wklej poniżej                      ║"
            "\n  ║                                                                ║"
            "\n  ╚════════════════════════════════════════════════════════════════╝"
        )
        session_id = input("\n  Wklej sessionid: ").strip()
        if not session_id or len(session_id) < 30:
            raise SystemExit("Nieprawidłowy sessionid (za krótki).")
        if not self._login_by_session_id(session_id):
            raise SystemExit("Logowanie przez sessionid nie powiodło się.")

    def login(self) -> None:
        self._session_file.parent.mkdir(parents=True, exist_ok=True)

        if self._session_file.exists():
            logger.info("Loading existing session from %s", self._session_file.name)
            try:
                settings = json.loads(self._session_file.read_text(encoding="utf-8"))
                self._client.set_settings(settings)
                self._client.login(self._username, self._password)
                logger.info("Session restored successfully")
                self._save_session()
                return
            except (LoginRequired, KeyError, json.JSONDecodeError):
                logger.warning("Saved session invalid, performing fresh login")
                self._client = Client()
                self._client.delay_range = CLIENT_DELAY_RANGE

        try:
            self._client.login(self._username, self._password)
        except (TwoFactorRequired, ChallengeRequired):
            self._handle_two_factor()
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

    def _check_session_raw(self) -> bool:
        """Verify session with a raw private API call, avoiding model parsing.

        Returns True if session is valid, False if expired/invalid.
        Raises PleaseWaitFewMinutes if rate-limited (session may still be valid).
        """
        try:
            result = self._client.private_request(
                f"users/{self._client.user_id}/info/",
                params={"is_prefetch": "false"},
            )
            return result.get("status") == "ok" or "user" in result
        except LoginRequired:
            return False
        except PleaseWaitFewMinutes:
            raise  # Caller must handle — session might be valid
        except Exception as exc:
            msg = str(exc).lower()
            if "please wait" in msg or "feedback_required" in msg or "is_spam" in msg:
                raise PleaseWaitFewMinutes(str(exc))
            logger.debug("Raw session check error (non-fatal): %s", exc)
            return False

    def check_session(self) -> bool:
        try:
            return self._check_session_raw()
        except PleaseWaitFewMinutes:
            # Rate limited — session is probably still valid, don't invalidate
            logger.warning("Rate limited during session check — assuming session valid")
            return True
        except Exception as exc:
            logger.warning("Session check failed: %s", exc)
            return False

    def request_new_session(self) -> None:
        print("\n  ⚠ Sesja wygasła. Wymagane ponowne logowanie.")
        self._prompt_session_id_login()
        self._save_session()
        print("  Nowa sesja zapisana.\n")

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
        following = self._client.user_following_v1(user_id, amount=0)
        return [
            self._user_short_to_account(u, source="following")
            for u in following
        ]

    def get_followers(self) -> list[AccountInfo]:
        user_id = self._client.user_id
        followers = self._client.user_followers_v1(user_id, amount=0)
        return [
            self._user_short_to_account(u, source="followers")
            for u in followers
        ]

    def _fetch_dm_threads_raw(self, amount: int = 0) -> list[dict]:
        """Fetch raw DM thread dicts from inbox API, skipping message parsing.

        This avoids instagrapi's extract_direct_message which crashes on
        MediaXma(video_url=None).  We only need thread metadata and user info.
        """
        cursor = None
        threads: list[dict] = []
        try:
            while True:
                params = {
                    "visual_message_return_type": "unseen",
                    "thread_message_limit": "0",
                    "persistentBadging": "true",
                    "limit": "20",
                    "is_prefetching": "false",
                }
                if cursor:
                    params.update(
                        {"cursor": cursor, "direction": "older", "fetch_reason": "page_scroll"}
                    )
                result = self._client.private_request("direct_v2/inbox/", params=params)
                inbox = result.get("inbox", {})
                for thread_data in inbox.get("threads", []):
                    threads.append(thread_data)
                cursor = inbox.get("oldest_cursor")
                if not cursor or (amount and len(threads) >= amount):
                    break
        except Exception as exc:
            logger.warning(
                "Błąd pobierania wątków DM (pobrano %d): %s",
                len(threads), exc,
            )
        if amount:
            threads = threads[:amount]
        logger.info("Pobrano %d surowych wątków DM z API", len(threads))
        return threads

    @staticmethod
    def _parse_thread_contacts(thread_data: dict) -> list[dict]:
        """Extract minimal user info + chat metadata from a raw thread dict."""
        users_raw = thread_data.get("users", [])
        last_ts = thread_data.get("last_activity_at_secs")
        contacts: list[dict] = []
        for u in users_raw:
            contacts.append({
                "username": u.get("username", ""),
                "full_name": u.get("full_name", ""),
                "pk": str(u.get("pk", "")),
                "has_chat": True,
                "last_activity_ts": last_ts,
            })
        return contacts

    def get_dm_contacts(self) -> list[AccountInfo]:
        raw_threads = self._fetch_dm_threads_raw()
        contacts: list[AccountInfo] = []
        seen: set[str] = set()

        for thread_data in raw_threads:
            parsed = self._parse_thread_contacts(thread_data)
            for c in parsed:
                uname = c["username"]
                if not uname or uname in seen:
                    continue
                seen.add(uname)

                last_date: str | None = None
                if c["last_activity_ts"]:
                    try:
                        from datetime import datetime, timezone
                        ts = int(c["last_activity_ts"])
                        last_date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        pass

                contacts.append(AccountInfo(
                    username=uname,
                    full_name=c["full_name"] or None,
                    user_id=c["pk"],
                    profile_url=f"https://www.instagram.com/{uname}/",
                    has_chat_history=True,
                    last_chat_date=last_date,
                    source_list="dm_contacts",
                ))

        return contacts

    def enrich_account(self, username: str) -> AccountInfo:
        try:
            user_id = self._client.user_id_from_username(username)
            info = self._client.user_info_v1(user_id)
            logger.info(
                "Wzbogacono @%s: imię=%r, bio=%d zn.",
                username,
                info.full_name,
                len(info.biography) if info.biography else 0,
            )
            return self._user_to_account(info, source="input_list")
        except UserNotFound:
            logger.warning("User not found: %s", username)
            return AccountInfo(username=username, source_list="input_list")
        except Exception as exc:
            logger.error("Failed to enrich %s: %s", username, exc)
            return AccountInfo(username=username, source_list="input_list")

    def enrich_by_user_id(self, user_id: str) -> AccountInfo | None:
        try:
            info = self._client.user_info_v1(user_id)
            logger.info(
                "Wzbogacono user_id=%s → @%s | imię='%s' | bio=%d zn. | prywatne=%s",
                user_id,
                info.username,
                info.full_name or "",
                len(info.biography) if info.biography else 0,
                info.is_private,
            )
            return self._user_to_account(info)
        except UserNotFound:
            logger.warning("Nie znaleziono użytkownika user_id=%s", user_id)
            return None
        except Exception as exc:
            logger.error("Błąd wzbogacania user_id=%s: %s", user_id, exc)
            return None

    def build_dm_index(self) -> dict[str, AccountInfo]:
        logger.info("Budowanie indeksu DM — rozpoczęto")
        raw_threads = self._fetch_dm_threads_raw()
        index: dict[str, AccountInfo] = {}

        for thread_data in raw_threads:
            parsed = self._parse_thread_contacts(thread_data)
            for c in parsed:
                uname_lower = c["username"].lower()
                if not uname_lower or uname_lower in index:
                    continue

                last_date: str | None = None
                if c["last_activity_ts"]:
                    try:
                        from datetime import datetime, timezone
                        ts = int(c["last_activity_ts"])
                        last_date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    except (ValueError, OSError):
                        pass

                index[uname_lower] = AccountInfo(
                    username=c["username"],
                    full_name=c["full_name"] or None,
                    user_id=c["pk"],
                    profile_url=f"https://www.instagram.com/{c['username']}/",
                    has_chat_history=True,
                    last_chat_date=last_date,
                    source_list="dm_contacts",
                )

        logger.info("Indeks DM zbudowany: %d kontaktów", len(index))
        return index

    def resolve_user_id(self, username: str) -> str | None:
        try:
            # Use v1 private API directly — avoids wasteful GQL requests (429)
            result = self._client.private_request(
                f"users/{username}/usernameinfo/"
            )
            user = result.get("user", {})
            pk = user.get("pk") or user.get("pk_id")
            if pk:
                return str(pk)
            return None
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

    def unfollow_by_user_id(self, user_id: str) -> bool:
        return self._client.user_unfollow(int(user_id))

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

        raw_threads = self._fetch_dm_threads_raw(amount=50)
        target_thread_id: str | None = None
        for thread_data in raw_threads:
            for user in thread_data.get("users", []):
                if str(user.get("pk", "")) == uid:
                    target_thread_id = thread_data.get("thread_id")
                    break
            if target_thread_id:
                break

        if not target_thread_id:
            logger.warning("No chat thread found for %s", username)
            return False

        try:
            result = self._client.direct_thread_hide(target_thread_id)
            return bool(result)
        except Exception as exc:
            raise CapabilityError(
                f"Permanent chat deletion unavailable for {username}: {exc}"
            ) from exc
