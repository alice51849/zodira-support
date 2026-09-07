from __future__ import annotations

import json
import re
import subprocess
import unittest

import lint_site as gate


class PrivacyDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (gate.ROOT / "locales.js").read_text(encoding="utf-8")
        cls.locales, cls.parse_errors = gate.parse_locales(cls.source)
        cls.english = gate.english_copy_index(cls.locales)
        cls.privacy = (gate.ROOT / "privacy.html").read_text(encoding="utf-8")
        cls.support = (gate.ROOT / "index.html").read_text(encoding="utf-8")
        cls.loader = (gate.ROOT / "localize.js").read_text(encoding="utf-8")

    def check_record(self, locale: str, record: dict) -> list[str]:
        return gate.lint_locale_record(locale, record, self.english)

    def check_template(self, source: str) -> list[str]:
        return gate.lint_privacy_template(self.locales, source, self.support)

    def test_current_exact50_site_contract(self) -> None:
        self.assertEqual(self.parse_errors, [])
        self.assertEqual(tuple(self.locales), gate.OFFICIAL_LOCALES)
        self.assertEqual(len(gate.PRIVACY_COPY_KEYS), 19)
        self.assertEqual(len(gate.PRIVACY_DISCLOSURE_KEYS), 15)
        self.assertEqual(set(gate.PRIVACY_SEMANTIC_MARKERS), gate.LOCALE_SET)
        self.assertEqual(self.check_template(self.privacy), [])
        self.assertEqual(gate.lint_runtime_schema(self.loader), [])
        self.assertEqual(gate.lint_identity_and_contact(), [])
        self.assertEqual(gate.lint_sitemap_and_robots(), [])
        for name, canonical in gate.PAGES.items():
            with self.subTest(page=name):
                self.assertEqual(
                    gate.lint_page(name, canonical, set(gate.REQUIRED_LOCALE_KEYS)), []
                )
        css = (gate.ROOT / "styles.css").read_text(encoding="utf-8")
        fields = re.search(r"\.payload-fields\s*\{([^}]+)\}", css).group(1)
        for declaration in (
            "direction: ltr", "unicode-bidi: isolate", "overflow-wrap: anywhere",
        ):
            self.assertIn(declaration, fields)

    def test_missing_extra_and_duplicate_dictionary_entries_fail(self) -> None:
        for locale in gate.OFFICIAL_LOCALES:
            with self.subTest(locale=locale):
                data = dict(self.locales)
                del data[locale]
                self.assertIn("exact-50 mismatch", gate.lint_locales(data)[0])
        data = {**self.locales, "bg": self.locales["en-US"]}
        self.assertIn("exact-50 mismatch", gate.lint_locales(data)[0])
        for source in (
            self.source.replace('"ar-SA": {', '"ar-SA": {}, "ar-SA": {', 1),
            self.source.replace('"watchTransfer":', '"watchTransfer": "", "watchTransfer":', 1),
        ):
            with self.subTest(duplicate=source[:80]):
                self.assertIn("duplicate dictionary key", gate.parse_locales(source)[1][0])
        for source in ("window.ZODIRA_LOCALES = [];\n", "not a dictionary"):
            self.assertTrue(gate.parse_locales(source)[1])

    def test_every_disclosure_rejects_missing_empty_placeholder_and_raw_key(self) -> None:
        for locale, original in self.locales.items():
            for key in gate.PRIVACY_COPY_KEYS:
                with self.subTest(locale=locale, key=key, mutation="missing"):
                    record = dict(original)
                    del record[key]
                    self.assertIn("schema mismatch", self.check_record(locale, record)[0])
                for invalid in (None, " \t", "translation needed", key):
                    with self.subTest(locale=locale, key=key, invalid=invalid):
                        record = {**original, key: invalid}
                        self.assertTrue(self.check_record(locale, record))
        for invalid in ([], 19, False):
            self.assertTrue(self.check_record("en-US", {**self.locales["en-US"], "commerce": invalid}))

    def test_every_nonenglish_disclosure_rejects_english_fallback(self) -> None:
        for locale, original in self.locales.items():
            if locale.startswith("en-"):
                continue
            for key in gate.PRIVACY_COPY_KEYS:
                english = self.locales["en-US"][key]
                for replacement in (
                    english,
                    " \n" + english.upper() + " !!! ",
                    english + " " + original[key][:2],
                ):
                    with self.subTest(locale=locale, key=key, replacement=replacement[:30]):
                        errors = self.check_record(locale, {**original, key: replacement})
                        self.assertIn(
                            f"locales.js: {locale}/{key} falls back to English", errors
                        )

    def test_each_nonlatin_disclosure_requires_native_script(self) -> None:
        for locale in gate.SCRIPT_MARKERS:
            for key in gate.PRIVACY_COPY_KEYS:
                with self.subTest(locale=locale, key=key):
                    original = self.locales[locale]
                    ascii_copy = "Untranslated " + "".join(
                        character for character in original[key] if character.isascii()
                    )
                    errors = self.check_record(locale, {**original, key: ascii_copy})
                    self.assertIn(
                        f"locales.js: {locale}/{key} lacks its native script", errors
                    )

    def test_all_semantic_qualifiers_and_dataflow_tokens_are_required(self) -> None:
        for locale, original in self.locales.items():
            for key, markers in gate.PRIVACY_SEMANTIC_MARKERS[locale].items():
                for marker in markers:
                    with self.subTest(locale=locale, key=key, marker=marker):
                        self.assertIn(marker, original[key])
                        record = {**original, key: original[key].replace(marker, "")}
                        errors = self.check_record(locale, record)
                        self.assertIn(
                            f"locales.js: {locale}/{key} missing semantic marker {marker!r}", errors
                        )
            for key, tokens in gate.PRIVACY_DATAFLOW_TOKENS.items():
                for token in tokens:
                    with self.subTest(locale=locale, key=key, token=token):
                        value = original[key]
                        for form in gate.DATAFLOW_TOKEN_FORMS.get((locale, token), (token,)):
                            value = value.replace(form, "")
                        errors = self.check_record(locale, {**original, key: value})
                        self.assertIn(
                            f"locales.js: {locale}/{key} missing dataflow token {token!r}", errors
                        )

    def test_hero_cannot_restore_an_absolute_offline_claim(self) -> None:
        for locale, original in self.locales.items():
            with self.subTest(locale=locale):
                lines = original["description"].splitlines()
                lines[3] = "Everything works fully offline. No data leaves your device."
                errors = self.check_record(locale, {**original, "description": "\n".join(lines)})
                self.assertIn(
                    f"locales.js: {locale}/description must reuse the qualified local disclosure",
                    errors,
                )

    def test_disclosures_cannot_be_removed_hidden_or_relegated_to_metadata(self) -> None:
        for key in gate.PRIVACY_COPY_KEYS:
            attribute = f'data-i18n="{key}"'
            for replacement in (
                f'data-unused="{key}"',
                f'hidden {attribute}',
                f'aria-hidden="true" {attribute}',
                f'style="display: none" {attribute}',
                f'style="visibility: hidden" {attribute}',
                f'style="opacity: 0" {attribute}',
            ):
                with self.subTest(key=key, mutation=replacement):
                    self.assertTrue(
                        self.check_template(self.privacy.replace(attribute, replacement, 1))
                    )
            pattern = rf"<(p|h2)\b[^>]*{re.escape(attribute)}[^>]*>.*?</\1>"
            changed, count = re.subn(
                pattern, f'<meta data-i18n="{key}">', self.privacy, count=1, flags=re.DOTALL
            )
            self.assertEqual(count, 1, key)
            self.assertTrue(self.check_template(changed))
        hidden_article = self.privacy.replace(
            '<article class="policy">', '<article class="policy" hidden>', 1
        )
        self.assertTrue(self.check_template(hidden_article))

    def test_watch_payload_fields_are_exact_and_visible(self) -> None:
        for field in gate.WATCH_PAYLOAD_FIELDS:
            code = f"<code>{field}</code>"
            for replacement in ("", f"<!--{code}-->", f"<code hidden>{field}</code>"):
                with self.subTest(field=field, replacement=replacement):
                    errors = self.check_template(self.privacy.replace(code, replacement, 1))
                    self.assertIn(
                        "privacy.html: visible Watch payload fields must match the exact minimal schema",
                        errors,
                    )
        extra = self.privacy.replace(
            "<code>issuedAt</code>", "<code>issuedAt</code><code>birthProfile</code>", 1
        )
        self.assertTrue(self.check_template(extra))
        self.assertTrue(self.check_template(
            self.privacy.replace('aria-labelledby="watch-payload-label"', "", 1)
        ))

    def test_static_copy_metadata_and_date_cannot_drift(self) -> None:
        for key in gate.PRIVACY_COPY_KEYS:
            with self.subTest(key=key):
                changed = self.privacy.replace(
                    f'data-i18n="{key}">', f'data-i18n="{key}">Outdated ', 1
                )
                self.assertNotEqual(changed, self.privacy)
                self.assertIn(
                    f"privacy.html: {key} static disclosure differs from en-US",
                    self.check_template(changed),
                )
        self.assertTrue(self.check_template(
            self.privacy.replace(gate.PRIVACY_UPDATED, "2026-08-29")
        ))
        self.assertTrue(self.check_template(
            self.privacy.replace('data-i18n-content="noCollection"', "", 1)
        ))

    def test_runtime_required_keys_cannot_omit_disclosures(self) -> None:
        for key in gate.PRIVACY_DISCLOSURE_KEYS:
            with self.subTest(key=key):
                altered = re.sub(rf'"{key}"\s*,?', "", self.loader, count=1)
                self.assertTrue(gate.lint_runtime_schema(altered))
        self.assertTrue(gate.lint_runtime_schema(
            self.loader.replace("supported.length !== 50", "false")
        ))

    def test_actual_javascript_exact50_rendering_and_fail_closed_paths(self) -> None:
        pages = {}
        for name, source in (("privacy.html", self.privacy), ("index.html", self.support)):
            parser = gate.DisclosureParser()
            parser.feed(source)
            pages[name] = [
                {"tag": node["tag"], "attrs": node["attrs"]} for node in parser.elements
            ]
        payload = json.dumps({
            "loader": self.loader, "locales": self.locales, "pages": pages,
            "newKeys": gate.PRIVACY_DISCLOSURE_KEYS,
        }, ensure_ascii=False)
        result = subprocess.run(
            ["node", "-e", JS_RENDER_TEST], input=payload, text=True,
            capture_output=True, timeout=120, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("100 localized pages; 1500 incomplete-copy and 50 missing-locale rejections", result.stdout)


JS_RENDER_TEST = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const data = JSON.parse(fs.readFileSync(0, "utf8"));
function render(page, requested, locales = data.locales) {
  const nodes = data.pages[page].map(({tag, attrs}) => ({
    tag, attrs: {...attrs}, dataset: {
      i18n: attrs["data-i18n"], i18nContent: attrs["data-i18n-content"]
    }, textContent: "", href: attrs.href,
    setAttribute(key, value) { this.attrs[key] = value; },
    getAttribute(key) { return this.attrs[key]; }
  }));
  const select = {
    options: [], handlers: {}, value: requested,
    append(option) { this.options.push(option); },
    addEventListener(type, handler) { this.handlers[type] = handler; }
  };
  const canonical = nodes.find(node => node.attrs.rel === "canonical");
  const document = {
    documentElement: {dataset: {}},
    createElement(tag) { assert.equal(tag, "option"); return {}; },
    querySelector(selector) {
      if (selector === "#locale-select") return select;
      if (selector === 'link[rel="canonical"]') return canonical;
      throw new Error(`Unexpected selector ${selector}`);
    },
    querySelectorAll(selector) {
      if (selector === "[data-i18n]") return nodes.filter(n => n.attrs["data-i18n"]);
      if (selector === "[data-i18n-content]") return nodes.filter(n => n.attrs["data-i18n-content"]);
      if (selector === "a[data-localized-link]") {
        return nodes.filter(n => n.tag === "a" && Object.hasOwn(n.attrs, "data-localized-link"));
      }
      throw new Error(`Unexpected selector ${selector}`);
    }
  };
  const location = {
    search: requested ? `?lang=${requested}&test=preserve` : "",
    href: `https://open.cait518.cc/zodira-support/${page}${requested ? "?lang="+requested+"&test=preserve" : ""}`,
    assign(url) { this.assigned = url; }
  };
  vm.runInNewContext(data.loader, {
    window: {ZODIRA_LOCALES: locales, location}, document, URL, URLSearchParams
  }, {timeout: 1000});
  return {document, nodes, select, canonical, location};
}
let rendered = 0;
let incomplete = 0;
let missingLocales = 0;
for (const locale of Object.keys(data.locales)) {
  for (const page of Object.keys(data.pages)) {
    const result = render(page, locale);
    assert.equal(result.document.documentElement.lang, locale);
    assert.equal(result.document.documentElement.dataset.localeReady, locale);
    assert.equal(result.document.documentElement.dir, ["ar-SA", "he", "ur-PK"].includes(locale) ? "rtl" : "ltr");
    for (const node of result.nodes) {
      if (node.dataset.i18n) {
        assert.equal(node.textContent, data.locales[locale][node.dataset.i18n], `${locale}/${node.dataset.i18n}`);
      }
      if (node.dataset.i18nContent) {
        assert.equal(node.attrs.content, data.locales[locale][node.dataset.i18nContent].replace(/\s+/g, " ").trim());
      }
      if (node.tag === "a" && Object.hasOwn(node.attrs, "data-localized-link")) {
        assert.equal(new URL(node.href).searchParams.get("lang"), locale);
      }
    }
    assert.equal(new URL(result.canonical.href).searchParams.get("lang"), locale);
    assert.equal(result.select.options.length, 50);
    assert.deepEqual(result.select.options.filter(o => o.selected).map(o => o.value), [locale]);
    const next = locale === "ja" ? "ar-SA" : "ja";
    result.select.value = next;
    result.select.handlers.change();
    assert.equal(new URL(result.location.assigned).searchParams.get("lang"), next);
    assert.equal(new URL(result.location.assigned).searchParams.get("test"), "preserve");
    rendered++;
  }
  for (const key of data.newKeys) {
    for (const missing of [true, false]) {
      const copy = {...data.locales, [locale]: {...data.locales[locale]}};
      if (missing) delete copy[locale][key];
      else copy[locale][key] = " \t";
      assert.throws(() => render("privacy.html", locale, copy), /Incomplete Zodira locale/);
      incomplete++;
    }
  }
  const absent = {...data.locales};
  delete absent[locale];
  assert.throws(() => render("privacy.html", locale, absent), /requires all 50 official locales/);
  missingLocales++;
}
for (const requested of ["", "unsupported"]) {
  assert.equal(render("privacy.html", requested).document.documentElement.lang, "en-US");
}
console.log(`${rendered} localized pages; ${incomplete} incomplete-copy and ${missingLocales} missing-locale rejections`);
"""


if __name__ == "__main__":
    unittest.main()
