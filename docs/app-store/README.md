# App Store kit

Everything for submitting the Trout Truck iOS app, in the order you need it:

- [`OWNER-STEPS.md`](OWNER-STEPS.md): the ordered owner steps from here to
  "Submitted for Review", the decisions to settle first, and what is
  already done.
- [`../APP-STORE-LISTING.md`](../APP-STORE-LISTING.md): paste-ready listing
  text with measured character counts (name, subtitle, promotional text,
  description, keywords, categories, URLs), the App Privacy answers with
  the reasoning per Apple data category, the age-rating answers, and the
  App Review notes.
- [`../APP-STORE.md`](../APP-STORE.md): the reasoning behind the listing,
  the privacy check against the code, the review clauses that apply, the
  in-app purchase to create, and the screenshot set.
- [`screenshots/`](screenshots/): the iPhone 6.9" screenshots, made by
  `ios/scripts/app-store-screenshots.sh` from the snapshot bundled with the
  app (`SCREENSHOT_CLASS=6.5` makes an optional 6.5" set in
  `screenshots/6.5-inch/`).

The readiness check behind "already done" is `make appstore`
(`scripts/check_app_store.py`), and the release workflow is
`.github/workflows/ios-release.yml`.
