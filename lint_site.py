#!/usr/bin/env python3
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
import json
import re
import sys

ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT.parent
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
CANONICAL_METADATA = APP_ROOT / "StoreAssets/metadata/build15-exact50.json"
FASTLANE_METADATA = APP_ROOT / "fastlane/metadata"
BACKUP_METADATA = APP_ROOT / "fastlane/metadata_backup_aso"
URL_BUILDER = APP_ROOT / "tools/build_asc_meta.py"
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
    current_metadata_files = [
        CANONICAL_METADATA,
        *FASTLANE_METADATA.glob("*/*.txt"),
        URL_BUILDER,
    ]
    public_sources = [(ROOT / name) for name in site_files] + current_metadata_files
    url_mirrors = list(FASTLANE_METADATA.glob("*/*_url.txt"))
    if BACKUP_METADATA.is_dir():
        url_mirrors.extend(BACKUP_METADATA.glob("*/*_url.txt"))

    for path in public_sources + url_mirrors:
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


def lint_metadata_urls(
    locales: dict[str, dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    canonical = json.loads(CANONICAL_METADATA.read_text(encoding="utf-8"))
    if tuple(canonical.get("_meta", {}).get("localeOrder", ())) != OFFICIAL_LOCALES:
        errors.append("canonical metadata localeOrder is not the official exact-50 order")
    if set(canonical) - {"_meta"} != LOCALE_SET:
        errors.append("canonical metadata locale records are not exact-50")

    actual_dirs = {path.name for path in FASTLANE_METADATA.iterdir() if path.is_dir()}
    if actual_dirs != LOCALE_SET:
        errors.append(
            "fastlane metadata locale mismatch "
            f"missing={sorted(LOCALE_SET - actual_dirs)} "
            f"extra={sorted(actual_dirs - LOCALE_SET)}"
        )
    for locale in OFFICIAL_LOCALES:
        expected = {
            "supportUrl": expected_support_url(locale),
            "privacyPolicyUrl": expected_privacy_url(locale),
        }
        record = canonical.get(locale, {})
        for field, value in expected.items():
            if record.get(field) != value:
                errors.append(f"canonical {locale}/{field} must be {value}")
        if locale in locales:
            if locales[locale].get("description") != record.get("description"):
                errors.append(f"locales.js: {locale}/description differs from canonical")
            if locales[locale].get("workflow") != record.get("whatsNew"):
                errors.append(f"locales.js: {locale}/workflow differs from canonical")

        files = {
            "support_url.txt": expected_support_url(locale),
            "privacy_url.txt": expected_privacy_url(locale),
            "marketing_url.txt": expected_support_url(locale),
        }
        for filename, value in files.items():
            path = FASTLANE_METADATA / locale / filename
            actual = path.read_text(encoding="utf-8") if path.is_file() else ""
            if actual != value:
                errors.append(f"{path}: expected {value!r}, found {actual!r}")
            parsed = urlsplit(actual)
            query = parse_qs(parsed.query, strict_parsing=True) if actual else {}
            if query != {"lang": [locale]}:
                errors.append(f"{path}: locale query must be exactly lang={locale}")

    if BACKUP_METADATA.is_dir():
        for path in BACKUP_METADATA.glob("*/*_url.txt"):
            locale = path.parent.name
            if locale not in LOCALE_SET:
                errors.append(f"{path}: unexpected backup locale")
                continue
            expected = (
                expected_privacy_url(locale)
                if path.name == "privacy_url.txt"
                else expected_support_url(locale)
            )
            if path.read_text(encoding="utf-8") != expected:
                errors.append(f"{path}: stale direct URL mirror")
    return errors


def lint_sitemap_and_robots() -> list[str]:
    errors: list[str] = []
    source = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    urls = set(re.findall(r"<loc>([^<]+)</loc>", source))
    expected = set(PAGES.values())
    expected.update(expected_support_url(locale) for locale in OFFICIAL_LOCALES)
    expected.update(expected_privacy_url(locale) for locale in OFFICIAL_LOCALES)
    if urls != expected:
        errors.append(
            "sitemap.xml: URL mismatch "
            f"missing={sorted(expected - urls)} extra={sorted(urls - expected)}"
        )
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
    errors.extend(lint_metadata_urls(locales))
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
        "localized URLs, mirrors, sitemap, contact and legal bundle exception"
    )


if __name__ == "__main__":
    main()
