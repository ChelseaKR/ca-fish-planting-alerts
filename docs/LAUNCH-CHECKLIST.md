# Launch checklist: the day Apple approves Trout Truck

This is the list for the day the app goes on the App Store. Nothing here
runs before then. The website says nothing about the App Store until the
launch switch is on, so nothing on the live site changes until you finish
step 3.

The app is free to download, with the optional $9.99 Full Access purchase
described in `docs/app-store/OWNER-STEPS.md`. Nothing in this list touches
the price, the purchase or the app itself. The app sends nothing to Google;
the website alone uses Google Analytics.

## What the switch is

One value: `APP_STORE_LIVE_DEFAULT` in `pipeline/src/cfpa/site.py`. It is
`False` today. When it is `True`, every App Store surface on the website
turns on together:

- Safari's Smart App Banner tag on every page
- Apple's badge on the home and support pages
- the text install links on the home, about and water pages
- the `MobileApplication` structured data on the home and support pages
- the `app_store_click` event in Google Analytics
- the "not in the App Store yet" sentence on the about page goes away
- the support page's two app questions (alerts, restoring a purchase) change
  from "not in the App Store yet" wording to the installed-app wording, in
  both the visible text and the FAQPage data

A test (`pipeline/tests/test_launch_switch.py`) builds the site both ways
and fails if any one of these disagrees with the others.

There is also a repository variable, `APP_STORE_LIVE`. Leave it unset. If
it is set to `true` or `false` it wins over the code, which makes it the
emergency off switch (see "If something is wrong").

## Before you start

1. In App Store Connect, confirm version 1.0.0 shows **Ready for Sale** and
   that https://apps.apple.com/us/app/id6818637427 opens the listing on your
   phone. The release is manual (`docs/app-store/OWNER-STEPS.md`), so
   approval alone is not enough.
2. Check that the repository variable is unset, so the code decides:
   `gh variable list --repo ChelseaKR/ca-fish-planting-alerts`. There should
   be no `APP_STORE_LIVE` line. If there is one, delete it with
   `gh variable delete APP_STORE_LIVE --repo ChelseaKR/ca-fish-planting-alerts`.

## The steps

1. **Run the pre-flight.** From the repository root:
   `cd pipeline && uv run python ../scripts/preflight_app_store_live.py`.
   It changes nothing and just reads. It checks that the App Store address opens, that Apple's
   lookup names this app (same id and bundle id) at the version in the
   project and these docs, and that a test build of the site is consistent
   with the switch both on and off. Every line must say PASS and the last
   line must say `READY to flip`. If one fails, stop; the line says what.
2. **Make the one-line change.** On a branch, change
   `APP_STORE_LIVE_DEFAULT = False` to `APP_STORE_LIVE_DEFAULT = True` in
   `pipeline/src/cfpa/site.py`. Add a line under "Unreleased" in
   `CHANGELOG.md`. Nothing else needs to change; the test suite pins the
   default off for itself.
3. **Merge, then deploy.** Open the pull request, let the checks pass, merge
   it, then run the publish workflow so the site does not wait for the
   daily run: `gh workflow run publish.yml --repo ChelseaKR/ca-fish-planting-alerts`.
   Wait for it to finish green.
4. **Verify with curl.** Each line should print the number after it:
   - `curl -s https://trouttruck.com/ | grep -c apple-itunes-app` prints 1
   - `curl -s https://trouttruck.com/ | grep -c 'Download on the App Store'` prints 1
   - `curl -s https://trouttruck.com/support/ | grep -c 'Download on the App Store'` prints 1
   - `curl -s https://trouttruck.com/ | grep -c MobileApplication` prints 1
   - `curl -s https://trouttruck.com/ | grep -c app_store_click` prints 1
   - `curl -s https://trouttruck.com/about/ | grep -c 'not in the App Store yet'` prints 0
   Then open the home page on your phone and tap the badge. It should open
   the App Store listing.
5. **Check the click event in Google Analytics.** In Google Analytics, open
   Admin, then DebugView for the Trout Truck property. In a browser that does
   not send Global Privacy Control or Do Not Track and where you have not
   used the footer's "Opt out of analytics" button, open the site with
   `https://trouttruck.com/?debug_mode=1` (or use the Google Analytics
   Debugger extension), then click the badge. An `app_store_click` event
   should appear within a few seconds with `placement` `home`, `link_type`
   `badge` and `link_url`. Click the text link on a water page and look for
   `placement` `water`, `link_type` `link`. Then press "Opt out of
   analytics" in the footer, click again, and confirm that no new event
   arrives. That is the privacy promise working.
6. **Ask Google to look again.** In Search Console, use URL Inspection on
   the home page and the support page, and choose Request Indexing for
   each. The structured data is new on those two pages.

## Steps that are yours alone

These need your Google or Apple login. An agent cannot do them.

- **Mark `app_store_click` as a key event** in Google Analytics: Admin, then
  Events, find `app_store_click` (it appears after the earliest real click,
  and can take up to a day to list), and switch on "Mark as key event".
  Do this once. It cannot be done before the event has arrived.
- **Register the two event details** so reports can split by them: Admin,
  then Custom definitions, then Create custom dimension, scope Event, with
  event parameter `placement` and again with `link_type`.
- **Read installs in App Store Connect:** Analytics, then Sources. Set the
  source type to Web Referrer to see downloads that came from
  trouttruck.com. That is the install count the site can be tied to. The
  website cannot see an install itself.
- **Confirm the build** in App Store Connect shows build 2 under version
  1.0.0. Apple does not publish the build number, so the pre-flight cannot
  check it.

## What to watch for 14 days

Look once a day for the opening week, then every other day.

- **Search Console, Performance:** impressions and clicks for the home
  page, per day. Impressions were 0, 45, 158 and 194 on the four days
  of data from 2026-10-14. A drop after the flip would be a reason to
  look at the structured data report for errors.
- **Search Console, Enhancements:** no errors on the `MobileApplication`
  or `FAQPage` items.
- **Google Analytics, Events:** `app_store_click` per day, split by
  `placement` and `link_type`. Home and water pages should lead. A count of
  zero for three days with traffic present means the event is broken.
- **App Store Connect:** product page views, downloads, and the Web Referrer
  source. Compare clicks in Google Analytics with downloads from the web.
  Expect clicks to be higher; not everyone installs.
- **Ratings and crashes:** App Store Connect, Ratings and Reviews, and
  Crashes.
- **The publish workflow:** the daily run at 13:17 UTC stays green. A failed
  run keeps the last good site, with the switch's state as it was.

## If something is wrong

To turn every App Store surface off without a code change, set the
variable and republish:
`gh variable set APP_STORE_LIVE --repo ChelseaKR/ca-fish-planting-alerts --body false`
then `gh workflow run publish.yml --repo ChelseaKR/ca-fish-planting-alerts`.
The variable beats the code, so this works even though the code says on.
When fixed, delete the variable so the code decides again. The proper fix
is the same one-line change back to `False` in a pull request.

Any other value in the variable (for example "yes") fails the publish run
and the site keeps its last good build. That is deliberate.

## Not in this list

An optional follow-up, not built: App Store links can carry a campaign
token (`?ct=...`) so App Store Connect can tell which page a download came
from. It changes the link addresses that the pre-flight and the tests
check, so it is a separate pull request if you want it.
