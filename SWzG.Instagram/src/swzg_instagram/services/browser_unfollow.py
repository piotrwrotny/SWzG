from __future__ import annotations

import logging
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from swzg_instagram.io.parser import parse_username_file
from swzg_instagram.models.results import ActionResult, ActionStatus

logger = logging.getLogger(__name__)
actions_logger = logging.getLogger("actions")

INSTAGRAM_URL = "https://www.instagram.com"
FOLLOWING_PATH_SUFFIX = "/following/"
SCROLL_PAUSE = 1.0
POST_UNFOLLOW_DELAY = 1.0

# Button labels that indicate the user is already followed (lowercase).
FOLLOWING_BUTTON_TEXTS_JS = (
    "obserwowanie|obserwujesz|following|requested|wysłano prośbę"
)


class BrowserUnfollowService:
    def __init__(
        self,
        inputs_dir: Path,
        state_dir: Path,
        instagram_username: str,
        min_delay: float = 2.0,
        max_delay: float = 4.0,
    ) -> None:
        self._inputs_dir = inputs_dir
        self._state_dir = state_dir
        self._instagram_username = instagram_username
        self._min_delay = min_delay
        self._max_delay = max_delay

    def plan(self) -> list[str]:
        return parse_username_file(self._inputs_dir / "unfollow_targets.txt")

    def run(self, usernames: list[str]) -> list[ActionResult]:
        targets = {u.lower() for u in usernames}
        if not targets:
            return []

        actions_logger.info("=" * 60)
        actions_logger.info(
            "PRZEGLĄDARKA — ODOBSERWOWANIE: %d kont na liście", len(targets),
        )
        actions_logger.info("=" * 60)

        results: list[ActionResult] = []
        profile_path = self._state_dir / "browser_profile"
        profile_path.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=False,
                viewport={"width": 1280, "height": 900},
                locale="pl-PL",
            )
            page = context.pages[0] if context.pages else context.new_page()

            if not self._ensure_logged_in(page):
                context.close()
                return results

            actions_logger.info("Stan sesji przeglądarki zapisany")

            self._navigate_to_following(page)

            input(
                "\n  ✅ Lista obserwowanych otwarta."
                "\n  Naciśnij ENTER aby rozpocząć odobserwowywanie..."
            )

            results = self._process_following_list(page, targets)

            ok_count = sum(1 for r in results if r.status == ActionStatus.SUCCESS)
            actions_logger.info("=" * 60)
            actions_logger.info(
                "ZAKOŃCZONO: %d/%d odobserwowano przez przeglądarkę",
                ok_count, len(targets),
            )
            actions_logger.info("=" * 60)

            print(f"\n  Zakończono. Odobserwowano {ok_count}/{len(targets)} kont.")
            input("  Naciśnij ENTER aby zamknąć przeglądarkę...")

            context.close()

        return results

    def _ensure_logged_in(self, page: Page) -> bool:
        page.goto(INSTAGRAM_URL, wait_until="domcontentloaded")
        time.sleep(2)

        # Dismiss cookie dialog if present
        try:
            cookie_btn = page.locator(
                "button:has-text('Zezwól na niezbędne i opcjonalne pliki cookie'),"
                "button:has-text('Allow all cookies'),"
                "button:has-text('Zezwól na wszystkie pliki cookie'),"
                "button:has-text('Allow essential and optional cookies')"
            )
            if cookie_btn.count() > 0:
                cookie_btn.first.click()
                time.sleep(1)
        except Exception:
            pass

        # Check if already logged in
        if self._is_logged_in(page):
            print("  ✅ Zalogowano automatycznie (zapisana sesja).")
            actions_logger.info("Sesja przeglądarki aktywna")
            return True

        print(
            "\n  ╔════════════════════════════════════════════════════════════════╗"
            "\n  ║  Logowanie przez przeglądarkę                                 ║"
            "\n  ╠════════════════════════════════════════════════════════════════╣"
            "\n  ║                                                                ║"
            "\n  ║  Przeglądarka Chromium otworzyła się z instagram.com.          ║"
            "\n  ║  Zaloguj się ręcznie (email/hasło + 2FA jeśli potrzeba).       ║"
            "\n  ║                                                                ║"
            "\n  ║  Po zalogowaniu naciśnij ENTER w tym oknie konsoli.            ║"
            "\n  ║                                                                ║"
            "\n  ╚════════════════════════════════════════════════════════════════╝"
        )
        input("\n  Naciśnij ENTER gdy jesteś zalogowany na Instagram... ")

        if not self._is_logged_in(page):
            print("  ❌ Nie wykryto zalogowanego użytkownika. Przerywam.")
            return False

        print("  ✅ Zalogowano pomyślnie!")
        actions_logger.info("Zalogowano przez przeglądarkę")
        return True

    def _is_logged_in(self, page: Page) -> bool:
        try:
            # Logged-in Instagram has navigation bar with profile link or home icon
            logged_in = page.locator(
                "svg[aria-label='Strona główna'],"
                "svg[aria-label='Home'],"
                "a[href*='/direct/'],"
                "span[role='link'][tabindex='0']"
            )
            return logged_in.count() > 0
        except Exception:
            return False

    def _navigate_to_following(self, page: Page) -> None:
        following_url = f"{INSTAGRAM_URL}/{self._instagram_username}{FOLLOWING_PATH_SUFFIX}"
        actions_logger.info("Otwieram listę obserwowanych: %s", following_url)
        page.goto(following_url, wait_until="domcontentloaded")
        time.sleep(3)

    def _process_following_list(
        self, page: Page, targets: set[str],
    ) -> list[ActionResult]:
        results: list[ActionResult] = []
        remaining = set(targets)
        seen_usernames: set[str] = set()
        idle_scrolls = 0
        max_idle_scrolls = 15
        own = self._instagram_username.lower()
        total = len(targets)

        dialog = page.locator("div[role='dialog']").first
        if dialog.count() == 0:
            dialog = page.locator("main")

        actions_logger.info(
            "Rozpoczynam przeglądanie listy obserwowanych (%d do odobserwowania)",
            len(remaining),
        )

        while remaining and idle_scrolls < max_idle_scrolls:
            # --- single JS call: scan all visible rows, return usernames ---
            visible = self._scan_visible_usernames(dialog)
            new_found = False

            for username in visible:
                if username == own or username in seen_usernames:
                    continue
                seen_usernames.add(username)
                new_found = True

                if username not in remaining:
                    continue

                # --- unfollow this user ---
                result = self._click_unfollow(page, dialog, username)
                results.append(result)
                remaining.discard(username)

                done = total - len(remaining)
                if result.status == ActionStatus.SUCCESS:
                    print(f"  [{done}/{total}] Odobserwowano @{username}")
                else:
                    print(f"  [{done}/{total}] Pominięto @{username}: {result.message}")

                time.sleep(POST_UNFOLLOW_DELAY)

            if new_found:
                idle_scrolls = 0
            else:
                idle_scrolls += 1

            # Scroll to load more
            try:
                dialog.evaluate("""
                    (dlg) => {
                        const s = dlg.querySelector('div[style*="overflow"]');
                        if (s) s.scrollTop = s.scrollHeight;
                    }
                """)
            except Exception:
                page.keyboard.press("End")

            time.sleep(SCROLL_PAUSE)

        if remaining:
            actions_logger.warning(
                "Nie znaleziono %d kont na liście: %s",
                len(remaining), ", ".join(sorted(remaining)),
            )
            for username in remaining:
                results.append(ActionResult(
                    username=username,
                    status=ActionStatus.SKIPPED,
                    message="Nie znaleziono na liście obserwowanych",
                    step="browser_unfollow",
                ))

        return results

    # ------------------------------------------------------------------
    # Fast helpers — minimise Python↔browser round-trips
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_visible_usernames(dialog: object) -> list[str]:
        """Return all usernames currently rendered in the dialog (single JS call)."""
        return dialog.evaluate("""
            (dlg) => {
                const links = dlg.querySelectorAll('a.notranslate');
                const names = [];
                for (const a of links) {
                    const href = a.getAttribute('href');
                    if (href) names.push(href.replace(/\\//g, '').split('/')[0].toLowerCase());
                }
                return names;
            }
        """)

    @staticmethod
    def _click_unfollow(
        page: Page, dialog: object, username: str,
    ) -> ActionResult:
        """Find the row for *username*, click the button, confirm the popup."""
        try:
            actions_logger.info("Odobserwowuję @%s", username)

            # One JS call: find the link, walk up to the row's button, click it.
            btn_text = dialog.evaluate(
                """
                (dlg, args) => {
                    const [uname, allowed] = args;
                    const pat = new RegExp(allowed, 'i');
                    const links = dlg.querySelectorAll('a.notranslate');
                    for (const a of links) {
                        const href = (a.getAttribute('href') || '').replace(/\\//g, '');
                        if (href.toLowerCase() !== uname) continue;
                        let el = a.parentElement;
                        while (el && el !== dlg) {
                            const btn = el.querySelector('button');
                            if (btn) {
                                const txt = btn.textContent.trim();
                                if (pat.test(txt)) { btn.click(); return txt; }
                                return 'WRONG:' + txt;
                            }
                            el = el.parentElement;
                        }
                        return null;
                    }
                    return null;
                }
                """,
                [username, FOLLOWING_BUTTON_TEXTS_JS],
            )

            if btn_text is None:
                actions_logger.warning("Nie znaleziono przycisku dla @%s", username)
                return ActionResult(
                    username=username, status=ActionStatus.FAILED,
                    message="Nie znaleziono przycisku", step="browser_unfollow",
                )

            if btn_text.startswith("WRONG:"):
                label = btn_text[6:]
                actions_logger.warning("Przycisk @%s: '%s'", username, label)
                return ActionResult(
                    username=username, status=ActionStatus.SKIPPED,
                    message=f"Przycisk: '{label}'", step="browser_unfollow",
                )

            # Wait for and click the confirmation popup
            confirm_btn = page.locator(
                "button:has-text('Przestań obserwować'),"
                "button:has-text('Unfollow')"
            ).first
            try:
                confirm_btn.wait_for(state="visible", timeout=2000)
                confirm_btn.click()
            except Exception:
                actions_logger.warning("Brak popupu potwierdzenia dla @%s", username)

            actions_logger.info("OK — odobserwowano @%s", username)
            return ActionResult(
                username=username, status=ActionStatus.SUCCESS,
                message="Odobserwowano przez przeglądarkę", step="browser_unfollow",
            )

        except Exception as exc:
            actions_logger.error("Błąd @%s: %s", username, exc)
            return ActionResult(
                username=username, status=ActionStatus.FAILED,
                message=str(exc), step="browser_unfollow",
            )
