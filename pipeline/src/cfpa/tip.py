"""The Ko-fi tip line (DECISIONS 0073; wording approved by Chelsea 2026-11-17).

One line at the end of every calendar event's description and one sentence
at the end of every water page (on since the App Review Board answered,
2026-11-17), both pointing at Chelsea's personal Ko-fi page. Website and calendar
feeds only: the iOS and Android apps read ``snapshot/v1.json`` and
``snapshot/v2.json``, never a page or a feed, and nothing here writes to the
snapshot. Judged on 2027-05-31: under $20 in tips by then, the line comes
out.

It is a plain link. No Ko-fi script, button image, widget or iframe, nothing
loaded from Ko-fi until a person presses the link, and no ``data-ga-event``,
so the site's GA4 click listener (``_ga4.html.jinja``) does not report it.

``KOFI_URL`` is the one value that holds the address. Set to
``""``, the line disappears from every page and every feed, whatever
``TIP_ON_WATER_PAGES`` says.
"""

from __future__ import annotations

# Chelsea's Ko-fi page, sent 2026-11-17. (The same day she lifted the
# 2026-11-27 hold for this line only; DECISIONS 0073.) The address lives
# here and nowhere else.
KOFI_URL = "https://ko-fi.com/chelseakr"

# The water-page sentence's switch. Chelsea's rule (2026-11-17): hold it
# while the App Review Board appeal is open, add it once Apple answers. The
# Board upheld the 4.3(a) rejection on 2026-11-17 (appeal closed; the app is
# not on the App Store), so it is on. False takes it off every water page and
# leaves the calendar line alone.
TIP_ON_WATER_PAGES = True

# The water-page sentence (approved 2026-11-17). The second half is the link
# text.
PAGE_LEAD = "Trout Truck is free and made by one person."
PAGE_LINK_TEXT = "You can leave a tip on Ko-fi."

# Every link to Ko-fi opens in a new tab, without giving Ko-fi's page a handle
# on this one.
LINK_TARGET = "_blank"
LINK_REL = "noopener"


def page_context(url: str | None = None) -> dict[str, str] | None:
    """What the water templates need, or None when the line is off (no
    address, or ``TIP_ON_WATER_PAGES`` False)."""
    url = KOFI_URL if url is None else url
    if not url or not TIP_ON_WATER_PAGES:
        return None
    return {
        "url": url,
        "lead": PAGE_LEAD,
        "link_text": PAGE_LINK_TEXT,
        "target": LINK_TARGET,
        "rel": LINK_REL,
    }


def calendar_line(url: str | None = None) -> str:
    """The last line of every calendar event's description (approved
    2026-11-17), unescaped; ``""`` when there is no address. The full https
    address, so every calendar app can make it a link. The caller joins it
    with a newline and escapes the whole description once."""
    url = KOFI_URL if url is None else url
    if not url:
        return ""
    return f"Free calendar from Trout Truck, made by one person. Tips: {url}"


__all__ = [
    "KOFI_URL",
    "LINK_REL",
    "LINK_TARGET",
    "PAGE_LEAD",
    "PAGE_LINK_TEXT",
    "TIP_ON_WATER_PAGES",
    "calendar_line",
    "page_context",
]
