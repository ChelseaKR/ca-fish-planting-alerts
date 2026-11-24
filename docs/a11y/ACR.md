# Trout Truck website: Accessibility Conformance Report

Accessibility Conformance Report (ACR), based on the VPAT® 2.5 Rev WCAG
edition.

VPAT® is a registered service mark of the Information Technology Industry
Council (ITI).

## Product information

- **Name of product:** Trout Truck website (trouttruck.com), built by this
  repository's site generator (`pipeline/src/cfpa/site.py` and
  `pipeline/src/cfpa/templates/`).
- **Version:** the site as built from `main` at `1b6745c`, plus
  the two branches already waiting to merge that change a page this report
  covers: `feat/ca-datemodified-ln-link-2026-11` (a "Toxic algae advisories"
  row on paired California water pages, ADR 0077) and `seo/readable-dates`
  (dates written out in the home heading and in descriptions). The site has
  no version number of its own (#3); the commit is the version.
- **Report date:** 2026-11-19.
- **Description:** a free, static website that lists each state wildlife
  agency's published trout planting and stocking schedule: a home page for
  this week in California, county, region, species and week pages, one page
  per water, a hub and water pages for each other state carried (Tennessee,
  Massachusetts, Michigan, New York), a page listing every state, guides,
  gear and gift pages, and the about, privacy, terms, support, open data and
  not-found pages. A water page offers a calendar subscription (Apple
  Calendar, Google Calendar, or an `.ics` file) and, where the build turns it
  on, a browser notification for that water.
- **Contact:** the support page, <https://trouttruck.com/support/>, or an
  issue in this repository.
- **Evaluated by:** an automated and code-reading audit run on 2026-11-19
  for the owner. No assistive-technology user took part (see "What this
  report does not claim").

## What this report does not claim

Read this before the tables.

- **No human screen-reader walkthrough has been done yet.** Every row
  marked "Supports" rests on the evidence named in its remarks: axe-core,
  pa11y-ci and Lighthouse over the built pages, keyboard and layout checks
  run in headless Chrome, and reading the templates, stylesheet and
  scripts. Where the criterion is about what assistive technology announces
  (names, roles, states, reading order, status messages), the row says so
  and points to the step in Appendix A that still needs a person with NVDA
  or VoiceOver. Until that walkthrough is done and committed under
  `docs/a11y/`, this report is not a claim that the site has been tested
  with a screen reader, and the site is not described as "WCAG conformant"
  (`docs/standards/ACCESSIBILITY-STANDARD.md` §2.0, §2.1).
- **The remarks describe the site after branch `a11y/acr-2026-11` is merged
  and deployed.** Each fix that branch makes is named in the row it
  changes. Until it is live, those rows describe the next deploy, not
  trouttruck.com today.
- **The apps are out of scope.** The iOS app's App Store submission was
  rejected under guideline 4.3 and it is not being resubmitted, so it is not
  covered here, although its `AccessibilityAuditUITests` remain in
  `ios/`. The Android app (`android/`) is not covered either; each app
  would need its own report.
- **Pages and content of other sites are out of scope:** CDFW's and the
  other agencies' pages, Google Calendar, Apple Calendar's subscription
  dialog, OpenStreetMap, Amazon (gear and gift links), Ko-fi, Lake Notice,
  and the browser's own permission prompts. See "Third-party content".

## Summary

| Level | Supports | Partially Supports | Does Not Support | Not Applicable | Not Evaluated |
|---|---|---|---|---|---|
| A (31 criteria in WCAG 2.2) | 17 | 0 | 0 | 14 | 0 |
| AA (24 criteria in WCAG 2.2) | 15 | 0 | 0 | 9 | 0 |

4.1.1 Parsing, listed for WCAG 2.0 and 2.1 only, is also "Supports".

Five "Supports" rows rest on code and accessibility-tree evidence and still
need a person with a screen reader to confirm what is announced: 1.3.1,
1.3.2, 2.4.3, 4.1.2 and 4.1.3. Their remarks say "Human check pending" and
name the step in Appendix A.

The audit found one defect, fixed on branch `a11y/acr-2026-11`: the skip
link did not move keyboard focus (2.4.1). Automated tools reported no
violation at any impact, and no "needs review" item, on any audited page.

## Evaluation methods used

All runs used local builds of the site from the repository's own CDFW
fixtures and the four other states' fixtures (about 1,550 pages each), with
the gift guide and the browser-notification control turned on, so every
page family and control in production was present. Two CDFW fixtures were
used so the home page was audited both ways it renders: a week with waters
listed (with "Sort by closest to me") and a week with none yet. Google
Analytics requests were blocked in every browser run.

1. **The repository's automated gates** (`tools/site-checks/run.sh`, the
   same script CI runs in `site-checks.yml`): axe-core 4.13.0 through
   `@axe-core/puppeteer` in Chrome for Testing 156, with the WCAG 2.0, 2.1
   and 2.2 A and AA tags, on every California page and a sample of the
   other states' water pages;
   pa11y-ci 5 with the axe runner at WCAG2AA; the 320 CSS px reflow check
   with the site's fonts and with a wide font; Lighthouse accessibility on
   four representative pages, three runs each. Result on this branch: 136
   pages checked (of 1,543 built), axe 0 problems, reflow 0 problems in
   both font passes, pa11y-ci 136 of 136 passed, every Lighthouse
   assertion (accessibility at least 0.90) passed.
2. **An extended audit of 29 representative pages, one or more per
   template, in light and dark color schemes** (58 page views): every axe
   result including `minor` and "needs review" items, the measured contrast
   of every text node axe checked, a full Tab walk recording each stop's
   focus outline and whether anything covered it, pointer target sizes,
   heading order, landmarks, and the WCAG 1.4.12 text-spacing overrides at
   320 and 1280 CSS px. Pages: home (both ways); `/states/`; the Tennessee,
   Massachusetts, Michigan and New York hubs and one water page each;
   `/county/` and one county; one region; one species; the week index and
   one week; two California water pages (one with the Lake Notice row, one
   thin page); `/gifts/`; `/gear/`; about; privacy; terms; support; open
   data; the guides index and one guide; the not-found page.
3. **Keyboard-only runs of every interactive control:** the skip link,
   "Sort by closest to me" (with location allowed and refused), "Alert me
   about this water" (with notifications allowed), and the footer's
   analytics opt-out;
   where focus lands after each press and what the status line says.
4. **Forced colors** (Windows High Contrast emulation), **200% text size**
   and a search for fixed or sticky elements that could cover focus.
5. **Code reading** of every template, `style.css`, `closest.js`,
   `push.js` and the analytics tag, and the design-token contrast pairs
   computed from the stylesheet (listed under 1.4.3 and 1.4.11).

## Applicable standards and guidelines

| Standard / guideline | Included in report |
|---|---|
| Web Content Accessibility Guidelines 2.0 | Level A (Yes), Level AA (Yes), Level AAA (No) |
| Web Content Accessibility Guidelines 2.1 | Level A (Yes), Level AA (Yes), Level AAA (No) |
| Web Content Accessibility Guidelines 2.2 | Level A (Yes), Level AA (Yes), Level AAA (No) |

WCAG 2.2 includes every WCAG 2.0 and 2.1 Level A and AA success criterion
except 4.1.1 Parsing, which 2.2 removed, so the tables below cover 2.0 and
2.1 as well. 4.1.1 is listed for readers who need a 2.0 or 2.1 answer.
Revised Section 508 and EN 301 549 chapters are not reported separately.

## Terms

- **Supports:** the functionality of the product has at least one method
  that meets the criterion without known defects or meets with equivalent
  facilitation.
- **Partially Supports:** some functionality of the product does not meet
  the criterion.
- **Does Not Support:** the majority of product functionality does not meet
  the criterion.
- **Not Applicable:** the criterion is not relevant to the product.
- **Not Evaluated:** the product has not been evaluated against the
  criterion. Used only for WCAG Level AAA, which this report does not cover.

## Table 1: Success Criteria, Level A

| Criteria | Conformance Level | Remarks and Explanations |
|---|---|---|
| 1.1.1 Non-text Content | Supports | No page content is an image: the pages are text, tables and lists. The breadcrumb separator is CSS-generated with empty alternative text (`content: "\203A" / ""`). The App Store badge image (alt "Download on the App Store") renders only when `APP_STORE_LIVE` is on, which it is not. Share-card images exist only in `og:image` metadata, with `og:image:alt`. axe `image-alt`, `svg-img-alt` and `role-img-alt` found nothing to fail. |
| 1.2.1 Audio-only and Video-only (Prerecorded) | Not Applicable | The site has no audio or video. |
| 1.2.2 Captions (Prerecorded) | Not Applicable | No video with audio. |
| 1.2.3 Audio Description or Media Alternative (Prerecorded) | Not Applicable | No video. |
| 1.3.1 Info and Relationships | Supports | Verified in the DOM and by axe: one `h1` per page and no skipped heading level on the 29 audited pages; every data table has a caption (visually hidden) and `th scope="col"`; the `/states/` table keeps explicit table roles when it stacks on a phone; "About this water" and the status block are `dl` term and definition pairs; banner, primary navigation, breadcrumb navigation, main and contentinfo landmarks on every page. Human check pending: that NVDA and VoiceOver announce table headers and definition-list pairs as intended (Appendix A, steps 2, 3 and 5). |
| 1.3.2 Meaningful Sequence | Supports | Source order is reading order on every template; no CSS reorders content (no `order`, no absolute positioning of content except the skip link and visually hidden captions). The stacked `/states/` rows add their column labels with empty alternative text, so the order read is the header once, then each value. Human check pending (Appendix A, step 5). |
| 1.3.3 Sensory Characteristics | Supports | Instructions name the control they mean ("the calendar options above", "press 'Alert me about this water'"); none relies on shape, color, size or position alone. |
| 1.4.1 Use of Color | Supports | Links in text are underlined (the stylesheet never removes the underline from a content link). The status badge always carries its word ("This week", "Next week", "None scheduled yet") and its three looks also differ in fill and border style. "Schedule changed" rows say so in words. |
| 1.4.2 Audio Control | Not Applicable | No audio. |
| 2.1.1 Keyboard | Supports | Every control is a native link or `<button>`. Keyboard-only runs completed each interactive task: the skip link (fixed on this branch, see 2.4.1), "Sort by closest to me" (Enter, with location allowed and refused), "Alert me about this water" (Enter; headless Chrome has no push service, so the run reached "Setting it up" and no further), and the footer's analytics opt-out (Enter, then Space to undo). Nothing needs a pointer. "Stop these notifications" is a native button but was not reached in a run (Appendix A, step 2). |
| 2.1.2 No Keyboard Trap | Supports | The Tab walk on each audited page reached the last control and left the page without being held; no script handles Tab or Escape. |
| 2.1.4 Character Key Shortcuts | Not Applicable | The site defines no keyboard shortcuts. |
| 2.2.1 Timing Adjustable | Not Applicable | No time limits. (The location request behind "Sort by closest to me" times out after 20 seconds only once the browser has the visitor's permission and is looking up the position; the visitor can press again.) |
| 2.2.2 Pause, Stop, Hide | Not Applicable | Nothing moves, blinks, scrolls or updates on its own. The stylesheet has no animations or transitions. |
| 2.3.1 Three Flashes or Below Threshold | Not Applicable | Nothing flashes. |
| 2.4.1 Bypass Blocks | Supports | Every page starts with a "Skip to main content" link (visible on focus) to `<main id="main">`, and has banner, navigation, main and contentinfo landmarks and a heading structure. **Fixed on this branch:** before it, in Chrome, Enter on the skip link scrolled to main but left focus behind, and the next Tab went to the header's first link, so the link skipped nothing for a keyboard user. `<main>` now has `tabindex="-1"` (not a Tab stop), so the next Tab after the skip link lands inside main; it draws no ring of its own. Test: `pipeline/tests/test_site_skip_link_target.py`. |
| 2.4.2 Page Titled | Supports | Every one of the 1,534 built pages has a `<title>`, and no two are the same; each names the water, county, state or topic and the site. |
| 2.4.3 Focus Order | Supports | Focus follows source order, which is reading order; no positive `tabindex`. After "Sort by closest to me" focus stays on the button; after "Alert me about this water" focus moves to the words that answer the press, or back to the button when it can be pressed again (both since PR 180). Human check pending for what is announced at each step (Appendix A, steps 1 and 2). |
| 2.4.4 Link Purpose (In Context) | Supports | Link text names its destination ("Fresno County", "View Diaz Lake on CDFW's map", "Apple Calendar (iPhone, iPad, Mac): subscribe", "Diaz Lake on Lake Notice"). Two read with their sentence: "View on map" is followed by "(opens OpenStreetMap)", and the footer's source link text is the source's own address. |
| 2.5.1 Pointer Gestures | Not Applicable | No multipoint or path-based gestures; the site has no map or carousel of its own. |
| 2.5.2 Pointer Cancellation | Supports | Only native links and buttons, which act on release (the `click` event). No `mousedown` or `touchstart` handlers. |
| 2.5.3 Label in Name | Supports | No control has an `aria-label` that differs from its visible text; every button's and link's accessible name is its visible words (axe `label-content-name-mismatch` found none). The one `aria-label` on a control container (the ad slot) is in code that is off (ADR 0040). |
| 2.5.4 Motion Actuation | Not Applicable | Nothing responds to device motion. |
| 3.1.1 Language of Page | Supports | `<html lang="en">` on every built page. |
| 3.2.1 On Focus | Supports | Focus never opens, submits or moves anything. Verified by the Tab walks. |
| 3.2.2 On Input | Not Applicable | The site has no form fields, checkboxes or selects. Its buttons act only when pressed. |
| 3.2.6 Consistent Help | Supports | The help mechanism is the footer's "support" link (with "about & attribution" and "privacy"), in the same place and the same order in every page's footer, California and other states alike. No page offers help in another place. |
| 3.3.1 Error Identification | Not Applicable | No input the visitor can get wrong. When the browser cannot share a location or set up a notification, the status line says so in words ("Your browser did not share your location, so the list is unchanged.") |
| 3.3.2 Labels or Instructions | Not Applicable | No form fields. |
| 3.3.7 Redundant Entry | Not Applicable | No process asks for information. |
| 4.1.1 Parsing (WCAG 2.0 and 2.1 only) | Supports | Removed in WCAG 2.2. The WCAG 2.1 errata (2023) say content in HTML is considered to meet it. The templates are autoescaped Jinja with no duplicate `id` on any audited page (axe `duplicate-id-aria` passed). |
| 4.1.2 Name, Role, Value | Supports | Native elements throughout. The calendar box is a `role="group"` named by its heading; "Sort by closest to me" reports busy with `aria-disabled` and keeps focus; the notification control shows one view at a time with `hidden`; the breadcrumb's current page has `aria-current="page"`. axe found no name, role or value failure. Human check pending: the group name, the busy state, and each notification view as announced (Appendix A, steps 1 and 2). |

## Table 2: Success Criteria, Level AA

| Criteria | Conformance Level | Remarks and Explanations |
|---|---|---|
| 1.2.4 Captions (Live) | Not Applicable | No live media. |
| 1.2.5 Audio Description (Prerecorded) | Not Applicable | No video. |
| 1.3.4 Orientation | Supports | No orientation lock; every page works in portrait and landscape. |
| 1.3.5 Identify Input Purpose | Not Applicable | No fields collect information about the visitor. |
| 1.4.3 Contrast (Minimum) | Supports | Lowest text contrast axe measured on the audited pages: 6.67:1 in light and 8.51:1 in dark. Design-token pairs from the stylesheet, light / dark: body text on page 16.32 / 15.85; muted text on page 7.81 / 10.29, on table stripes 7.29 / 9.75, on the footer 7.05 / 9.38, on cards 7.16 / 9.25; links on page 7.95 / 10.74, on cards 7.28 / 9.65; visited links on page 10.16 / 9.73; masthead text 10.48 / 13.13; site name (gold) on masthead 6.68 / 8.52; calendar buttons 7.95 / 10.74; "Next week" badge 9.44 / 9.82. |
| 1.4.4 Resize Text | Supports | Sizes are in `rem`; the viewport meta allows zoom. With the root text size at 200%, no content was cut off and nothing needed sideways scrolling beyond the reflow below. |
| 1.4.5 Images of Text | Not Applicable | No images of text in page content (the App Store badge is off). |
| 1.4.10 Reflow | Supports | The repository gate checks every built California page, every state hub and `/states/`, and 12 water pages per other state, at 320 CSS px with the site's fonts and with a wide font: none scrolls sideways. Tables become stacked rows or wrap. The audit repeated this on the 28 pages in both color schemes. |
| 1.4.11 Non-text Contrast | Supports | Focus ring against the page, light / dark: 7.95 / 10.74 (gold on the masthead 6.68 / 8.52). Button and card edges (`--border-strong`) 4.37 / 5.43 on the page and 4.01 / 4.88 on cards; the "None scheduled yet" badge's dashed edge 4.37 / 5.43; the calendar buttons' fill against their card 7.28 / 9.65. With forced colors on, the calendar and notification buttons keep a drawn edge (PR 180). Table rules and section dividers are decoration, not needed to understand the content. |
| 1.4.12 Text Spacing | Supports | With the WCAG text-spacing overrides applied (line height 1.5, letter spacing 0.12em, word spacing 0.16em, space after paragraphs 2em), at 320 and at 1280 CSS px, on every audited page in both schemes: no page scrolled sideways and no element cut off its text. |
| 1.4.13 Content on Hover or Focus | Not Applicable | Nothing appears on hover or focus except the skip link, which is the focused control itself, and underlines. No tooltips or `title` popups on content. |
| 2.4.5 Multiple Ways | Supports | A water page is reachable from the home page's tables, its county page, its region and species pages, the week pages, the home page's "Browse by water" list, the breadcrumb trail, and the sitemap. Other states' water pages: from their hub and from `/states/`. |
| 2.4.6 Headings and Labels | Supports | Headings name what follows ("Where Diaz Lake stands on CDFW's schedule", "Planting history", "About this water"); the definition list terms name their values. |
| 2.4.7 Focus Visible | Supports | Links and buttons get a 3 px outline with a 2 px offset in the focus color (gold on the masthead). The Tab walks on all 28 pages in both schemes found every stop with a visible outline (4,640 focus stops in 58 page views), and none hidden or covered. |
| 2.4.11 Focus Not Obscured (Minimum) | Supports | The site has no fixed or sticky header, footer, banner or cookie notice, so nothing can cover the focused control. In the Tab walks every focused control was scrolled into view and was the topmost element at its center. |
| 2.5.7 Dragging Movements | Not Applicable | Nothing is dragged. The "View on map" link opens OpenStreetMap, which is another site. |
| 2.5.8 Target Size (Minimum) | Supports | Header, breadcrumb, footer-row and state-card links keep a 24 px minimum height; the calendar and notification buttons are 44 px tall; the analytics opt-out is 24 px tall (footer row since PR 180). Links inside sentences and table cells are inline and excepted. axe `target-size` passed on every audited page. |
| 3.1.2 Language of Parts | Supports | All text is English. Place and water names in Spanish are proper names, which the criterion excepts. |
| 3.2.3 Consistent Navigation | Supports | The header navigation is the same, in the same order, on every California page ("This week", "By county", "Other states", "About & privacy") and on every page of each other state ("[State] this week", "All states", "About & privacy"). The footer row is the same on every page. |
| 3.2.4 Consistent Identification | Supports | The same function has the same name across the site: "About & privacy", the footer row, the calendar box's three ways in, the status badge words. One difference, noted: the link to `/states/` reads "Other states" from California pages and "All states" from another state's pages, which describe the same page from where the visitor is. |
| 3.3.3 Error Suggestion | Not Applicable | No input errors. |
| 3.3.4 Error Prevention (Legal, Financial, Data) | Not Applicable | No transactions, and no data the visitor submits. (Affiliate links go to Amazon, which is out of scope.) |
| 3.3.8 Accessible Authentication (Minimum) | Not Applicable | No sign-in of any kind. |
| 4.1.3 Status Messages | Supports | "Sort by closest to me" reports in a `role="status"` line; the notification control has a `role="status"` `aria-live="polite"` line that stays in the page while empty and moves focus to the words that answer a press; the analytics opt-out reports in a `role="status"` span. Verified in keyboard runs: the closest-to-me line reads "Your browser did not share your location, so the list is unchanged." with focus left on the button, and the opt-out line changes with each press. The notification control's success and failure lines were not reached in headless Chrome (see 2.1.1). Human check pending: that NVDA and VoiceOver speak each message without moving the reading position (Appendix A, steps 1, 2 and 6). |

## Third-party content

The standard asks the ACR to note embedded and third-party content
(`ACCESSIBILITY-STANDARD.md` §2, third-party audit).

- **Google Analytics 4** (DECISIONS 0011) has no visible interface. Its one
  visible part is first-party: the footer's "Opt out of analytics" button
  and its status line, covered above under 2.1.1, 2.5.8 and 4.1.3.
- **Links to other sites** (CDFW and the other agencies, Google Calendar,
  OpenStreetMap, Amazon search results from the gear and gift pages, Ko-fi,
  Lake Notice) leave this site. Their pages are not covered by this report.
- **Apple Calendar's and the browser's own dialogs** (the `webcal:`
  subscription sheet, the location and notification permission prompts)
  belong to the operating system or browser.
- **Display ads** (ADR 0040) are off. If they are turned on, the ad slot
  needs its own audit first: it is marked `aria-hidden="true"`, which must
  not hold a focusable ad link.

## Appendix A: human walkthrough still to do

`ACCESSIBILITY-STANDARD.md` §2.1 requires these three pairings. Record the
result as `docs/a11y/screen-reader-walkthrough-YYYY-MM-DD.md`, pass or fail
per step, with what was heard. Then the "Human check pending" remarks above
can be updated.

| Pairing | Platform |
|---|---|
| NVDA (current) + Firefox or Chrome | Windows |
| VoiceOver + Safari | macOS |
| VoiceOver + Safari | iOS (phone width) |

Use trouttruck.com after this branch is deployed, on a week when the
schedule lists waters.

1. **Home page.** Press Tab once: "Skip to main content" should be the first
   thing heard and seen. Open the headings list (NVDA: Insert+F7; VoiceOver:
   rotor): one level 1 heading naming this week, then the region headings.
   Move into the first table: the caption, then "Water", "County",
   "Species" with each cell. Press "Sort by closest to me" and allow
   location. Listen for: "Waiting for your browser to ask about your
   location", then "Sorted by straight-line distance...", spoken without
   the reading position jumping; focus stays on the button; the new list is
   below it. Deny location once and listen for "Your browser did not share
   your location...".
2. **A California water page with the Lake Notice row** (for example Diaz
   Lake). The breadcrumb is announced as navigation with the current page
   marked. Under "Where Diaz Lake stands on CDFW's schedule", hear the badge
   word, then a group named "Get Diaz Lake's new weeks in your calendar"
   with its two links. Where the notification control is on, press "Alert
   me about this water": hear "Setting it up", then either the sentence
   that it is on (focus on it) or the browser's permission prompt; then
   press "Stop these notifications" and hear "Stopped...". In "About this
   water", the terms and values are read as pairs, and the last link reads
   "Diaz Lake on Lake Notice".
3. **Calendar subscribe flow** on the same page. Activate "Apple Calendar
   (iPhone, iPad, Mac): subscribe" on macOS and iOS and complete Apple's
   subscription sheet with VoiceOver (the sheet is Apple's, but note
   anything that blocks). Activate "Google Calendar (any phone or computer):
   add it" and confirm it opens Google Calendar. Activate "download a
   one-time copy (.ics)".
4. **A county page** (for example Fresno County) and a region page: the
   "at a glance" card heading, then each table's caption and headers.
5. **`/states/` at phone width (iOS)**: each state's row is read as its
   labeled lines, each label once. Then the Tennessee hub and one Tennessee
   water page: the header navigation reads "Tennessee this week", "All
   states", "About & privacy".
6. **Footer, any page** (with analytics allowed in the browser): reach
   "Opt out of analytics" by Tab, press it, hear the status message, press
   again ("Opt back in").
7. **`/gifts/`**: the affiliate disclosure is read before the first gift
   link.
8. **Keyboard only, no screen reader, desktop browser:** repeat steps 1 to
   3 with Tab, Shift+Tab, Enter and Space; the focus ring is visible at
   every stop. Then at 200% browser zoom and 400% zoom (1280 px window),
   check nothing is cut off or needs sideways scrolling.
9. **Windows High Contrast** (or Firefox's forced colors): the calendar and
   notification buttons keep a visible edge, and the focus ring shows.

Time: about 45 minutes per screen-reader pairing for steps 1 to 7, and 30
minutes for steps 8 and 9, so about 3 hours in all.
