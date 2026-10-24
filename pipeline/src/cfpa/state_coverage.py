"""Which of the 50 states and DC Trout Truck covers, for ``/states/``.

Each state has one of three statuses, always said in words (the design
system's StateCoverageList):

- **live**: the state has pages in this build (it is in ``snapshot/v2.json``),
  so its card links to them;
- **soon**: a state Trout Truck is adding (``COMING_SOON``) and that has no
  pages in this build yet; the card says "Coming soon" and links nowhere;
- **not covered**: every other state. Its card links to that state wildlife
  agency's own stocking page (``AGENCY_LINKS``) and carries nothing else:
  Trout Truck never copies, counts or summarizes a state it does not cover.

A coming-soon state turns live by itself on the first build that has its
pages, so the page never calls a state "coming soon" while linking it in the
table above.

Every link in ``AGENCY_LINKS`` is on the agency's own domain and was checked
on ``LINKS_CHECKED`` with one short, polite GET that honored the host's
robots.txt. Where no
stocking page could be confirmed, the entry links the agency's home page and
says so (``homepage_only``).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .states import SOURCES

LINKS_CHECKED = "2026-10-23"

# Being added: each has a reader in cfpa.states already.
COMING_SOON: frozenset[str] = frozenset({"MA", "MI", "NY"})

STATE_NAMES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


@dataclasses.dataclass(frozen=True)
class AgencyLink:
    agency: str
    short: str
    url: str
    # True when no stocking page could be confirmed and the link is the
    # agency's home page instead.
    homepage_only: bool = False


# Every state with no reader in cfpa.states. Checked LINKS_CHECKED; a comment
# marks each entry whose link could not be confirmed as a stocking page.
AGENCY_LINKS: dict[str, AgencyLink] = {
    "AK": AgencyLink(
        "Alaska Department of Fish and Game",
        "ADF&G",
        "https://www.adfg.alaska.gov/index.cfm?adfg=fishingSportStockingHatcheries.main",
    ),
    # No stocking page confirmed; the agency page loads.
    "AL": AgencyLink(
        "Alabama Department of Conservation and Natural Resources, Wildlife and Freshwater Fisheries Division",
        "ADCNR",
        "https://www.outdooralabama.com/",
        homepage_only=True,
    ),
    "AR": AgencyLink(
        "Arkansas Game and Fish Commission",
        "AGFC",
        "https://www.agfc.com/fishing/where-to-fish/family-and-community-fishing-program-stocked-ponds/",
    ),
    # Not verified: Blocks automated fetch: robots.txt returns 403 to our user agent, so no page was fetched. Stocking page URL not confirmed; homepage listed unverified.
    "AZ": AgencyLink(
        "Arizona Game and Fish Department",
        "AZGFD",
        "https://www.azgfd.com/",
        homepage_only=True,
    ),
    "CO": AgencyLink(
        "Colorado Parks and Wildlife",
        "CPW",
        "https://cpw.state.co.us/fishing/stocking-report",
    ),
    "CT": AgencyLink(
        "Connecticut Department of Energy and Environmental Protection",
        "CT DEEP",
        "https://portal.ct.gov/deep/fishing/general-information/trout-stocking-maps",
    ),
    # No stocking page confirmed; the agency page loads.
    "DC": AgencyLink(
        "District of Columbia Department of Energy and Environment",
        "DOEE",
        "https://doee.dc.gov/service/fishdc",
        homepage_only=True,
    ),
    "DE": AgencyLink(
        "Delaware Department of Natural Resources and Environmental Control, Division of Fish and Wildlife",
        "DNREC",
        "https://dnrec.delaware.gov/fish-wildlife/fishing/freshwater-trout/",
    ),
    "FL": AgencyLink(
        "Florida Fish and Wildlife Conservation Commission",
        "FWC",
        "https://myfwc.com/fishing/freshwater/stocking/",
    ),
    "GA": AgencyLink(
        "Georgia Department of Natural Resources, Wildlife Resources Division",
        "Georgia WRD",
        "https://georgiawildlife.com/fishing/trout",
    ),
    # No stocking page confirmed; the agency page loads.
    "HI": AgencyLink(
        "Hawaii Department of Land and Natural Resources, Division of Aquatic Resources",
        "DLNR DAR",
        "https://dlnr.hawaii.gov/dar/",
        homepage_only=True,
    ),
    # No stocking page confirmed; the agency page loads.
    "IA": AgencyLink(
        "Iowa Department of Natural Resources",
        "Iowa DNR",
        "https://www.iowadnr.gov/",
        homepage_only=True,
    ),
    "ID": AgencyLink(
        "Idaho Department of Fish and Game",
        "IDFG",
        "https://idfg.idaho.gov/ifwis/fishingplanner/stocking/",
    ),
    # No stocking page confirmed; the agency page loads.
    "IL": AgencyLink(
        "Illinois Department of Natural Resources",
        "Illinois DNR",
        "https://dnr.illinois.gov/",
        homepage_only=True,
    ),
    "IN": AgencyLink(
        "Indiana Department of Natural Resources, Division of Fish and Wildlife",
        "Indiana DNR",
        "https://www.in.gov/dnr/fish-and-wildlife/fishing/indiana-fish-stocking/",
    ),
    # Not verified: Blocks automated fetch: robots.txt returns 403. Likely trout program page https://ksoutdoors.gov/Fishing/Special-Fishing-Programs-for-You/Trout-Fishing-Program was not confirmed.
    "KS": AgencyLink(
        "Kansas Department of Wildlife and Parks",
        "KDWP",
        "https://ksoutdoors.gov/",
        homepage_only=True,
    ),
    "KY": AgencyLink(
        "Kentucky Department of Fish and Wildlife Resources",
        "KDFWR",
        "https://fw.ky.gov/Fish/Pages/Fish_Stocking.aspx",
    ),
    # Not verified: Louisiana has no trout stocking. Blocks automated fetch: robots.txt returns 403; fish stocking page not confirmed.
    "LA": AgencyLink(
        "Louisiana Department of Wildlife and Fisheries",
        "LDWF",
        "https://www.wlf.louisiana.gov/",
        homepage_only=True,
    ),
    "MD": AgencyLink(
        "Maryland Department of Natural Resources",
        "Maryland DNR",
        "https://dnr.maryland.gov/fisheries/pages/trout/stocking.aspx",
    ),
    # Not verified: Blocks automated fetch: robots.txt on maine.gov returns 403. Likely stocking report page https://www.maine.gov/ifw/fishing-boating/fishing/fishing-resources/stocking-report.html was not confirmed.
    "ME": AgencyLink(
        "Maine Department of Inland Fisheries and Wildlife",
        "MDIFW",
        "https://www.maine.gov/ifw/",
        homepage_only=True,
    ),
    # No stocking page confirmed; the agency page loads.
    "MN": AgencyLink(
        "Minnesota Department of Natural Resources",
        "Minnesota DNR",
        "https://www.dnr.state.mn.us/fishing/index.html",
        homepage_only=True,
    ),
    "MO": AgencyLink(
        "Missouri Department of Conservation",
        "MDC",
        "https://mdc.mo.gov/fishing/species/trout",
    ),
    # Not verified: Mississippi has no trout stocking. TLS certificate chain failed verification (incomplete chain), so nothing was fetched; fish stocking page not confirmed.
    "MS": AgencyLink(
        "Mississippi Department of Wildlife, Fisheries, and Parks",
        "MDWFP",
        "https://www.mdwfp.com/",
        homepage_only=True,
    ),
    "MT": AgencyLink(
        "Montana Fish, Wildlife & Parks",
        "Montana FWP",
        "https://fwp.mt.gov/fish/stocking.html",
    ),
    "NC": AgencyLink(
        "North Carolina Wildlife Resources Commission",
        "NCWRC",
        "https://www.ncwildlife.gov/fish/hatcheries-and-stocking-public-waters",
    ),
    # No stocking page confirmed; the agency page loads.
    "ND": AgencyLink(
        "North Dakota Game and Fish Department",
        "NDGF",
        "https://gf.nd.gov/fishing",
        homepage_only=True,
    ),
    # Not verified: Blocks automated fetch: robots.txt returns 403; trout stocking page not confirmed.
    "NE": AgencyLink(
        "Nebraska Game and Parks Commission",
        "Nebraska Game and Parks",
        "https://outdoornebraska.gov/",
        homepage_only=True,
    ),
    # Not verified: Blocks automated fetch: robots.txt returns 403. Likely page https://www.wildlife.nh.gov/fishing-new-hampshire/trout-stocking-report was not confirmed.
    "NH": AgencyLink(
        "New Hampshire Fish and Game Department",
        "NHFG",
        "https://www.wildlife.nh.gov/",
        homepage_only=True,
    ),
    # Not verified: Pages return 200 but with no readable content to scripts (likely bot protection), so nothing could be verified. Candidate https://dep.nj.gov/njfw/fishing/freshwater/trout-stocking-information/ not confirmed.
    "NJ": AgencyLink(
        "New Jersey Department of Environmental Protection, Division of Fish and Wildlife",
        "NJ Fish & Wildlife",
        "https://dep.nj.gov/njfw/",
        homepage_only=True,
    ),
    "NM": AgencyLink(
        "New Mexico Department of Wildlife",
        "NMDW",
        "https://wildlife.dgf.nm.gov/fishing/weekly-report/",
    ),
    # Not verified: robots.txt disallows all user agents except major search engines, so no page was fetched; stocking page not confirmed.
    "NV": AgencyLink(
        "Nevada Department of Wildlife",
        "NDOW",
        "https://www.ndow.org/",
        homepage_only=True,
    ),
    # Not verified: Every ODNR URL tried, including the homepage, returned 404 to automated requests; stocking page not confirmed.
    "OH": AgencyLink(
        "Ohio Department of Natural Resources, Division of Wildlife",
        "ODNR",
        "https://ohiodnr.gov/",
        homepage_only=True,
    ),
    # No stocking page confirmed; the agency page loads.
    "OK": AgencyLink(
        "Oklahoma Department of Wildlife Conservation",
        "ODWC",
        "https://www.wildlifedepartment.com/fishing",
        homepage_only=True,
    ),
    "OR": AgencyLink(
        "Oregon Department of Fish and Wildlife",
        "ODFW",
        "https://myodfw.com/fishing/species/trout/stocking-schedule",
    ),
    "PA": AgencyLink(
        "Pennsylvania Fish and Boat Commission",
        "PFBC",
        "https://www.pa.gov/agencies/fishandboat/fishing/stocking/trout-stocking",
    ),
    # Not verified: Blocks automated fetch: dem.ri.gov returns 403 (homepage and the candidate https://dem.ri.gov/natural-resources-bureau/fish-wildlife/freshwater-fisheries/trout-stocking, which was not confirmed).
    "RI": AgencyLink(
        "Rhode Island Department of Environmental Management",
        "RIDEM",
        "https://dem.ri.gov/",
        homepage_only=True,
    ),
    # No stocking page confirmed; the agency page loads.
    "SC": AgencyLink(
        "South Carolina Department of Natural Resources",
        "SCDNR",
        "https://www.dnr.sc.gov/",
        homepage_only=True,
    ),
    # No stocking page confirmed; the agency page loads.
    "SD": AgencyLink(
        "South Dakota Game, Fish and Parks",
        "SD GFP",
        "https://gfp.sd.gov/",
        homepage_only=True,
    ),
    "TX": AgencyLink(
        "Texas Parks and Wildlife Department",
        "TPWD",
        "https://tpwd.texas.gov/fishboat/fish/management/stocking/trout_stocking.phtml",
    ),
    "UT": AgencyLink(
        "Utah Division of Wildlife Resources",
        "Utah DWR",
        "https://dwrapps.utah.gov/fishstocking/Fish",
    ),
    "VA": AgencyLink(
        "Virginia Department of Wildlife Resources",
        "Virginia DWR",
        "https://dwr.virginia.gov/fishing/trout-stocking-schedule/",
    ),
    "VT": AgencyLink(
        "Vermont Fish and Wildlife Department",
        "Vermont Fish & Wildlife",
        "https://vtfishandwildlife.com/fish/fish-stocking",
    ),
    "WA": AgencyLink(
        "Washington Department of Fish and Wildlife",
        "WDFW",
        "https://wdfw.wa.gov/fishing/reports/stocking/trout-plants",
    ),
    "WI": AgencyLink(
        "Wisconsin Department of Natural Resources",
        "Wisconsin DNR",
        "https://dnr.wisconsin.gov/topic/Fishing/stocking",
    ),
    "WV": AgencyLink(
        "West Virginia Division of Natural Resources",
        "WVDNR",
        "https://wvdnr.gov/fishing/fish-stocking/",
    ),
    "WY": AgencyLink(
        "Wyoming Game and Fish Department",
        "WGFD",
        "https://wgfapps.wyo.gov/FishStock/FishStock",
    ),
}


def agency_link(code: str) -> AgencyLink:
    """The outbound link for a state that is not covered. A state with a
    reader in cfpa.states links the page that reader uses; every other state
    is in AGENCY_LINKS (a test checks that none is missing)."""
    if code in AGENCY_LINKS:
        return AGENCY_LINKS[code]
    src = SOURCES[code]
    return AgencyLink(src.agency_name, src.agency_short_name, src.source_url)


def coverage(live: dict[str, str]) -> list[dict[str, Any]]:
    """One entry per state and DC, alphabetical by name. ``live`` maps each
    state code with pages in this build to its URL relative to /states/."""
    out: list[dict[str, Any]] = []
    for code, name in sorted(STATE_NAMES.items(), key=lambda kv: kv[1]):
        entry: dict[str, Any] = {"code": code, "name": name}
        if code in live:
            entry.update(status="live", href=live[code])
        elif code in COMING_SOON:
            entry.update(status="soon")
        else:
            link = agency_link(code)
            entry.update(
                status="none",
                agency=link.agency,
                short=link.short,
                url=link.url,
                homepage_only=link.homepage_only,
            )
        out.append(entry)
    return out
