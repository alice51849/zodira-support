# Zodira Support

Public support, privacy and contact site for **Zodira: Decision Journal**.
Contact for every surface: <hourstag.app@gmail.com>

## Layout

| Path | Purpose |
| --- | --- |
| `index.html`, `privacy.html`, `terms.html` | Root pages. Rendered from `locales.js` by `localize.js`; `?lang=<locale>` switches all 50 locales client-side. |
| `<locale>/index.html`, `<locale>/support.html`, `<locale>/privacy.html` | Static, crawlable required surfaces for every one of Apple's 50 product-page locales (150 files). |
| `locales.js` | Single source of truth for the native 50-locale product copy. |
| `source/crosspromo_catalog.json` | Verified first-party app facts used by the cross-promo module. |
| `tools/support_surfaces.py` | Builds and validates the 150 static surfaces. |
| `lint_site.py` | Existing site lint (identity, dictionary, localized URLs, sitemap, contact). |

## Commands

```bash
python3 tools/support_surfaces.py build   # regenerate the 150 static surfaces, surface.css, sitemap rows and the root cross-promo module
python3 tools/support_surfaces.py check   # full rule-based validation (must print "PASS")
python3 lint_site.py                      # existing site lint (run from a checkout beside the app project)
```

`lint_site.py` reads the app project's store metadata from `../StoreAssets`,
`../fastlane` and `../tools`, so run it from a checkout that sits next to the
Zodira app project.

## Content rules enforced by `tools/support_surfaces.py check`

* The locale set is exactly Apple's official 50 product-page locales; every
  locale has `index`, `support` and `privacy`.
* `canonical`, the 50 `hreflang` alternates and `x-default` resolve to real
  files; `x-default` always points at `en-US`.
* `hourstag.app@gmail.com` is the only address anywhere on the site.
* No raw localization keys, placeholders, retired brand names, secrets, or
  English copy reused for a non-English locale; RTL, Indic, CJK and Cyrillic
  locales must actually contain their own script.
* Cross-promo cards use the catalog's **exact** canonical App Store URL with no
  campaign parameters added or rewritten, plus Apple's own localized app name
  and formatted price. Only apps verified live with a read-only, non-subscription
  unlock may carry the one-time-unlock line. No ratings, rankings or download
  counts, and the module is a first-party publisher list, not an independent
  ranking.
* The three root pages carry the same verified module inside
  `<!-- ls-family:start -->` markers with self-contained styles, so `build`
  keeps them in sync and `check` fails if they go stale.
* Zodira itself has **no verified live App Store URL**, so no surface renders an
  own-app store button. This is deliberate fail-closed behaviour: if the app
  ships, add its catalog URL first and rebuild.

Zodira is a private reflection and decision journal. Its wording is deliberately
framed as a way to question assumptions — never as a forecast, an instruction,
or medical, legal or financial advice.
