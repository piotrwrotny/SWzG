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
        processed: set[str] = set()
        remaining = set(targets)
        failed: set[str] = set()
        scroll_attempts_without_new = 0
        max_idle_scrolls = 15

        dialog = page.locator("div[role='dialog']").first
        if dialog.count() == 0:
            dialog = page.locator("main")

        actions_logger.info(
            "Rozpoczynam przeglądanie listy obserwowanych (%d do odobserwowania)",
            len(remaining),
        )

        while remaining and scroll_attempts_without_new < max_idle_scrolls:
            found_new = False
            did_action = False

            # a.notranslate targets only the username text links
            # (avatar links use different classes and are not .notranslate)
            username_links = dialog.locator("a.notranslate")
            count = username_links.count()

            for idx in range(count):
                try:
                    link = username_links.nth(idx)
                    href = link.get_attribute("href", timeout=2000)
                    if not href:
                        continue
                    username = href.strip("/").split("/")[0].lower()

                    if username in processed or username == self._instagram_username.lower():
                        continue
                    processed.add(username)
                    found_new = True

                    if username not in remaining or username in failed:
                        continue

                    result = self._unfollow_user_in_dialog(page, link, username)
                    results.append(result)
                    if result.status == ActionStatus.SUCCESS:
                        remaining.discard(username)
                        print(
                            f"  [{len(targets) - len(remaining)}/{len(targets)}] "
                            f"Odobserwowano @{username}"
                        )
                    else:
                        failed.add(username)
                        remaining.discard(username)
                        print(
                            f"  [{len(targets) - len(remaining)}/{len(targets)}] "
                            f"Nie udało się: @{username}"
                        )

                    time.sleep(self._min_delay)
                    # DOM changes after unfollow — re-query on next pass
                    did_action = True
                    break
                except Exception as exc:
                    logger.debug("Błąd wiersza %d: %s", idx, exc)
                    continue

            if did_action:
                scroll_attempts_without_new = 0
                continue

            if found_new:
                scroll_attempts_without_new = 0
            else:
                scroll_attempts_without_new += 1

            # Scroll the list inside the dialog to load more accounts
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
                "Nie znaleziono %d kont na liście obserwowanych: %s",
                len(remaining),
                ", ".join(sorted(remaining)),
            )
            for username in remaining:
                results.append(ActionResult(
                    username=username,
                    status=ActionStatus.SKIPPED,
                    message="Nie znaleziono na liście obserwowanych",
                    step="browser_unfollow",
                ))

        return results

    def _unfollow_user_in_dialog(
        self,
        page: Page,
        user_link: object,
        username: str,
    ) -> ActionResult:
        try:
            actions_logger.info("Odobserwowuję @%s przez przeglądarkę", username)

            # Walk up from the username link to the nearest ancestor
            # that contains a <button> element, then read its text.
            button_text = user_link.evaluate("""
                (link) => {
                    let el = link.parentElement;
                    while (el) {
                        const btn = el.querySelector('button');
                        if (btn) return btn.textContent.trim();
                        el = el.parentElement;
                    }
                    return null;
                }
            """)

            if not button_text:
                actions_logger.warning(
                    "Nie znaleziono przycisku dla @%s", username,
                )
                return ActionResult(
                    username=username,
                    status=ActionStatus.FAILED,
                    message="Nie znaleziono przycisku",
                    step="browser_unfollow",
                )

            if button_text.lower() not in FOLLOWING_BUTTON_TEXTS:
                actions_logger.warning(
                    "Przycisk dla @%s: '%s' — nie rozpoznano jako 'Obserwowanie'",
                    username, button_text,
                )
                return ActionResult(
                    username=username,
                    status=ActionStatus.SKIPPED,
                    message=f"Przycisk: '{button_text}'",
                    step="browser_unfollow",
                )

            # Click the following button via JS
            user_link.evaluate("""
                (link) => {
                    let el = link.parentElement;
                    while (el) {
                        const btn = el.querySelector('button');
                        if (btn) { btn.click(); return; }
                        el = el.parentElement;
                    }
                }
            """)

            time.sleep(0.5)

            # Confirm unfollow in the popup dialog
            confirm_btn = page.locator(
                "button:has-text('Przestań obserwować'),"
                "button:has-text('Unfollow')"
            ).first
            try:
                confirm_btn.wait_for(state="visible", timeout=3000)
                confirm_btn.click()
                time.sleep(0.5)
            except Exception:
                actions_logger.warning(
                    "Nie pojawił się dialog potwierdzenia dla @%s", username,
                )

            actions_logger.info("OK — odobserwowano @%s", username)
            return ActionResult(
                username=username,
                status=ActionStatus.SUCCESS,
                message="Odobserwowano przez przeglądarkę",
                step="browser_unfollow",
            )

        except Exception as exc:
            actions_logger.error(
                "Błąd podczas odobserwowywania @%s: %s", username, exc,
            )
            return ActionResult(
                username=username,
                status=ActionStatus.FAILED,
                message=str(exc),
                step="browser_unfollow",
            )
