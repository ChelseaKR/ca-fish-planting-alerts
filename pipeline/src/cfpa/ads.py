"""Display ads on the website (docs/adr/0040), OFF by default.

One Google AdSense unit, at the end of the main content of the pages named
in ``AD_PAGES``, and nowhere else: never the home page, the gear guide (its
Amazon links), about, privacy, support, data, the guides, the email pages,
the emails or the apps. The build emits nothing for ads unless
``ADS_ENABLED`` is True, and then only with a well-formed publisher ID and
ad-unit slot ID (a publisher ID alone, with the switch off, adds only the
``google-adsense-account`` meta tag and ads.txt that AdSense's site review
looks for); a flag that is on without them fails the build rather than
shipping an empty box.

The privacy rules the slot's script follows (``_ad_slot.html.jinja``):
Global Privacy Control, Do Not Track or the visitor's own "turn off ads"
choice means the AdSense script never loads; otherwise it asks for
non-personalized ads only. Restricted data processing is an AdSense account
setting (docs/adr/0040 lists the owner steps). The slot stays collapsed until
AdSense reports it filled and removes itself on "unfilled", a script error
or a 10-second wait, so no visitor ever sees a blank or broken slot.
The slot is collapsed to zero height while it waits, not display:none,
because AdSense sizes a responsive unit from the width of its container.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jinja2

# THE ADS SWITCH. False until the owner has an approved AdSense account and
# has done the steps in docs/adr/0040. Turning it on is one small reviewed
# pull request that sets these four values together.
ADS_ENABLED = False
# The AdSense publisher ID, "ca-pub-" and 16 digits (AdSense > Account >
# Settings > Account information). Public by design: it is in every page's
# HTML and in ads.txt.
ADSENSE_PUBLISHER_ID = ""
# The display ad unit's slot ID, the 10 digits in data-ad-slot of the code
# AdSense shows for a new responsive display unit (Ads > By ad unit).
ADSENSE_SLOT_ID = ""
# The day the privacy policy's ads section takes effect: the launch day.
ADS_EFFECTIVE_DATE = ""

_PUBLISHER_ID_RE = re.compile(r"ca-pub-[0-9]{16}")
_SLOT_ID_RE = re.compile(r"[0-9]{6,12}")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# The pages that carry the one ad unit, by template name.
AD_PAGES = frozenset(
    {
        "water.html.jinja",
        "county.html.jinja",
        "counties.html.jinja",
        "region.html.jinja",
        "species.html.jinja",
        "week.html.jinja",
        "week_index.html.jinja",
        "state_hub.html.jinja",
        "state_water.html.jinja",
    }
)

ADSENSE_SCRIPT_URL = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"
# ads.txt's certification authority ID for Google, from AdSense's ads.txt
# guide (support.google.com/adsense/answer/7532444).
GOOGLE_ADS_TXT_CERT_ID = "f08c47fec0942fa0"

AD_CSS = """
/* Display ads (cfpa/ads.py). The slot stays collapsed until AdSense fills it. */
.ad-slot { margin: 2.5rem 0 1rem; padding-top: 0.75rem; border-top: 1px solid currentColor; }
.ad-slot.ad-pending { height: 0; overflow: hidden; margin: 0; padding: 0; border: 0; }
.ad-slot .ad-label { margin: 0 0 0.5rem; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
.ad-slot ins.adsbygoogle { display: block; }
.ad-slot ins.adsbygoogle[data-ad-status="unfilled"] { display: none !important; }
"""


@dataclass(frozen=True)
class AdsConfig:
    """A checked ads configuration. ``enabled`` False means no ad unit; a
    publisher ID without it only connects the site to the AdSense account."""

    enabled: bool = False
    publisher_id: str = ""
    slot_id: str = ""
    effective_date: str = ""

    @property
    def ads_txt_publisher(self) -> str:
        """The ID as ads.txt writes it: "pub-..." without "ca-"."""
        return self.publisher_id.removeprefix("ca-")


ADS_OFF = AdsConfig()


def _check_publisher_id(publisher_id: str) -> None:
    if not _PUBLISHER_ID_RE.fullmatch(publisher_id):
        raise ValueError(
            f"AdSense publisher ID {publisher_id!r} is not of the form "
            "'ca-pub-' followed by 16 digits"
        )


def ads_config(
    enabled: bool | None = None,
    publisher_id: str | None = None,
    slot_id: str | None = None,
    effective_date: str | None = None,
) -> AdsConfig:
    """Check the ads settings; an argument left out reads the committed value.

    Off returns ``ADS_OFF``, or with a publisher ID the connect-only
    settings, and ignores the slot and date. On, a missing or malformed
    value raises: a typo must not ship a slot that can never fill, and the
    policy must name the day ads began.
    """
    publisher_id = ADSENSE_PUBLISHER_ID if publisher_id is None else publisher_id
    if not (ADS_ENABLED if enabled is None else enabled):
        # Off, a publisher ID alone (owner step 1, before approval) only
        # connects the site to the AdSense account: the meta tag and
        # ads.txt, no script and no unit.
        publisher_id = publisher_id.strip()
        if publisher_id == "":
            return ADS_OFF
        _check_publisher_id(publisher_id)
        return AdsConfig(False, publisher_id)
    slot_id = ADSENSE_SLOT_ID if slot_id is None else slot_id
    if effective_date is None:
        effective_date = ADS_EFFECTIVE_DATE
    publisher_id = publisher_id.strip()
    slot_id = slot_id.strip()
    effective_date = effective_date.strip()
    _check_publisher_id(publisher_id)
    if not _SLOT_ID_RE.fullmatch(slot_id):
        raise ValueError(f"AdSense slot ID {slot_id!r} is not the unit's digits")
    if not _DATE_RE.fullmatch(effective_date):
        raise ValueError(
            f"ADS_EFFECTIVE_DATE {effective_date!r} is not a YYYY-MM-DD date"
        )
    return AdsConfig(True, publisher_id, slot_id, effective_date)


def for_build(config: AdsConfig | None, *, analytics: bool) -> AdsConfig:
    """The settings a build uses: ``config``, or the committed ones if None.

    Ads need the analytics build: the no-analytics privacy and about copy
    promises no third-party script at all, so ads are only described
    alongside analytics.
    """
    config = config if config is not None else ads_config()
    if config.enabled and not analytics:
        raise ValueError("ads need the analytics build: set a GA4 measurement ID")
    return config


def install(env: jinja2.Environment, config: AdsConfig) -> dict[str, Any]:
    """Register ``ad_slot()`` for base.html.jinja; return the shared context.

    ``ad_slot()`` returns the slot's settings on a page in ``AD_PAGES`` when
    ads are on, and None everywhere else. A Jinja context's name is the
    template the page rendered, even inside the base template it extends.
    """

    @jinja2.pass_context
    def ad_slot(ctx: jinja2.runtime.Context) -> dict[str, str] | None:
        if not config.enabled or ctx.name not in AD_PAGES:
            return None
        return {
            "client": config.publisher_id,
            "slot": config.slot_id,
            "script_url": f"{ADSENSE_SCRIPT_URL}?client={config.publisher_id}",
        }

    env.globals["ad_slot"] = ad_slot
    return {
        "adsense_account": config.publisher_id,
        "ads_enabled": config.enabled,
        "ads_effective_date": config.effective_date,
    }


def write_files(
    out_dir: Path,
    written: list[Path],
    config: AdsConfig,
    *,
    minify: Callable[[str], str],
) -> None:
    """ads.txt at the site root when there is a publisher ID, and the slot's
    CSS when ads are on. With neither, nothing.

    ``minify`` is site.minify_css, passed in because site imports this module.
    """
    if not config.publisher_id:
        return
    ads_txt = out_dir / "ads.txt"
    ads_txt.write_text(
        f"google.com, {config.ads_txt_publisher}, DIRECT, {GOOGLE_ADS_TXT_CERT_ID}\n",
        encoding="utf-8",
    )
    written.append(ads_txt)
    if not config.enabled:
        return
    css = out_dir / "assets" / "style.css"
    with css.open("a", encoding="utf-8") as f:
        f.write(minify(AD_CSS))
