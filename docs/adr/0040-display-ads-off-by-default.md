# 0040. Display ads: one Google AdSense unit, built and off

Status: Proposed
Date: 2026-10-23
Deciders: Chelsea Kelly-Reif

## Context

The owner allowed ads "if really worth it" (2026-10-23). The site had about
714 users and 46 engaged sessions in the 28 days before that date, and most
raw sessions have been crawlers. The comparison of networks, the privacy
rules and the revenue estimate are in the owner's research note
(`_agent-tools/growth/research-tt-ads-2026-10-23.md`, outside this repo).
In short:

- Google AdSense is the only network that accepts a site this small. Journey
  by Mediavine needs 1,000 Tier 1 sessions in 30 days; Mediavine, Raptive,
  EthicalAds and Carbon need far more traffic or a developer audience.
- Expected revenue is cents to a few dollars a month, and AdSense pays out
  at $100. One app sale nets more than a month of ads.

## Decision

- **Off by default.** `pipeline/src/cfpa/ads.py` holds the switch
  (`ADS_ENABLED = False`) and the three values that go with it: the
  publisher ID, the ad unit's slot ID and the date the privacy policy's ads
  section takes effect. Off with no publisher ID, the build is byte for
  byte what it was before; off with one, it adds only the account meta tag
  and `ads.txt`, for AdSense's site review. On, a missing or malformed
  value fails the build. Ads also need the
  analytics build, because the no-analytics copy promises no third-party
  script.
- **Where.** One responsive unit at the end of the main content on water,
  county, county index, region, species, week and week-index pages, and the
  other states' hub and water pages (`ads.AD_PAGES`). Never on the home page,
  the "What to bring" page, about, privacy, support, data, the guides, 404,
  the email pages, in any email or in the apps. On a water page it sits below
  the "other waters" lists, well after the Amazon gear links and their
  disclosure, under its own "Advertisement" label and a rule.
- **No empty box.** The slot is collapsed (zero height, hidden from
  assistive technology) until AdSense marks the unit `filled`. `unfilled`,
  `unfill-optimized`, a script error or no answer in 10 seconds removes it.
- **Privacy.** GPC, Do Not Track or the visitor's "Turn off ads" choice on
  the privacy page means the AdSense script never loads. Otherwise the tag
  asks for non-personalized ads only. Restricted data processing is turned
  on in the AdSense account, so Google acts as a service provider for
  California and the other US states with privacy laws, and the site does
  not sell or share personal information. Google's own consent message
  covers the EEA, the UK and Switzerland.
- **Disclosure.** The privacy policy gets an "Ads" section, the about page
  stops saying there are no ads, and every page's footer links to the ad
  choices. The build writes `ads.txt` at the site root.

## Owner steps before turning it on

1. Sign up for Google AdSense with the trouttruck.com site. To connect the
   site, paste the publisher ID (`ca-pub-` and 16 digits) into
   `ADSENSE_PUBLISHER_ID` in `pipeline/src/cfpa/ads.py` and merge that one
   line with `ADS_ENABLED` still False: the build then adds only the
   `google-adsense-account` meta tag and `ads.txt`, no script and no ad.
   Choose the meta tag option in AdSense and wait for approval.
2. In AdSense, Privacy & messaging: create and publish the European
   regulations message (EEA, UK, Switzerland). Under US state regulations,
   turn on restricted data processing for all users in the applicable
   states.
3. Create one responsive display ad unit and copy its `data-ad-slot` value.
4. In one pull request, set in `pipeline/src/cfpa/ads.py`:
   `ADS_ENABLED = True`, `ADSENSE_SLOT_ID = "..."` and
   `ADS_EFFECTIVE_DATE` to the launch day; and move the privacy policy's
   "Last updated" date to the same day.
5. After the deploy, check `https://trouttruck.com/ads.txt` and AdSense's
   ads.txt status.

## Consequences

- Pages with ads get slower: AdSense loads its loader, an iframe and the
  creatives. The site's speed and reflow gates run with ads off, so they
  keep measuring the site itself.
- If revenue stays under a few dollars a month after the spring 2027
  planting peak, turn the switch off; the cost in speed and trust is not
  worth it.
