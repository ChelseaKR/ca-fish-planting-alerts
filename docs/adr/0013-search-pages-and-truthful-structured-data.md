# 0013. Search: county pages, and structured data that states only what the schedule says

Status: Proposed
Date: 2026-09-18
Deciders: Chelsea Kelly-Reif

## Context

The website is how people find Trout Truck (`docs/DECISIONS.md` 0001).
Anglers search for things like "<lake> trout stocking", "<county> fish
plants this week" and "CDFW planting schedule". PR 14 added titles with the
county, canonical URLs and a sitemap whose `<lastmod>` comes from the data.
An audit of the live site on 2026-09-18
(`https://chelseakr.github.io/ca-fish-planting-alerts/`, 385 water pages)
found these gaps:

- **No page per county.** A county search had nothing to land on. Every
  water page linked only back to the home page, and never to another water.
- **Titles and wording.** Water titles gave the bare county name
  ("Bass Lake (Siskiyou)"). The three catfish-only park lakes (MacArthur
  Park, Ralph Clark Regional Park and John Anson Ford Park) were titled as
  trout schedules.
- **Absence.** A water with nothing listed this week or later was described
  only by its most recent week. No page said plainly that nothing is
  scheduled now, or that this does not mean there are no fish.
- **No structured data.**
- **robots.txt is never read.** Crawlers request robots.txt only at a
  host's root. The site's own file is at `/ca-fish-planting-alerts/robots.txt`,
  and `https://chelseakr.github.io/robots.txt` returns 404, which crawlers
  treat as "allow everything". So the `Sitemap:` line in it is never seen,
  and Google learns about the sitemap only if it is submitted in Search
  Console.
- **No Search Console property.** A github.io project site cannot be a
  Domain property, because that needs a DNS TXT record on `github.io`. It can
  only be a URL-prefix property, verified with an HTML file or a meta tag.

## Decision

### Pages and wording

- **County pages** at `/county/<county>/` for every county with at least
  one water page, plus an index at `/county/` grouped by CDFW region. A
  county page shows what is scheduled there this week, then every water in
  the county with its latest scheduled week (marked "upcoming" when it is
  after the current week) and its number of weeks on record, most recent
  first. The home page links every county page, and every row of its
  this-week tables links the water's county pages. The header gets a
  "By county" link.
- **Water pages.** The title reads
  "<water> (<county> County) <species> planting schedule | Trout Truck".
  The h1 reads "... <species> stocking schedule and history", so the page
  carries both of the words people search with. The meta description gives
  the county, "stocking", and the week that answers the question (this
  week, the next week, or the last week with "none listed this week or
  later"). The species wording comes from the data: "trout", "catfish" or
  "trout and catfish".
- **Internal links come from the data only.** A water page links its county
  pages and lists every other water that shares one of its counties. The
  snapshot has no location for any water, so the page never says "nearby":
  a county is the only nearness the data supports. A visible breadcrumb
  reads Trout Truck > Counties > <first county> > <water>, going through the
  first county because that is the county the snapshot takes the region
  from.
- **Absence is said plainly.** A water with nothing listed this week or
  later says: "Nothing is on CDFW's schedule for <water> this week or later.
  That means no plant is scheduled right now, not that there are no fish."
  A county with nothing this week says the same. No page anywhere says "no
  fish" in any other form, and a test enforces that.

### Structured data (schema.org JSON-LD)

One `<script type="application/ld+json">` block per page, built from the
snapshot only. `tojson` escapes `<`, `>` and `&`, so no water name can close
the element. Validated on 2026-09-18 with validator.schema.org (0 errors,
0 warnings on the home, about, county index, county and water pages) and
checked against the schema.org vocabulary (every type exists, and every
property is valid on its type).

| Page | Types | Why |
|---|---|---|
| Home | `WebSite` (name, url, description, language) | Names the site. Google reads it for site names only on a domain or subdomain home page, never a subdirectory, so on github.io it does nothing yet. It is still true, and it starts working once the site has its own domain. No `potentialAction`: Google retired the sitelinks search box, and the site has no search. |
| Water | `WebPage` about a `BodyOfWater`, plus `BreadcrumbList` | `BodyOfWater` (a `Place`) is true of every CDFW planting water, whether lake, reservoir, creek or river section. The subtypes (`LakeBodyOfWater`, `Reservoir`, `RiverBodyOfWater`) would be guesses from the name, and a name does not say whether a "lake" is dammed. It carries `containedInPlace` (the county `AdministrativeArea`, inside the `State` California), `hasMap` (CDFW's own map link for the water), `identifier` (the CDFW stock ID) and `alternateName` (CDFW's other spellings). It has no `geo` and no `address`, because the snapshot has no location. `BreadcrumbList` mirrors the visible breadcrumb name for name. It is the one type here that Google shows as a rich result. |
| County, county index | `CollectionPage` about the county (or California), plus `BreadcrumbList` | These pages are lists of links to waters. `CollectionPage` says that and nothing more. `ItemList` was not used: Google's list results cover only recipes, courses, restaurants and movies. |
| About | `Dataset` | Describes the compiled schedule history: name, description, `url` (`/about/#data`), `isAccessibleForFree`, `creator` (Trout Truck), `keywords`, `variableMeasured`, `spatialCoverage` (California), `temporalCoverage` (the earliest scheduled week to the latest), `dateModified` (the day the data last changed, the same date as the home page's lastmod), and `distribution` (`snapshot/v1.json`). CDFW is credited through `isBasedOn` (the schedule, created by CDFW as a `GovernmentOrganization`, with its terms, CDFW's Conditions of Use) and `creditText` (the attribution every page carries). |
| Privacy, support, 404 | none | Nothing on them to describe. |

What was ruled out:

- **`Event`, for any planting.** CDFW publishes a week, never a day or a
  time, and says every plant is subject to change. An `Event` needs a
  `startDate`. Google shows event dates in results, so an event on the
  Sunday of the week would state a day CDFW never gave, and imply a
  confirmed occasion. The `.ics` feeds already give each week as an
  all-day, week-long span labelled "scheduled". A test forbids `Event`,
  and forbids `startDate`, `endDate`, `doorTime` and `eventStatus`,
  anywhere in the structured data.
- **`TouristAttraction`.** It is a claim about the place that the data does
  not make: a section of creek is not a tourist attraction. Google shows no
  rich result for it either.
- **`geo` coordinates.** The snapshot's `location` is null for every water.
  Geocoding a name like "Deer Creek" could put a pin on the wrong one of
  the two (in Tehama and Tulare counties).
- **A CC-BY `license` on the Dataset.** CC-BY is the licence of a
  different CDFW product, the Fishing Guide dataset on data.ca.gov
  (`docs/LICENSES-AND-ATTRIBUTION.md`). The planting schedule falls under
  CDFW's Conditions of Use, and the Dataset cites that through
  `isBasedOn.license`. The licence for Trout Truck's own compilation is
  the owner's choice. It stays unset until she makes it:
  `DATASET_LICENSE_URL` in `pipeline/src/cfpa/site.py`, where `""` means
  the markup states no licence. Google lists `license` as recommended, not
  required, so Search Console may show a warning for it until then.

A test holds the set of types to exactly the list above, so adding a type
means adding it here first.

### Sitemap and robots.txt

- The sitemap lists every indexable page: home, `/county/`, about, privacy,
  support, every county page and every water page. A test checks that the
  sitemap and the built pages match exactly.
- `<lastmod>` is the day a page's substance last changed, never the build
  date. For a water page, that is the day a plant was first listed or
  removed; the Sunday of the current week, if the water has a listing close
  enough to that week that the rollover changes its wording; or the day a
  water sharing one of its counties first appeared, because it links to
  that water. Other waters are listed by name only, so their new weeks do
  not change the page. For a county page, it is the latest of its waters'
  own dates. For `/county/`, it is the day any water first appeared. For
  the home page, it is the current week's Sunday or any water's date,
  whichever is later. The "last checked" line changes on every run, and it
  is deliberately not counted, because it says when the data was read, not
  that it changed. For the same reason, no sentence outside that line
  prints the current week's date unless the page has a listing near that
  week. A test runs the two real fixtures in order and checks that only
  the pages whose data changed move to the new date.
- robots.txt is kept, with a comment in `site.py` that explains the
  host-root rule. It takes effect as written once `SITE_BASE_URL` is a
  domain root. Until then, the sitemap is submitted in Search Console
  (`docs/SEARCH-CONSOLE.md`).

### Search Console verification

`GOOGLE_SITE_VERIFICATION` in `pipeline/src/cfpa/site.py` holds the
`content` value of Search Console's HTML tag, following the precedent set
for the GA4 measurement ID (`docs/DECISIONS.md` 0011): the value is public
and appears in the HTML, so it is committed rather than stored as a secret.
It is empty in this change. When it is set, only the home page gets
`<meta name="google-site-verification">`, because the home page is the one
Search Console checks. `cfpa` refuses the run, writing nothing, if the value
is anything but a bare token (for example, the whole pasted `<meta>` tag).
The owner's steps are in `docs/SEARCH-CONSOLE.md`.

## Consequences

- The site grows from 390 pages to about 440 (49 county pages and the
  index on 2026-09-18 data). They go through the same axe, pa11y-ci and
  Lighthouse gates, and `tools/site-checks/run.sh` now adds a county page
  to the Lighthouse set.
- Pages now contain a `<script>` element even when no GA4 ID is set. It is
  a JSON-LD data block, which a browser never runs and which fetches
  nothing, so "no JavaScript runs on this site" stays true. The tests that
  guarded "no `<script>` at all" now tell JSON-LD blocks apart from
  executable scripts, and their negative controls cover a typed
  `<script type="module">` too.
- Water-page titles changed wording. Google re-crawls on its own schedule,
  and results can show the old titles for a while.
- Nothing is verified in Search Console until the owner does it. Until then
  Google finds pages only by crawling links.
