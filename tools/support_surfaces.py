#!/usr/bin/env python3
"""Build and validate the exact-50 public support surfaces for zodira-support.

Single sources of truth
  * ``locales.js``                     - native product copy for the 50 Apple
    product-page locales, already gated by ``lint_site.py``.
  * ``source/crosspromo_catalog.json`` - first-party verified app facts for the
    cross-promo module (canonical App Store URLs, Apple's own localized names
    and price strings, read-only monetization flags).

Fail-closed rules
  * Zodira itself has no verified live App Store URL, so no surface renders an
    own-app store button. Nothing is guessed.
  * Cross-promo cards only ever use the catalog's exact canonical App Store URL
    (no campaign parameters added or rewritten) plus Apple's own localized name
    and formatted price. No ratings, rankings, download counts or invented copy.

Usage
    python3 tools/support_surfaces.py build
    python3 tools/support_surfaces.py check
    python3 tools/support_surfaces.py digest
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOCALES_JS = ROOT / "locales.js"
CATALOG = ROOT / "source" / "crosspromo_catalog.json"
BASE_URL = "https://alice51849.github.io/zodira-support/"
EMAIL = "hourstag.app@gmail.com"
APP_NAME_LATIN = "Zodira"
SURFACES = ("index", "support", "privacy")
FILES = {"index": "index.html", "support": "support.html", "privacy": "privacy.html"}
MIN_CARDS = 3

OFFICIAL = [
    "ar-SA", "bn-BD", "ca", "zh-Hans", "zh-Hant", "hr", "cs", "da",
    "nl-NL", "en-AU", "en-CA", "en-GB", "en-US", "fi", "fr-CA",
    "fr-FR", "de-DE", "el", "gu-IN", "he", "hi", "hu", "id", "it",
    "ja", "kn-IN", "ko", "ms", "ml-IN", "mr-IN", "no", "or-IN", "pl",
    "pt-BR", "pt-PT", "pa-IN", "ro", "ru", "sk", "sl-SI", "es-MX",
    "es-ES", "sv", "ta-IN", "te-IN", "th", "tr", "uk", "ur-PK", "vi",
]
ENGLISH = {"en-US", "en-GB", "en-AU", "en-CA"}
RTL = {"ar-SA", "he", "ur-PK"}
SCRIPT_RANGES = {
    "ar-SA": r"[\u0600-\u06ff]", "he": r"[\u0590-\u05ff]",
    "ur-PK": r"[\u0600-\u06ff]", "bn-BD": r"[\u0980-\u09ff]",
    "gu-IN": r"[\u0a80-\u0aff]", "hi": r"[\u0900-\u097f]",
    "mr-IN": r"[\u0900-\u097f]", "kn-IN": r"[\u0c80-\u0cff]",
    "ml-IN": r"[\u0d00-\u0d7f]", "or-IN": r"[\u0b00-\u0b7f]",
    "pa-IN": r"[\u0a00-\u0a7f]", "ta-IN": r"[\u0b80-\u0bff]",
    "te-IN": r"[\u0c00-\u0c7f]", "el": r"[\u0370-\u03ff]",
    "ru": r"[\u0400-\u04ff]", "uk": r"[\u0400-\u04ff]",
    "zh-Hans": r"[\u4e00-\u9fff]", "zh-Hant": r"[\u4e00-\u9fff]",
    "ja": r"[\u3040-\u30ff\u4e00-\u9fff]", "ko": r"[\uac00-\ud7af]",
    "th": r"[\u0e00-\u0e7f]",
}
COPY_KEYS = (
    "languageName", "name", "subtitle", "description", "workflow", "local",
    "lens", "purchase", "noSubscription", "restore", "delete", "support",
    "privacy", "noCollection", "deletion", "restoreHelp", "titleSupport",
    "titlePrivacy",
)
TAG_RE = re.compile(r"<[^>]+>")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
RAW_KEY_RE = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){2,}\b")
# Visible host names are not localization keys.
HOSTNAME_RE = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:com|org|net|io|app|co|dev|gov|edu|jp|uk|tw|cn)\b", re.I)
# Uppercase-only markers: "todo" is an ordinary Spanish/Portuguese word.
MARKER_RE = re.compile(r"\b(?:TODO|TBD|FIXME|XXX)\b")
PLACEHOLDER_RE = re.compile(
    r"(?:\blorem ipsum\b|\bplaceholder\b|\bcoming soon\b|\{\{|\}\}|"
    r"\bundefined\b|\[object Object\])", re.I
)
SECRET_RE = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{20,}|"
    r"\bsk-[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{16}\b|BEGIN OPENSSH)"
)
BANNED_TEXT_RE = re.compile(
    r"\bAstrea\b|alice51849@hotmail\.com|"
    r"\b(?:rating|ranking|downloads?)\s*[:#]", re.I
)


# --------------------------------------------------------------------------- #
# sources
# --------------------------------------------------------------------------- #
def load_locales() -> dict:
    text = LOCALES_JS.read_text(encoding="utf-8")
    data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    if list(data) != OFFICIAL:
        raise SystemExit("locales.js: locale set is not the official Apple 50")
    for locale, entry in data.items():
        missing = [key for key in COPY_KEYS if not str(entry.get(key, "")).strip()]
        if missing:
            raise SystemExit(f"{locale}: missing native copy for {missing}")
    return data


def load_catalog() -> dict:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    if data.get("schema") != "zodira-support-crosspromo/v1":
        raise SystemExit("crosspromo catalog: unsupported schema")
    if set(data["copy"]) != set(OFFICIAL):
        raise SystemExit("crosspromo catalog: copy locale set mismatch")
    if set(data["storefront_by_locale"]) != set(OFFICIAL):
        raise SystemExit("crosspromo catalog: storefront locale set mismatch")
    for app in data["apps"]:
        url = app["canonical_app_store_url"]
        if not url.startswith("https://apps.apple.com/") or "?" in url:
            raise SystemExit(f"{app['key']}: App Store URL is not the exact catalog URL")
    return data


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def route(locale: str, surface: str) -> str:
    return f"{locale}/{FILES[surface]}"


def route_url(locale: str, surface: str) -> str:
    return BASE_URL + route(locale, surface)


def blocks(text: str) -> str:
    """Render native paragraphs and bullet lists without inventing structure."""
    out: list[str] = []
    bullets: list[str] = []

    def flush() -> None:
        if bullets:
            out.append("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in bullets) + "</ul>")
            bullets.clear()

    for chunk in (x.strip() for x in text.split("\n")):
        if not chunk:
            continue
        if chunk[0] in "\u2022-\u2013\u2014*":
            bullets.append(chunk.lstrip("\u2022-\u2013\u2014* ").strip())
        else:
            flush()
            out.append(f"<p>{esc(chunk)}</p>")
    flush()
    return "".join(out)


def meta_description(lead: str, fallback: str) -> str:
    first = next((x.strip() for x in lead.split("\n") if x.strip()), "")
    return first if 0 < len(first) <= 200 else fallback


def page_plan(copy: dict) -> dict[str, dict]:
    return {
        "index": {
            "title": copy["name"],
            "eyebrow": copy["subtitle"],
            "heading": copy["name"],
            "lead": copy["description"],
            "description": meta_description(copy["description"], copy["subtitle"]),
            "sections": [
                (copy["support"], copy["workflow"]),
                (copy["privacy"], copy["local"]),
                (copy["purchase"], copy["noSubscription"]),
            ],
            "contact": False,
        },
        "support": {
            "title": copy["titleSupport"],
            "eyebrow": copy["support"],
            "heading": copy["titleSupport"],
            "lead": copy["workflow"],
            "description": meta_description(copy["workflow"], copy["subtitle"]),
            "sections": [
                (copy["restore"], copy["restoreHelp"]),
                (copy["delete"], copy["deletion"]),
                (copy["privacy"], copy["noCollection"]),
                (copy["purchase"], copy["noSubscription"]),
            ],
            "contact": True,
        },
        "privacy": {
            "title": copy["titlePrivacy"],
            "eyebrow": copy["privacy"],
            "heading": copy["titlePrivacy"],
            "lead": copy["noCollection"],
            "description": meta_description(copy["noCollection"], copy["subtitle"]),
            "sections": [
                (copy["privacy"], copy["local"]),
                (copy["delete"], copy["deletion"]),
                (copy["restore"], copy["restoreHelp"]),
                (copy["purchase"], copy["noSubscription"]),
            ],
            "contact": True,
        },
    }


# --------------------------------------------------------------------------- #
# cross-promo
# --------------------------------------------------------------------------- #
def family_module(catalog: dict, locale: str, standalone: bool = False) -> str:
    """Localized "more apps from the same developer" module.

    ``standalone`` emits a self-contained variant (scoped styles, no dependency
    on surface.css) for the JavaScript-rendered root pages.
    """
    copy = catalog["copy"][locale]
    storefront = catalog["storefront_by_locale"][locale]
    prefix = "lsf-" if standalone else ""
    cards = []
    for app in catalog["apps"]:
        listing = app["storefronts"].get(storefront)
        if not listing or not listing["name"] or not listing["formatted_price"]:
            continue
        price = listing["formatted_price"]
        if app["unlock_iap_verified"]:
            price = price + " \u00b7 " + copy["iap"]
        icon = ""
        if listing["icon"]:
            icon = (
                f'<img src="{esc(listing["icon"])}" width="46" height="46" alt="" '
                'loading="lazy" decoding="async">'
            )
        cards.append(
            f'<a class="{prefix}family-card" '
            f'href="{esc(app["canonical_app_store_url"])}" '
            f'rel="noopener">{icon}<span class="{prefix}family-text">'
            f'<strong>{esc(listing["name"])}</strong>'
            f'<span class="{prefix}family-meta">{esc(price)}</span>'
            f'<span class="{prefix}family-cta">{esc(copy["cta"])}</span></span></a>'
        )
    if len(cards) < MIN_CARDS:
        raise SystemExit(f"{locale}: only {len(cards)} verified cross-promo cards")
    styles = FAMILY_STYLES if standalone else ""
    shell = "lsf-family" if standalone else "card wide family"
    return (
        "<!-- ls-family:start -->"
        f'{styles}<section class="{shell}" aria-label="{esc(copy["heading"])}">'
        f'<h2>{esc(copy["heading"])}</h2>'
        f'<div class="{prefix}family-grid">{"".join(cards)}</div>'
        f'<p class="{prefix}family-note">{esc(copy["note"])} '
        f'<a href="{esc(catalog["guide_url"])}" rel="noopener">{esc(copy["guide"])}</a></p>'
        "</section>"
        "<!-- ls-family:end -->"
    )


FAMILY_STYLES = (
    "<style>"
    ".lsf-family{width:min(1080px,calc(100% - 32px));margin:30px auto;padding:20px 22px;"
    "border:1px solid rgba(127,127,127,.24);border-radius:20px;"
    "background:rgba(127,127,127,.08);color:inherit;font-family:inherit;text-align:start}"
    ".lsf-family h2{margin:0 0 14px;font-size:17px;font-weight:500;color:inherit}"
    ".lsf-family-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}"
    ".lsf-family-card{display:flex;align-items:center;gap:12px;padding:12px 14px;"
    "border:1px solid rgba(127,127,127,.22);border-radius:16px;"
    "background:rgba(127,127,127,.10);color:inherit;text-decoration:none;min-width:0}"
    ".lsf-family-card img{border-radius:11px;flex:0 0 auto}"
    ".lsf-family-text{min-width:0}"
    ".lsf-family-text strong{display:block;font-size:14px;font-weight:500;line-height:1.35}"
    ".lsf-family-meta,.lsf-family-cta{display:block;font-size:12px;line-height:1.45;opacity:.72}"
    ".lsf-family-note{margin:12px 0 0;font-size:13px;opacity:.72}"
    "</style>"
)
FAMILY_BLOCK_RE = re.compile(
    r"<!-- ls-family:start -->.*?<!-- ls-family:end -->", re.S)
ROOT_PAGES = ("index.html", "privacy.html", "terms.html")
ROOT_CANONICALS = {
    "index.html": BASE_URL,
    "privacy.html": BASE_URL + "privacy.html",
    "terms.html": BASE_URL + "terms.html",
}
ROOT_X_DEFAULTS = {
    "index.html": BASE_URL,
    "privacy.html": BASE_URL + "privacy.html",
}
ROOT_NAV_CONTRACTS = {
    "index.html": (
        ("index.html", "support", True),
        ("privacy.html", "privacy", False),
    ),
    "privacy.html": (
        ("index.html", "support", False),
        ("privacy.html", "privacy", True),
    ),
}
ROOT_STATIC_ENTRIES = {
    "index.html": ("en-US/support.html", "Localized support pages"),
    "privacy.html": ("en-US/privacy.html", "Localized privacy pages"),
}
ROOT_PAGE_SURFACES = {
    "index.html": "index",
    "privacy.html": "privacy",
}
ROOT_HTML_RE = re.compile(r"<html\b([^>]*)>", re.I)
ROOT_DATA_PAGE_NAME_RE = re.compile(
    r"(?:^|\s)data-page(?=\s|=|$)", re.I
)
ROOT_DATA_PAGE_VALUE_RE = re.compile(
    r"""(?:^|\s)data-page\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
    re.I,
)
ROOT_DATA_PAGE_ATTR_RE = re.compile(
    r"""(?:\s+)data-page(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?""",
    re.I,
)
ROOT_STATIC_ENTRY_RE = re.compile(
    r"<!-- root-static-entry:start -->.*?<!-- root-static-entry:end -->",
    re.S,
)
SITEMAP_LASTMOD = "2026-08-29"


def root_data_page_state(text: str) -> tuple[int, int, list[str]]:
    html_tags = ROOT_HTML_RE.findall(text)
    values = [
        html.unescape(next((value for value in match if value != ""), ""))
        for attrs in html_tags
        for match in ROOT_DATA_PAGE_VALUE_RE.findall(attrs)
    ]
    marker_count = sum(
        len(ROOT_DATA_PAGE_NAME_RE.findall(attrs))
        for attrs in html_tags
    )
    return len(html_tags), marker_count, values


def sync_root_data_pages() -> list[str]:
    """Canonicalize the root page identity used by the legacy locale router."""
    touched = []
    for name, page in ROOT_PAGE_SURFACES.items():
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        html_tags = list(ROOT_HTML_RE.finditer(text))
        if len(html_tags) != 1:
            raise SystemExit(f"{name}: expected exactly one html element")
        match = html_tags[0]
        attrs = ROOT_DATA_PAGE_ATTR_RE.sub("", match.group(1)).rstrip()
        opening = f'<html{attrs} data-page="{page}">'
        updated = text[:match.start()] + opening + text[match.end():]
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            touched.append(name)
    return touched


def sync_root_modules(catalog: dict) -> list[str]:
    """Keep the same verified module on the JavaScript-rendered root pages."""
    module = family_module(catalog, "en-US", standalone=True)
    touched = []
    for name in ROOT_PAGES:
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        if FAMILY_BLOCK_RE.search(text):
            updated = FAMILY_BLOCK_RE.sub(lambda _: module, text, count=1)
        else:
            anchor = text.lower().rfind("<footer")
            if anchor < 0:
                anchor = text.lower().rfind("</body>")
            if anchor < 0:
                raise SystemExit(f"{name}: no anchor for the cross-promo module")
            updated = text[:anchor] + module + "\n" + text[anchor:]
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            touched.append(name)
    return touched


def root_static_entry(name: str) -> str:
    href, label = ROOT_STATIC_ENTRIES[name]
    return (
        f'<!-- root-static-entry:start --><a href="{esc(href)}">'
        f'{esc(label)}</a><!-- root-static-entry:end -->'
    )


def sync_root_static_entries() -> list[str]:
    """Keep one crawlable, non-nav entry into each root page's static cluster."""
    touched = []
    for name in ROOT_STATIC_ENTRIES:
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        entry = root_static_entry(name)
        if ROOT_STATIC_ENTRY_RE.search(text):
            updated = ROOT_STATIC_ENTRY_RE.sub(lambda _: entry, text, count=1)
        else:
            footer = '<div class="footer-links">\n'
            anchor = text.find(footer)
            if anchor < 0:
                raise SystemExit(f"{name}: footer-links anchor missing")
            insert_at = anchor + len(footer)
            updated = text[:insert_at] + f"        {entry}\n" + text[insert_at:]
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            touched.append(name)
    return touched


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def alternates(surface: str) -> str:
    rows = [
        f'<link rel="alternate" hreflang="{code}" href="{esc(route_url(code, surface))}">'
        for code in OFFICIAL
    ]
    rows.append(
        '<link rel="alternate" hreflang="x-default" '
        f'href="{esc(route_url("en-US", surface))}">'
    )
    return "\n".join(rows)


def schema_block(locale: str, surface: str, plan: dict) -> str:
    payload = {
        "@context": "https://schema.org",
        "@graph": [{
            "@type": "WebPage",
            "url": route_url(locale, surface),
            "name": plan["title"],
            "inLanguage": locale,
            "isPartOf": {"@type": "WebSite", "url": BASE_URL, "name": APP_NAME_LATIN},
            "publisher": {"@type": "Organization", "name": "Lumi Studio", "email": EMAIL},
        }],
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return body.replace("</", "<\\/")


def render(locales: dict, catalog: dict, locale: str, surface: str) -> str:
    copy = locales[locale]
    plan = page_plan(copy)[surface]
    canonical = route_url(locale, surface)
    current_page = ' aria-current="page"'
    current_true = ' aria-current="true"'
    nav = "".join(
        f'<a href="{esc(FILES[key])}"{current_page if key == surface else ""}>'
        f'{esc(label)}</a>'
        for key, label in (("index", copy["name"]), ("support", copy["support"]),
                           ("privacy", copy["privacy"]))
    )
    languages = "".join(
        f'<a lang="{code}" hreflang="{code}" href="{esc(route_url(code, surface))}"'
        f'{current_true if code == locale else ""}>'
        f'{esc(locales[code]["languageName"])}</a>'
        for code in OFFICIAL
    )
    sections = "".join(
        f'<section class="card"><h2>{esc(heading)}</h2>{blocks(body)}</section>'
        for heading, body in plan["sections"]
    )
    contact = ""
    if plan["contact"]:
        contact = (
            f'<section class="card wide contact"><h2>{esc(copy["support"])}</h2>'
            f'<p><a class="button" href="mailto:{EMAIL}">{esc(copy["support"])}</a></p>'
            f'<p><a class="email" href="mailto:{EMAIL}">{EMAIL}</a></p></section>'
        )
    return f"""<!doctype html>
<html lang="{esc(locale)}" dir="{"rtl" if locale in RTL else "ltr"}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="support-surface-generated" content="zodira-support-surface/v1">
<meta name="support-surface-authority" content="{esc(catalog["digest"])}">
<title>{esc(plan["title"])}</title>
<meta name="description" content="{esc(plan["description"])}">
<meta name="theme-color" content="#090716">
<link rel="canonical" href="{esc(canonical)}">
{alternates(surface)}
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(plan["title"])}">
<meta property="og:description" content="{esc(plan["description"])}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:locale" content="{esc(locale.replace("-", "_"))}">
<script id="support-surface-schema" type="application/ld+json">{schema_block(locale, surface, plan)}</script>
<link rel="stylesheet" href="../surface.css">
</head>
<body>
<div class="shell">
<header class="site-header">
<a class="brand" href="{esc(FILES["index"])}">{esc(copy["name"])}</a>
<nav class="nav" aria-label="{esc(copy["support"])}">{nav}</nav>
<details class="language"><summary>{esc(copy["languageName"])}</summary>
<div class="language-list">{languages}</div></details>
</header>
<main>
<section class="hero">
<p class="eyebrow">{esc(plan["eyebrow"])}</p>
<h1>{esc(plan["heading"])}</h1>
<div class="lead">{blocks(plan["lead"])}</div>
<p class="lens">{esc(copy["lens"])}</p>
</section>
<div class="grid">{sections}{contact}{family_module(catalog, locale)}</div>
</main>
<footer class="site-footer">
<span>&copy; 2026 {esc(copy["name"])}</span>
<span>{esc(copy["local"])}</span>
<a href="mailto:{EMAIL}">{EMAIL}</a>
</footer>
</div>
</body>
</html>
"""


STYLESHEET = """:root{color-scheme:dark;--ink:#f4f1ff;--muted:#b6aee0;--a1:#a98bff;--a2:#5b4cc4;--bg:#090716;--panel:rgba(255,255,255,.055);--line:rgba(160,140,255,.24)}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;min-height:100vh;color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"SF Pro Rounded","Segoe UI","Noto Sans","Noto Sans Arabic","Noto Sans Hebrew","Noto Sans Devanagari","Noto Sans Bengali","Noto Sans Gujarati","Noto Sans Gurmukhi","Noto Sans Kannada","Noto Sans Malayalam","Noto Sans Oriya","Noto Sans Tamil","Noto Sans Telugu","Noto Sans Thai",sans-serif;font-weight:400;background:radial-gradient(circle at 10% -4%,rgba(139,92,246,.24),transparent 34rem),radial-gradient(circle at 92% 2%,rgba(91,76,196,.22),transparent 30rem)}
a{color:var(--a1);text-decoration:none}
a:focus-visible,summary:focus-visible{outline:3px solid rgba(169,139,255,.65);outline-offset:4px}
.shell{width:min(1080px,calc(100% - 32px));margin:auto}
.site-header{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;padding:22px 0}
.brand{color:var(--ink);font-weight:600;font-size:17px;text-wrap:balance}
.nav{display:flex;gap:6px;flex-wrap:wrap}
.nav a{display:inline-flex;align-items:center;min-height:44px;padding:10px 14px;border-radius:14px;color:var(--muted);font-weight:500}
.nav a[aria-current]{background:rgba(139,92,246,.18);color:var(--ink)}
.language{position:relative}
.language summary{display:inline-flex;align-items:center;min-height:44px;padding:10px 14px;border:1px solid var(--line);border-radius:14px;color:var(--muted);cursor:pointer;list-style:none}
.language summary::-webkit-details-marker{display:none}
.language-list{position:absolute;z-index:9;inset-inline-end:0;top:54px;width:min(620px,calc(100vw - 24px));max-height:66vh;overflow:auto;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px;padding:12px;border:1px solid var(--line);border-radius:18px;background:#140f2a;box-shadow:0 24px 70px rgba(0,0,0,.55)}
.language-list a{padding:9px 11px;border-radius:11px;color:var(--muted);font-size:14px}
.language-list a[aria-current]{background:rgba(139,92,246,.2);color:var(--ink)}
main{padding:10px 0 6px}
.hero{padding:14px 0 26px;max-width:74ch}
.eyebrow{margin:0;color:var(--a1);font-size:13px;font-weight:600;letter-spacing:.09em;text-transform:uppercase}
h1{margin:12px 0 10px;font-size:clamp(30px,5.6vw,52px);line-height:1.14;font-weight:300;letter-spacing:-.02em;text-wrap:balance}
.lead p{margin:0 0 10px;color:var(--muted);font-size:18px;text-wrap:pretty}
.lead ul{margin:0 0 12px;padding-inline-start:1.15em;color:var(--muted)}
.lead li{margin:4px 0}
.lens{margin:14px 0 0;padding:12px 16px;border-inline-start:3px solid var(--a1);border-radius:10px;background:rgba(139,92,246,.1);color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.card{padding:22px 24px;border:1px solid var(--line);border-radius:20px;background:var(--panel);backdrop-filter:blur(14px)}
.card.wide{grid-column:1/-1}
.card h2{margin:0 0 10px;font-size:19px;font-weight:500;text-wrap:balance}
.card p{margin:0 0 8px;color:var(--muted);text-wrap:pretty}
.card p:last-child{margin-bottom:0}
.card ul{margin:0;padding-inline-start:1.15em;color:var(--muted)}
.button{display:inline-flex;align-items:center;min-height:44px;padding:11px 22px;border-radius:14px;color:#fff;font-weight:500;background:linear-gradient(130deg,var(--a1),var(--a2))}
.email{color:var(--muted)}
.family-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}
.family-card{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.05);color:var(--ink);min-width:0}
.family-card img{border-radius:11px;flex:0 0 auto}
.family-text{min-width:0}
.family-text strong{display:block;font-size:14px;font-weight:500;line-height:1.35}
.family-meta,.family-cta{display:block;font-size:12px;line-height:1.45;color:var(--muted)}
.family-note{margin:12px 0 0;font-size:13px;color:var(--muted)}
.site-footer{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap;margin-top:30px;padding:24px 0 40px;border-top:1px solid var(--line);color:var(--muted);font-size:14px}
@media(max-width:760px){.language-list{position:fixed;inset:78px 12px auto;grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


# --------------------------------------------------------------------------- #
# sitemap
# --------------------------------------------------------------------------- #
def expected_sitemap_urls() -> list[str]:
    return [
        *ROOT_CANONICALS.values(),
        *(
            route_url(locale, surface)
            for locale in OFFICIAL
            for surface in SURFACES
        ),
    ]


def write_sitemap() -> None:
    path = ROOT / "sitemap.xml"
    root_rows = [
        f"  <url><loc>{esc(url)}</loc><lastmod>{SITEMAP_LASTMOD}</lastmod>"
        f"<changefreq>monthly</changefreq><priority>{priority}</priority></url>\n"
        for url, priority in (
            (BASE_URL, "1.0"),
            (BASE_URL + "privacy.html", "0.7"),
            (BASE_URL + "terms.html", "0.4"),
        )
    ]
    locale_rows = [
        f"  <url><loc>{esc(route_url(locale, surface))}</loc>"
        "<changefreq>monthly</changefreq>"
        f"<priority>{'0.9' if surface == 'index' else '0.8'}</priority></url>\n"
        for locale in OFFICIAL for surface in SURFACES
    ]
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{"".join(root_rows)}{"".join(locale_rows)}</urlset>\n',
        encoding="utf-8",
    )


def build() -> dict:
    locales = load_locales()
    catalog = load_catalog()
    root_data_pages = sync_root_data_pages()
    (ROOT / "surface.css").write_text(STYLESHEET, encoding="utf-8")
    written = 0
    for locale in OFFICIAL:
        for surface in SURFACES:
            target = ROOT / route(locale, surface)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(locales, catalog, locale, surface), encoding="utf-8")
            written += 1
    write_sitemap()
    root_pages = sync_root_modules(catalog)
    root_entries = sync_root_static_entries()
    return {
        "written": written,
        "root_data_pages_synced": root_data_pages,
        "root_pages_synced": root_pages,
        "root_static_entries_synced": root_entries,
        "digest": digest(),
    }


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def visible_text(text: str) -> str:
    text = re.sub(r"<(?:script|style)\b.*?</(?:script|style)>", " ", text, flags=re.I | re.S)
    return " ".join(html.unescape(TAG_RE.sub(" ", text)).split())


def attr_values(text: str, tag: str, attr: str,
                required: tuple[str, str] | None = None) -> list[str]:
    out = []
    for match in re.finditer(fr"<{tag}\b([^>]*)>", text, re.I):
        attrs = match.group(1)
        if required:
            found = re.search(fr"\b{required[0]}\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
            if not found or found.group(1).lower() != required[1].lower():
                continue
        value = re.search(fr"\b{attr}\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
        if value:
            out.append(html.unescape(value.group(1)))
    return out


def attributes(source: str) -> dict[str, str]:
    return {
        name.lower(): html.unescape(value)
        for name, _, value in re.findall(
            r"""([:\w-]+)\s*=\s*(["'])(.*?)\2""", source, re.S
        )
    }


def alternate_values(text: str, hreflang: str) -> list[str]:
    values = []
    for match in re.finditer(r"<link\b([^>]*)>", text, re.I):
        attrs = attributes(match.group(1))
        if (attrs.get("rel", "").lower() == "alternate"
                and attrs.get("hreflang") == hreflang
                and attrs.get("href")):
            values.append(attrs["href"])
    return values


def container_anchors(text: str, tag: str,
                      class_name: str) -> list[dict[str, str]]:
    pattern = rf"<{re.escape(tag)}\b([^>]*)>(.*?)</{re.escape(tag)}>"
    for match in re.finditer(pattern, text, re.I | re.S):
        container_attrs = attributes(match.group(1))
        if class_name not in container_attrs.get("class", "").split():
            continue
        anchors = []
        for anchor in re.finditer(r"<a\b([^>]*)>(.*?)</a>", match.group(2),
                                  re.I | re.S):
            record = attributes(anchor.group(1))
            record["text"] = visible_text(anchor.group(2))
            anchors.append(record)
        return anchors
    return []


def root_nav_anchors(text: str) -> list[dict[str, str]]:
    return container_anchors(text, "nav", "nav")


def footer_link_anchors(text: str) -> list[dict[str, str]]:
    return container_anchors(text, "div", "footer-links")


def frozen_js_map(source: str, name: str) -> dict[str, str]:
    match = re.search(
        rf"const\s+{re.escape(name)}\s*=\s*Object\.freeze\((\{{.*?\}})\);",
        source,
        re.S,
    )
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def resolve_local(current: str, href: str) -> Path | None:
    if not href or href.startswith(("#", "mailto:", "tel:")):
        return None
    parts = urlsplit(href)
    if parts.scheme in {"http", "https"}:
        base = urlsplit(BASE_URL)
        if parts.netloc != base.netloc or not parts.path.startswith(base.path):
            return None
        relative = unquote(parts.path[len(base.path):])
    elif parts.scheme or parts.netloc:
        return None
    else:
        relative = str((Path(current).parent / unquote(parts.path)).as_posix())
    candidate = (ROOT / relative).resolve()
    if not candidate.suffix:
        candidate = candidate / "index.html"
    return candidate


def relative_anchor_target(current: str, href: str) -> str | None:
    target = resolve_local(current, href)
    if target is None:
        return None
    try:
        return target.relative_to(ROOT).as_posix()
    except ValueError:
        return None


def crawl_anchor_graph(starts: set[str], nodes: set[str]) -> set[str]:
    reached = set(starts)
    pending = list(starts)
    while pending:
        current = pending.pop()
        path = ROOT / current
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for href in attr_values(text, "a", "href"):
            target = relative_anchor_target(current, href)
            if target in nodes and target not in reached:
                reached.add(target)
                pending.append(target)
    return reached


def check() -> dict:
    locales = load_locales()
    catalog = load_catalog()
    errors: list[str] = []
    expected_hreflang = set(OFFICIAL) | {"x-default"}
    store_urls = {app["canonical_app_store_url"] for app in catalog["apps"]}
    visible: dict[tuple[str, str], str] = {}
    canonical_owners: dict[str, list[str]] = {}
    checked = 0

    for locale in OFFICIAL:
        for surface in SURFACES:
            relative = route(locale, surface)
            path = ROOT / relative
            if not path.is_file():
                errors.append(f"{relative}: missing required surface")
                continue
            checked += 1
            text = path.read_text(encoding="utf-8")
            plain = visible_text(text)
            visible[(locale, surface)] = plain

            if attr_values(text, "html", "lang") != [locale]:
                errors.append(f"{relative}: html lang mismatch")
            want_dir = "rtl" if locale in RTL else "ltr"
            if attr_values(text, "html", "dir") != [want_dir]:
                errors.append(f"{relative}: html dir must be {want_dir}")
            canonical = attr_values(text, "link", "href", ("rel", "canonical"))
            if canonical != [route_url(locale, surface)]:
                errors.append(f"{relative}: canonical mismatch")
            else:
                canonical_owners.setdefault(canonical[0], []).append(relative)

            found: dict[str, str] = {}
            for match in re.finditer(r"<link\b([^>]*)>", text, re.I):
                attrs = match.group(1)
                rel = re.search(r"\brel\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
                lang = re.search(r"\bhreflang\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
                href = re.search(r"\bhref\s*=\s*[\"']([^\"']+)[\"']", attrs, re.I)
                if rel and rel.group(1).lower() == "alternate" and lang and href:
                    found[lang.group(1)] = html.unescape(href.group(1))
            if set(found) != expected_hreflang:
                errors.append(f"{relative}: hreflang set is not the official 50 plus x-default")
            else:
                for code in OFFICIAL:
                    if found[code] != route_url(code, surface):
                        errors.append(f"{relative}: hreflang {code} target mismatch")
                        break
                if found["x-default"] != route_url("en-US", surface):
                    errors.append(f"{relative}: x-default must point at en-US")

            schema = re.search(
                r'<script\b[^>]*id=["\']support-surface-schema["\'][^>]*>(.*?)</script>',
                text, re.I | re.S)
            try:
                if not schema:
                    raise ValueError
                json.loads(schema.group(1))
            except (ValueError, json.JSONDecodeError):
                errors.append(f"{relative}: invalid JSON-LD block")

            emails = {value.lower() for value in EMAIL_RE.findall(text)}
            if emails != {EMAIL}:
                errors.append(f"{relative}: unapproved public email {sorted(emails - {EMAIL})}")
            if SECRET_RE.search(text):
                errors.append(f"{relative}: possible secret material")
            if (PLACEHOLDER_RE.search(plain) or MARKER_RE.search(plain)
                    or RAW_KEY_RE.search(HOSTNAME_RE.sub(" ", plain))):
                errors.append(f"{relative}: placeholder or raw key visible")
            if BANNED_TEXT_RE.search(plain):
                errors.append(f"{relative}: banned brand or unverifiable claim")
            if APP_NAME_LATIN not in text:
                errors.append(f"{relative}: app identity missing")

            for href in attr_values(text, "a", "href"):
                if href.lower().startswith("mailto:"):
                    if EMAIL not in href.lower():
                        errors.append(f"{relative}: wrong mailto target")
                    continue
                if href.startswith("https://apps.apple.com/") and href not in store_urls:
                    errors.append(f"{relative}: App Store URL is not the exact catalog URL")
                    continue
                target = resolve_local(relative, href)
                if target is not None and not target.is_file():
                    errors.append(f"{relative}: broken local link {href}")

            module = re.search(r"<!-- ls-family:start -->(.*?)<!-- ls-family:end -->",
                               text, re.S)
            if not module:
                errors.append(f"{relative}: cross-promo module missing")
            elif len(re.findall(r'href="https://apps\.apple\.com/',
                                module.group(1))) < MIN_CARDS:
                errors.append(f"{relative}: cross-promo has fewer than {MIN_CARDS} cards")

            if surface == "support" and EMAIL not in plain:
                errors.append(f"{relative}: support surface must publish the contact address")
            if surface == "privacy" and len(re.findall(r"<h[23]\b", text, re.I)) < 4:
                errors.append(f"{relative}: privacy surface is too thin")
            if locale not in ENGLISH:
                pattern = SCRIPT_RANGES.get(locale)
                if pattern and not re.search(pattern, plain):
                    errors.append(f"{relative}: expected script absent")

    for surface in SURFACES:
        baseline = visible.get(("en-US", surface))
        for locale in OFFICIAL:
            if locale in ENGLISH:
                continue
            if baseline and visible.get((locale, surface)) == baseline:
                errors.append(f"{locale}/{surface}: English fallback copied")
    for locale in OFFICIAL:
        if len({visible.get((locale, surface)) for surface in SURFACES}) != len(SURFACES):
            errors.append(f"{locale}: surfaces are not distinct")
    if len(canonical_owners) != len(OFFICIAL) * len(SURFACES):
        errors.append("static surfaces: canonical targets are not unique")
    for canonical, owners in canonical_owners.items():
        if len(owners) != 1:
            errors.append(f"static surfaces: canonical {canonical} owned by {owners}")

    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    sitemap_urls = [
        html.unescape(value)
        for value in re.findall(r"<loc>([^<]+)</loc>", sitemap)
    ]
    expected_urls = expected_sitemap_urls()
    if any(urlsplit(url).query or urlsplit(url).fragment for url in sitemap_urls):
        errors.append("sitemap.xml: query strings and fragments are forbidden")
    if len(sitemap_urls) != len(set(sitemap_urls)):
        errors.append("sitemap.xml: duplicate URL")
    if sitemap_urls != expected_urls:
        missing = sorted(set(expected_urls) - set(sitemap_urls))
        extra = sorted(set(sitemap_urls) - set(expected_urls))
        errors.append(f"sitemap.xml: exact static contract mismatch "
                      f"missing={missing} extra={extra}")

    expected_root = family_module(catalog, "en-US", standalone=True)
    for name in ROOT_PAGES:
        text = (ROOT / name).read_text(encoding="utf-8")
        canonical = attr_values(text, "link", "href", ("rel", "canonical"))
        if canonical != [ROOT_CANONICALS[name]]:
            errors.append(f"{name}: root canonical mismatch")
        if name in ROOT_X_DEFAULTS:
            x_default = alternate_values(text, "x-default")
            if x_default != [ROOT_X_DEFAULTS[name]]:
                errors.append(f"{name}: root x-default mismatch")
        module = FAMILY_BLOCK_RE.search(text)
        if not module:
            errors.append(f"{name}: cross-promo module missing")
        elif module.group(0) != expected_root:
            errors.append(f"{name}: cross-promo module is stale")
        for href in attr_values(text, "a", "href"):
            if href.startswith("https://apps.apple.com/") and href not in store_urls:
                errors.append(f"{name}: App Store URL is not the exact catalog URL")

    for name, contract in ROOT_NAV_CONTRACTS.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        html_count, marker_count, data_pages = root_data_page_state(text)
        if (
            html_count != 1
            or marker_count != 1
            or data_pages != [ROOT_PAGE_SURFACES[name]]
        ):
            errors.append(
                f"{name}: html data-page must be exactly "
                f"{ROOT_PAGE_SURFACES[name]}"
            )
        anchors = root_nav_anchors(text)
        if len(anchors) != len(contract):
            errors.append(f"{name}: root nav must contain exactly support and privacy")
            continue
        destinations = []
        for anchor, (href, key, current) in zip(anchors, contract):
            destinations.append(anchor.get("href", ""))
            if anchor.get("href") != href or anchor.get("data-i18n") != key:
                errors.append(f"{name}: root nav destination contract mismatch")
            if (anchor.get("aria-current") == "page") != current:
                errors.append(f"{name}: root nav current-page state mismatch")
            if "data-surface" in anchor or "data-localized-link" in anchor:
                errors.append(f"{name}: root nav must stay static and unambiguous")
        if len(destinations) != len(set(destinations)):
            errors.append(f"{name}: root nav has duplicate destinations")
        for locale, copy in locales.items():
            labels = [
                " ".join(copy[key].split()).casefold()
                for _, key, _ in contract
            ]
            if len(labels) != len(set(labels)):
                errors.append(f"{name}: duplicate visible nav label in {locale}")

    required_static = {
        route(locale, surface)
        for locale in OFFICIAL
        for surface in SURFACES
    }
    for name, (expected_href, expected_label) in ROOT_STATIC_ENTRIES.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        marker = ROOT_STATIC_ENTRY_RE.findall(text)
        if marker != [root_static_entry(name)]:
            errors.append(f"{name}: generated static footer entry is stale")
        footer = footer_link_anchors(text)
        labels = [" ".join(anchor.get("text", "").split()).casefold()
                  for anchor in footer]
        if len(labels) != len(set(labels)):
            errors.append(f"{name}: footer links have duplicate visible labels")
        static_anchors = [
            anchor for anchor in footer
            if relative_anchor_target(name, anchor.get("href", "")) in required_static
        ]
        if [(anchor.get("href"), anchor.get("text")) for anchor in static_anchors] != [
            (expected_href, expected_label)
        ]:
            errors.append(f"{name}: static footer entry contract mismatch")

    graph_nodes = required_static | set(ROOT_STATIC_ENTRIES)
    reached = crawl_anchor_graph(set(ROOT_STATIC_ENTRIES), graph_nodes)
    unreachable = sorted(required_static - reached)
    if unreachable:
        errors.append(
            f"root anchor graph reaches {len(required_static) - len(unreachable)}/"
            f"{len(required_static)} required surfaces; missing={unreachable[:10]}"
        )

    loader = (ROOT / "localize.js").read_text(encoding="utf-8")
    route_map = frozen_js_map(loader, "STATIC_LOCALE_ROUTES")
    if list(route_map) != OFFICIAL or route_map != {code: code for code in OFFICIAL}:
        errors.append("localize.js: static locale route map is not fixed exact-50")
    surface_map = frozen_js_map(loader, "STATIC_SURFACES")
    if surface_map != {"index": "support.html", "privacy": "privacy.html"}:
        errors.append("localize.js: legacy root surface map mismatch")
    for contract in (
        'preserved.delete("lang")',
        "next.hash = window.location.hash",
        "window.location.replace(target.href)",
    ):
        if contract not in loader:
            errors.append(f"localize.js: missing legacy route contract {contract!r}")

    if errors:
        raise SystemExit("\n".join(errors[:80]))
    return {
        "site": "zodira-support",
        "locales": len(OFFICIAL),
        "surfaces_per_locale": len(SURFACES),
        "surfaces_checked": checked,
        "anchor_surfaces_reachable": len(required_static & reached),
        "crosspromo_apps": [app["key"] for app in catalog["apps"]],
        "own_app_store_url": None,
        "digest": digest(),
        "status": "PASS",
    }


def digest() -> str:
    sha = hashlib.sha256()
    for locale in OFFICIAL:
        for surface in SURFACES:
            relative = route(locale, surface)
            sha.update(relative.encode())
            sha.update(b"\0")
            sha.update((ROOT / relative).read_bytes())
            sha.update(b"\0")
    return sha.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "check", "digest"))
    args = parser.parse_args()
    if args.command == "build":
        print(json.dumps(build(), sort_keys=True))
    elif args.command == "check":
        print(json.dumps(check(), sort_keys=True))
    else:
        print(digest())


if __name__ == "__main__":
    main()
