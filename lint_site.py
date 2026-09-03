#!/usr/bin/env python3
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parent


def _find_app_root() -> Path | None:
    """Locate the Zodira app repo that owns the canonical App Store metadata.

    The support site used to live inside the app repo; it is now its own
    repository, so the metadata is looked up next to it, in ~/22_Zodira, or
    wherever ZODIRA_APP_ROOT points.
    """
    candidates = []
    if env := os.environ.get("ZODIRA_APP_ROOT"):
        candidates.append(Path(env).expanduser())
    candidates.append(ROOT.parent)
    candidates.append(Path.home() / "22_Zodira")
    for candidate in candidates:
        if (candidate / "StoreAssets/metadata").is_dir():
            return candidate
    return None


APP_ROOT = _find_app_root()
SITE_ROOT = "https://open.cait518.cc/zodira-support/"
# App Store Connect still has the github.io URLs registered, and this
# change deliberately does not touch App Store metadata: GitHub Pages
# remains the origin, so those URLs keep resolving.  Page-facing URLs
# (canonical, alternates, sitemap, robots) moved to our own domain.
ASC_SITE_ROOT = "https://alice51849.github.io/zodira-support/"
PAGES = {
    "index.html": SITE_ROOT,
    "privacy.html": f"{SITE_ROOT}privacy.html",
    "terms.html": f"{SITE_ROOT}terms.html",
}
OFFICIAL_LOCALES = (
    "ar-SA", "bn-BD", "ca", "zh-Hans", "zh-Hant", "hr", "cs", "da",
    "nl-NL", "en-AU", "en-CA", "en-GB", "en-US", "fi", "fr-CA",
    "fr-FR", "de-DE", "el", "gu-IN", "he", "hi", "hu", "id", "it",
    "ja", "kn-IN", "ko", "ms", "ml-IN", "mr-IN", "no", "or-IN", "pl",
    "pt-BR", "pt-PT", "pa-IN", "ro", "ru", "sk", "sl-SI", "es-MX",
    "es-ES", "sv", "ta-IN", "te-IN", "th", "tr", "uk", "ur-PK", "vi",
)
LOCALE_SET = frozenset(OFFICIAL_LOCALES)
REQUIRED_LOCALE_KEYS = frozenset(
    {
        "languageName", "name", "subtitle", "description", "workflow",
        "support", "privacy", "local", "lens", "purchase", "noSubscription",
        "restore", "delete", "noCollection", "deletion", "restoreHelp",
        "titleSupport", "titlePrivacy",
    }
)
CRITICAL_TRANSLATED_KEYS = (
    "support", "privacy", "local", "lens", "purchase", "noSubscription",
    "restore", "delete", "noCollection", "deletion",
)
SCRIPT_MARKERS = {
    "ar-SA": r"[\u0600-\u06ff]",
    "bn-BD": r"[\u0980-\u09ff]",
    "zh-Hans": r"[\u3400-\u9fff]",
    "zh-Hant": r"[\u3400-\u9fff]",
    "el": r"[\u0370-\u03ff]",
    "gu-IN": r"[\u0a80-\u0aff]",
    "he": r"[\u0590-\u05ff]",
    "hi": r"[\u0900-\u097f]",
    "ja": r"[\u3040-\u30ff]",
    "kn-IN": r"[\u0c80-\u0cff]",
    "ko": r"[\uac00-\ud7af]",
    "ml-IN": r"[\u0d00-\u0d7f]",
    "mr-IN": r"[\u0900-\u097f]",
    "or-IN": r"[\u0b00-\u0b7f]",
    "pa-IN": r"[\u0a00-\u0a7f]",
    "ru": r"[\u0400-\u04ff]",
    "ta-IN": r"[\u0b80-\u0bff]",
    "te-IN": r"[\u0c00-\u0c7f]",
    "th": r"[\u0e00-\u0e7f]",
    "uk": r"[\u0400-\u04ff]",
    "ur-PK": r"[\u0600-\u06ff]",
}
CANONICAL_METADATA = (
    APP_ROOT / "StoreAssets/metadata/build19-exact50.json" if APP_ROOT else None
)
ALLOWED_EMAIL = "hourstag.app@gmail.com"
BUNDLE_ID = "com.alice51849." + "Astrea"
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PLACEHOLDER_RE = re.compile(
    r"\b(?:TODO|TBD|PLACEHOLDER|TRANSLATION NEEDED)\b|"
    r"\{\{[^}]+\}\}|\[\[[^\]]+\]\]|<missing>",
)
LEGACY_TOKENS = (
    "astrea" + "-support",
    "sup_" + "astrea",
    "legacy public" + " path",
)


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.ids: set[str] = set()
        self.canonical: list[str] = []
        self.i18n_keys: set[str] = set()
        self.html_lang = ""
        self.h1_count = 0
        self.has_viewport = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "html":
            self.html_lang = values.get("lang", "")
        if tag == "meta" and values.get("name", "").casefold() == "viewport":
            self.has_viewport = bool(values.get("content"))
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        if tag == "script" and values.get("src"):
            self.hrefs.append(values["src"])
        if values.get("id"):
            self.ids.add(values["id"])
        if values.get("data-i18n"):
            self.i18n_keys.add(values["data-i18n"])
        if values.get("data-i18n-content"):
            self.i18n_keys.add(values["data-i18n-content"])
        if tag == "link" and values.get("href"):
            if values.get("rel", "").casefold() == "canonical":
                self.canonical.append(values["href"])
            else:
                self.hrefs.append(values["href"])
        if tag == "h1":
            self.h1_count += 1


def expected_support_url(locale: str) -> str:
    return f"{ASC_SITE_ROOT}?lang={locale}"


def expected_privacy_url(locale: str) -> str:
    return f"{ASC_SITE_ROOT}privacy.html?lang={locale}"


def parse_locales() -> tuple[dict[str, dict[str, str]], list[str]]:
    errors: list[str] = []
    path = ROOT / "locales.js"
    source = path.read_text(encoding="utf-8")
    prefix = "window.ZODIRA_LOCALES = "
    if not source.startswith(prefix) or not source.endswith(";\n"):
        return {}, ["locales.js: expected one explicit local dictionary assignment"]
    try:
        locales = json.loads(source[len(prefix):-2])
    except json.JSONDecodeError as error:
        return {}, [f"locales.js: invalid dictionary JSON: {error}"]
    if set(locales) != LOCALE_SET:
        errors.append(
            "locales.js: exact-50 mismatch "
            f"missing={sorted(LOCALE_SET - set(locales))} "
            f"extra={sorted(set(locales) - LOCALE_SET)}"
        )
        return locales, errors

    english = locales["en-US"]
    for locale in OFFICIAL_LOCALES:
        record = locales[locale]
        if not isinstance(record, dict) or set(record) != REQUIRED_LOCALE_KEYS:
            errors.append(f"locales.js: {locale} schema mismatch")
            continue
        for key, value in record.items():
            if not isinstance(value, str) or not value.strip():
                errors.append(f"locales.js: {locale}/{key} is empty")
            elif "\ufffd" in value or PLACEHOLDER_RE.search(value):
                errors.append(f"locales.js: {locale}/{key} has placeholder text")
            elif value.strip() in REQUIRED_LOCALE_KEYS:
                errors.append(f"locales.js: {locale}/{key} exposes a raw key")
        if not locale.startswith("en-"):
            for key in CRITICAL_TRANSLATED_KEYS:
                if record.get(key) == english.get(key):
                    errors.append(
                        f"locales.js: {locale}/{key} falls back to en-US"
                    )
        marker = SCRIPT_MARKERS.get(locale)
        if marker:
            critical = " ".join(record.get(key, "") for key in CRITICAL_TRANSLATED_KEYS)
            if not re.search(marker, critical):
                errors.append(f"locales.js: {locale} lacks its native script")
    return locales, errors


def lint_page(
    name: str,
    canonical: str,
    locale_keys: set[str],
) -> list[str]:
    errors: list[str] = []
    path = ROOT / name
    source = path.read_text(encoding="utf-8")
    parser = PageParser()
    parser.feed(source)
    parser.close()

    if not source.lstrip().casefold().startswith("<!doctype html>"):
        errors.append(f"{name}: missing HTML5 doctype")
    expected_lang = "en-US" if name in {"index.html", "privacy.html"} else "en"
    if parser.html_lang != expected_lang:
        errors.append(f"{name}: html lang must be {expected_lang}")
    if not parser.has_viewport:
        errors.append(f"{name}: missing viewport metadata")
    if parser.h1_count != 1:
        errors.append(f"{name}: expected one h1, found {parser.h1_count}")
    if parser.canonical != [canonical]:
        errors.append(f"{name}: canonical mismatch {parser.canonical!r}")
    if unknown := sorted(parser.i18n_keys - locale_keys):
        errors.append(f"{name}: unknown locale keys {unknown}")
    if name in {"index.html", "privacy.html"}:
        for required_asset in ("locales.js", "localize.js"):
            if required_asset not in parser.hrefs:
                errors.append(f"{name}: missing {required_asset}")
        if 'id="locale-select"' not in source:
            errors.append(f"{name}: missing exact locale selector")

    for email in EMAIL_RE.findall(source):
        if email.casefold() != ALLOWED_EMAIL:
            errors.append(f"{name}: disallowed public email {email}")
    for href in parser.hrefs:
        parsed = urlsplit(href)
        if parsed.scheme in {"https", "mailto"}:
            if parsed.scheme == "mailto":
                address = unquote(parsed.path).casefold()
                if address != ALLOWED_EMAIL:
                    errors.append(f"{name}: disallowed mailto address {address}")
            continue
        if parsed.scheme or parsed.netloc:
            errors.append(f"{name}: unsupported link {href}")
            continue
        if not parsed.path:
            if parsed.fragment and parsed.fragment not in parser.ids:
                errors.append(f"{name}: missing local anchor #{parsed.fragment}")
            continue
        target = (path.parent / unquote(parsed.path)).resolve()
        if ROOT not in target.parents and target != ROOT:
            errors.append(f"{name}: link escapes site root: {href}")
        elif not target.is_file():
            errors.append(f"{name}: broken local link {href}")
    return errors


def lint_identity_and_contact() -> list[str]:
    errors: list[str] = []
    site_files = (
        "index.html", "privacy.html", "terms.html", "robots.txt", "sitemap.xml",
        "styles.css", "locales.js", "localize.js",
    )
    # The site is its own repository now: it lints what it publishes.  The
    # fastlane URL mirrors inside the app repo keep their own gate there.
    public_sources = [(ROOT / name) for name in site_files]

    for path in public_sources:
        source = path.read_text(encoding="utf-8")
        folded = source.casefold()
        for token in LEGACY_TOKENS:
            if token in folded:
                errors.append(f"{path}: stale public identity token {token!r}")
        if re.search(r"\b" + "Astrea" + r"\b", source.replace(BUNDLE_ID, "")):
            errors.append(f"{path}: stale public Astrea brand")
        for email in EMAIL_RE.findall(source):
            if email.casefold() != ALLOWED_EMAIL:
                errors.append(f"{path}: disallowed public email {email}")

    site_source = "\n".join(
        (ROOT / name).read_text(encoding="utf-8") for name in site_files
    )
    if site_source.count(BUNDLE_ID) != 1:
        errors.append("privacy bundle ID must appear exactly once on the public site")
    without_bundle = site_source.replace(BUNDLE_ID, "")
    if re.search(r"\b" + "Astrea" + r"\b", without_bundle):
        errors.append("public site contains stale Astrea branding outside the legal bundle ID")
    if BUNDLE_ID not in (ROOT / "privacy.html").read_text(encoding="utf-8"):
        errors.append("privacy.html: missing the registered bundle ID")

    campaigns = re.findall(r"utm_campaign=([^&\"']+)", site_source)
    if not campaigns:
        errors.append("site: missing support-site campaign")
    elif any(campaign != "sup_zodira" for campaign in campaigns):
        errors.append(f"site: campaign mismatch {campaigns}")
    return errors


PRIMARY_TABS = ("Today", "Tarot", "Astrology", "Destiny", "Me")


def lint_store_consistency(
    locales: dict[str, dict[str, str]],
) -> list[str]:
    """The support site must describe the product the App Store listing sells.

    A reviewer opens the support URL straight from the listing, so any drift
    between the two is a Guideline 2.3 (Accurate Metadata) risk.  The canonical
    store metadata is the single source of truth: the site reuses its
    sentences rather than paraphrasing them, and the secondary Decision
    Journal must never be presented as the product.
    """
    errors: list[str] = []
    if CANONICAL_METADATA is None or not CANONICAL_METADATA.is_file():
        return [
            "canonical App Store metadata not found; "
            "set ZODIRA_APP_ROOT to the Zodira app repository"
        ]
    canonical = json.loads(CANONICAL_METADATA.read_text(encoding="utf-8"))
    meta = canonical.get("_meta", {})
    if tuple(meta.get("localeOrder", ())) != OFFICIAL_LOCALES:
        errors.append("canonical metadata localeOrder is not the official exact-50 order")
    if set(canonical) - {"_meta"} != LOCALE_SET:
        errors.append("canonical metadata locale records are not exact-50")
    if tuple(meta.get("primaryTabs", ())) != PRIMARY_TABS:
        errors.append(f"canonical metadata primaryTabs must be {list(PRIMARY_TABS)}")

    for locale in OFFICIAL_LOCALES:
        record = canonical.get(locale, {})
        site = locales.get(locale)
        if not isinstance(site, dict) or not record:
            continue

        for field, value in (
            ("supportUrl", expected_support_url(locale)),
            ("privacyPolicyUrl", expected_privacy_url(locale)),
        ):
            actual = record.get(field, "")
            if actual != value:
                errors.append(f"canonical {locale}/{field} must be {value}")
            query = parse_qs(urlsplit(actual).query, strict_parsing=True) if actual else {}
            if query != {"lang": [locale]}:
                errors.append(f"canonical {locale}/{field}: query must be exactly lang={locale}")

        store_name = record.get("name", "").strip()
        site_name = site.get("name", "").strip()
        if site_name != store_name and not site_name.startswith(f"{store_name} — "):
            errors.append(
                f"locales.js: {locale}/name {site_name!r} does not match "
                f"the App Store name {store_name!r}"
            )
        if site.get("subtitle") != record.get("subtitle"):
            errors.append(f"locales.js: {locale}/subtitle differs from the App Store subtitle")
        for key in ("titleSupport", "titlePrivacy"):
            if not site.get(key, "").startswith(store_name):
                errors.append(f"locales.js: {locale}/{key} must lead with the App Store name")

        paragraphs = [part.strip() for part in record.get("description", "").split("\n\n")]
        lines = [line.strip() for line in site.get("description", "").splitlines() if line.strip()]
        if not 3 <= len(lines) <= 6:
            errors.append(
                f"locales.js: {locale}/description must be 3-6 lines, found {len(lines)}"
            )
        reused = sum(1 for part in paragraphs if part and part in lines)
        if reused < 3:
            errors.append(
                f"locales.js: {locale}/description reuses only {reused} "
                "verbatim App Store paragraphs"
            )

        disclosure = record.get("journalFreeDisclosure", "").strip()
        if disclosure:
            if not lines or not lines[-1].startswith(disclosure):
                errors.append(
                    f"locales.js: {locale}/description must close with the exact "
                    "App Store Decision Journal disclosure"
                )
            if lines and lines[0].startswith(disclosure):
                errors.append(
                    f"locales.js: {locale}/description leads with the Decision Journal, "
                    "which is a secondary feature"
                )

        workflow = site.get("workflow", "")
        missing_steps = [step for step in ("01", "02", "03", "04", "05") if step not in workflow]
        if missing_steps:
            errors.append(
                f"locales.js: {locale}/workflow is missing the primary-tab "
                f"walkthrough steps {missing_steps}"
            )
    return errors


def lint_sitemap_and_robots() -> list[str]:
    errors: list[str] = []
    source = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    urls = set(re.findall(r"<loc>([^<]+)</loc>", source))
    # The sitemap is served from this site's own origin, so it may only list
    # URLs on that origin -- the ASC-registered github.io URLs still resolve,
    # but a cross-origin sitemap entry is invalid.  Every canonical page must
    # be listed; localized ?lang= variants of those pages are optional.
    expected = set(PAGES.values())
    if missing := sorted(expected - urls):
        errors.append(f"sitemap.xml: missing canonical pages {missing}")
    for url in sorted(urls - expected):
        parsed = urlsplit(url)
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        query = parse_qs(parsed.query, strict_parsing=True) if parsed.query else {}
        if base not in expected:
            errors.append(f"sitemap.xml: URL outside this site {url}")
        elif set(query) != {"lang"} or query["lang"][0] not in LOCALE_SET:
            errors.append(f"sitemap.xml: localized URL must carry one official lang {url}")
    robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
    expected_line = f"Sitemap: {SITE_ROOT}sitemap.xml"
    if expected_line not in robots:
        errors.append(f"robots.txt: missing {expected_line}")
    return errors


def main() -> None:
    locales, errors = parse_locales()
    locale_keys = set(next(iter(locales.values()), {}))
    for name, canonical in PAGES.items():
        errors.extend(lint_page(name, canonical, locale_keys))
    errors.extend(lint_identity_and_contact())
    errors.extend(lint_store_consistency(locales))
    errors.extend(lint_sitemap_and_robots())

    loader = (ROOT / "localize.js").read_text(encoding="utf-8")
    for contract in (
        "URLSearchParams", "data-localized-link", "document.documentElement.dir",
        "Object.hasOwn(locales, requested)",
    ):
        if contract not in loader:
            errors.append(f"localize.js: missing fail-closed locale contract {contract!r}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(
        "site lint passed: canonical identity, exact-50 native dictionary, "
        "App Store product consistency, sitemap, contact and legal bundle exception"
    )


if __name__ == "__main__":
    main()
