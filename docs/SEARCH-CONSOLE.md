# Google Search Console: owner steps

Only the owner can do these, signed in to the Google account that should own
the property. Why the site works this way is in
`docs/adr/0013-search-pages-and-truthful-structured-data.md`.

## The limitation

The site is a GitHub Pages **project** site:
`https://chelseakr.github.io/ca-fish-planting-alerts/`.

- It **cannot be a Domain property.** A Domain property is verified with a
  DNS TXT record on the domain, and `github.io` belongs to GitHub.
- It **can be a URL-prefix property** for exactly
  `https://chelseakr.github.io/ca-fish-planting-alerts/`, verified with an
  HTML tag (below) or an HTML file. That property covers only URLs under
  that prefix, which is the whole site.
- Search Console's Google Analytics method probably will not work. That
  method needs the gtag.js snippet in the home page's `<head>`, but this
  site adds gtag.js from a script, after the Global Privacy Control / Do Not
  Track check (`docs/DECISIONS.md` 0011). Use the HTML tag.
- `robots.txt` is only read at a host's root, so the site's own
  `/ca-fish-planting-alerts/robots.txt` is never requested, and its
  `Sitemap:` line is never seen. Submitting the sitemap in step 6 is how
  Google learns about it.

## Steps

1. Open <https://search.google.com/search-console>, choose **Add property**,
   then the **URL prefix** box (not Domain), and enter exactly
   `https://chelseakr.github.io/ca-fish-planting-alerts/`, with `https` and
   the trailing slash.
2. Under **Other verification methods**, choose **HTML tag**. Google shows
   a tag like
   `<meta name="google-site-verification" content="AbC...xyz" />`.
   Copy **only the `content` value**, not the whole tag. Leave the dialog
   open, and do not press Verify yet.
3. In `pipeline/src/cfpa/site.py`, set that value:

   ```python
   GOOGLE_SITE_VERIFICATION = "AbC...xyz"
   ```

   Open a PR and merge it. `cfpa` refuses to run if the value is anything
   other than a bare token, so pasting the whole `<meta>` tag fails the
   tests rather than shipping a tag Google cannot match.
4. Publish: either wait for the daily `publish` run (13:17 UTC) or start it
   now with **Actions → publish → Run workflow** (or
   `gh workflow run publish.yml -R ChelseaKR/ca-fish-planting-alerts`).
   Check that the tag is live:

   ```sh
   curl -s https://chelseakr.github.io/ca-fish-planting-alerts/ | grep google-site-verification
   ```

   The home page carries the tag, and no other page does.
5. Back in Search Console, press **Verify**. **Keep the value in `site.py`
   for as long as the property is used**, because Search Console re-checks
   it, and removing it un-verifies the property.
6. Go to **Sitemaps**, enter `sitemap.xml` (the full URL is
   `https://chelseakr.github.io/ca-fish-planting-alerts/sitemap.xml`), and
   press **Submit**.
7. Optional: use **URL inspection** to request indexing of the home page,
   `/county/`, and a few county and water pages. Google crawls the rest
   from the sitemap and the links.
8. Optional: use the Rich Results Test (<https://search.google.com/test/rich-results>)
   on a water page. It should find a **Breadcrumbs** item, with no errors.
   Over the following weeks, Search Console's **Breadcrumbs** and
   **Datasets** reports show what Google picked up. The Dataset may show
   a warning for the missing `license` until one is chosen
   (`DATASET_LICENSE_URL` in `site.py`, ADR 0013).
9. Optional: to see search queries next to site analytics, link the
   property in **Google Analytics → Admin → Product links → Search Console
   links** (GA4 property 554849409).

## If the site moves to its own domain

Set `SITE_BASE_URL` (`pipeline/README.md`) and add a **Domain** property
for the new domain, verified by DNS. At a domain root, the site's
`robots.txt` and `WebSite` structured data take effect as written. Keep the
old URL-prefix property until the `github.io` URLs redirect.
