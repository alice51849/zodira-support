"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const localeSource = fs.readFileSync(path.join(ROOT, "locales.js"), "utf8");
const localizeSource = fs.readFileSync(path.join(ROOT, "localize.js"), "utf8");
const localePrefix = "window.ZODIRA_LOCALES = ";
const locales = JSON.parse(localeSource.slice(localePrefix.length, -2));
const ROOT_PAGE_SURFACES = {
  "index.html": "index",
  "privacy.html": "privacy",
};

function assertRootDataPage(source, filename) {
  const html = [...source.matchAll(/<html\b([^>]*)>/gi)];
  assert.equal(html.length, 1, `${filename} must contain exactly one html element`);
  const dataPages = [...html[0][1].matchAll(
    /(?:^|\s)data-page\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))/gi,
  )].map((match) => match[1] ?? match[2] ?? match[3]);
  const markerCount = [...html[0][1].matchAll(
    /(?:^|\s)data-page(?=\s|=|$)/gi,
  )].length;
  assert.equal(markerCount, 1, `${filename} must contain one data-page marker`);
  assert.deepEqual(dataPages, [ROOT_PAGE_SURFACES[filename]]);
}

function runRootPage(href, page, withSelect = false) {
  const current = new URL(href);
  const canonical = { href: page === "privacy"
    ? "https://alice51849.github.io/zodira-support/privacy.html"
    : "https://alice51849.github.io/zodira-support/" };
  const select = {
    value: "",
    options: [],
    append(option) {
      this.options.push(option);
    },
    addEventListener(name, handler) {
      if (name === "change") this.onChange = handler;
    },
  };
  const documentElement = { dataset: { page }, lang: "en-US", dir: "ltr" };
  let replaced = null;
  let assigned = null;
  const location = {
    href: current.href,
    search: current.search,
    hash: current.hash,
    replace(value) {
      replaced = value;
    },
    assign(value) {
      assigned = value;
    },
  };
  const document = {
    documentElement,
    createElement() {
      return {};
    },
    querySelector(selector) {
      if (selector === 'link[rel="canonical"]') return canonical;
      if (selector === "#locale-select" && withSelect) return select;
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  const context = vm.createContext({
    URL,
    URLSearchParams,
    document,
    window: { location },
  });
  vm.runInContext(localeSource, context, { filename: "locales.js" });
  vm.runInContext(localizeSource, context, { filename: "localize.js" });
  return {
    assigned: () => assigned,
    canonical,
    documentElement,
    replaced,
    select,
  };
}

test("all legacy locale queries replace to their static surface", () => {
  for (const locale of Object.keys(locales)) {
    for (const [page, rootPath, file] of [
      ["index", "", "support.html"],
      ["privacy", "privacy.html", "privacy.html"],
    ]) {
      const result = runRootPage(
        `https://alice51849.github.io/zodira-support/${rootPath}`
          + `?utm_source=legacy&lang=${encodeURIComponent(locale)}&keep=a%2Fb#details`,
        page,
      );
      assert.ok(result.replaced, `${locale}/${page} did not redirect`);
      const target = new URL(result.replaced);
      assert.equal(
        target.pathname,
        `/zodira-support/${locale}/${file}`,
        `${locale}/${page} route mismatch`,
      );
      assert.equal(target.searchParams.get("utm_source"), "legacy");
      assert.equal(target.searchParams.get("keep"), "a/b");
      assert.equal(target.searchParams.has("lang"), false);
      assert.equal(target.hash, "#details");
      assert.equal(
        result.canonical.href,
        `https://alice51849.github.io/zodira-support/${locale}/${file}`,
      );
    }
  }
});

test("unknown locale values never redirect", () => {
  for (const requested of [
    "https://example.com/",
    "//example.com/",
    "../en-US",
    "en-US/../../",
    "not-a-locale",
  ]) {
    const result = runRootPage(
      "https://alice51849.github.io/zodira-support/"
        + `?lang=${encodeURIComponent(requested)}&next=https://example.com/#support`,
      "index",
    );
    assert.equal(result.replaced, null);
    assert.equal(result.documentElement.dataset.localeReady, "en-US");
    assert.equal(
      result.canonical.href,
      "https://alice51849.github.io/zodira-support/",
    );
  }
});

test("locale picker uses the same confined static route map", () => {
  const result = runRootPage(
    "https://alice51849.github.io/zodira-support/privacy.html"
      + "?utm_source=picker#privacy",
    "privacy",
    true,
  );
  assert.equal(result.select.options.length, 50);
  result.select.value = "zh-Hant";
  result.select.onChange();
  const target = new URL(result.assigned());
  assert.equal(target.pathname, "/zodira-support/zh-Hant/privacy.html");
  assert.equal(target.search, "?utm_source=picker");
  assert.equal(target.hash, "#privacy");

  result.select.value = "https://example.com/";
  result.select.onChange();
  assert.equal(result.assigned(), target.href);
});

test("sitemap contains only unique root and static locale URLs", () => {
  const source = fs.readFileSync(path.join(ROOT, "sitemap.xml"), "utf8");
  const urls = [...source.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => (
    match[1]
  ));
  const expected = [
    "https://alice51849.github.io/zodira-support/",
    "https://alice51849.github.io/zodira-support/privacy.html",
    "https://alice51849.github.io/zodira-support/terms.html",
  ];
  for (const locale of Object.keys(locales)) {
    for (const surface of ["index.html", "support.html", "privacy.html"]) {
      expected.push(
        `https://alice51849.github.io/zodira-support/${locale}/${surface}`,
      );
    }
  }
  assert.deepEqual(urls, expected);
  assert.equal(new Set(urls).size, urls.length);
  assert.equal(urls.some((url) => new URL(url).search), false);
});

test("root nav and static canonicals remain unambiguous", () => {
  const rootContracts = {
    "index.html": [
      ["index.html", "support", true],
      ["privacy.html", "privacy", false],
    ],
    "privacy.html": [
      ["index.html", "support", false],
      ["privacy.html", "privacy", true],
    ],
  };
  for (const [filename, contract] of Object.entries(rootContracts)) {
    const source = fs.readFileSync(path.join(ROOT, filename), "utf8");
    assertRootDataPage(source, filename);
    const nav = source.match(/<nav class="nav"[^>]*>([\s\S]*?)<\/nav>/);
    assert.ok(nav, `${filename} nav missing`);
    const anchors = [...nav[1].matchAll(/<a\s+([^>]*)>([\s\S]*?)<\/a>/g)];
    assert.equal(anchors.length, contract.length);
    for (let index = 0; index < contract.length; index += 1) {
      const [href, key, current] = contract[index];
      const attrs = anchors[index][1];
      assert.match(attrs, new RegExp(`href="${href.replace(".", "\\.")}"`));
      assert.match(attrs, new RegExp(`data-i18n="${key}"`));
      assert.equal(/aria-current="page"/.test(attrs), current);
      assert.equal(/data-(?:surface|localized-link)=/.test(attrs), false);
    }
    for (const copy of Object.values(locales)) {
      const labels = contract.map(([, key]) => copy[key].trim().toLocaleLowerCase());
      assert.equal(new Set(labels).size, labels.length);
    }
  }

  const canonicalOwners = new Set();
  for (const locale of Object.keys(locales)) {
    for (const surface of ["index.html", "support.html", "privacy.html"]) {
      const source = fs.readFileSync(path.join(ROOT, locale, surface), "utf8");
      const canonical = source.match(/<link rel="canonical" href="([^"]+)">/);
      assert.ok(canonical, `${locale}/${surface} canonical missing`);
      assert.equal(
        canonical[1],
        `https://alice51849.github.io/zodira-support/${locale}/${surface}`,
      );
      assert.equal(canonicalOwners.has(canonical[1]), false);
      canonicalOwners.add(canonical[1]);
      assert.match(
        source,
        new RegExp(
          `<link rel="alternate" hreflang="x-default" href="`
          + `https://alice51849\\.github\\.io/zodira-support/en-US/`
          + `${surface.replace(".", "\\.")}">`,
        ),
      );
    }
  }
  assert.equal(canonicalOwners.size, 150);
});

test("root data-page guard rejects missing, wrong and duplicate markers", () => {
  for (const [filename, expected] of Object.entries(ROOT_PAGE_SURFACES)) {
    const source = fs.readFileSync(path.join(ROOT, filename), "utf8");
    const marker = ` data-page="${expected}"`;
    assert.ok(source.includes(marker), `${filename} canonical marker missing`);
    const wrong = expected === "index" ? "support" : "index";
    const mutations = {
      missing: source.replace(marker, ""),
      wrong: source.replace(marker, ` data-page="${wrong}"`),
      duplicate: source.replace(marker, marker + marker),
    };
    for (const [kind, mutation] of Object.entries(mutations)) {
      assert.throws(
        () => assertRootDataPage(mutation, filename),
        `${filename}/${kind} must fail`,
      );
    }
  }
});

test("root footer entries make all static surfaces anchor-reachable", () => {
  const siteRoot = new URL("https://alice51849.github.io/zodira-support/");
  const footerContracts = {
    "index.html": ["en-US/support.html", "Localized support pages"],
    "privacy.html": ["en-US/privacy.html", "Localized privacy pages"],
  };
  const required = new Set();
  for (const locale of Object.keys(locales)) {
    for (const surface of ["index.html", "support.html", "privacy.html"]) {
      required.add(`${locale}/${surface}`);
    }
  }

  function internalTarget(current, href) {
    const target = new URL(href.replaceAll("&amp;", "&"), new URL(current, siteRoot));
    if (target.origin !== siteRoot.origin
        || !target.pathname.startsWith(siteRoot.pathname)) {
      return null;
    }
    let relative = decodeURIComponent(
      target.pathname.slice(siteRoot.pathname.length),
    );
    if (!relative || relative.endsWith("/")) relative += "index.html";
    return relative;
  }

  for (const [filename, [expectedHref, expectedLabel]]
    of Object.entries(footerContracts)) {
    const source = fs.readFileSync(path.join(ROOT, filename), "utf8");
    const footer = source.match(
      /<div class="footer-links">([\s\S]*?)<\/div>/,
    );
    assert.ok(footer, `${filename} footer links missing`);
    const anchors = [...footer[1].matchAll(/<a\s+([^>]*)>([\s\S]*?)<\/a>/g)];
    const labels = anchors.map((anchor) => anchor[2].trim().toLocaleLowerCase());
    assert.equal(new Set(labels).size, labels.length);
    const staticAnchors = anchors.filter((anchor) => {
      const href = anchor[1].match(/href="([^"]+)"/)?.[1] || "";
      return required.has(internalTarget(filename, href));
    });
    assert.equal(staticAnchors.length, 1);
    assert.match(staticAnchors[0][1], new RegExp(`href="${expectedHref}"`));
    assert.equal(staticAnchors[0][2].trim(), expectedLabel);
    assert.equal(
      source.match(/<!-- root-static-entry:start -->/g)?.length,
      1,
    );
  }

  const nodes = new Set([...required, ...Object.keys(footerContracts)]);
  const reached = new Set(Object.keys(footerContracts));
  const pending = [...reached];
  while (pending.length) {
    const current = pending.pop();
    const source = fs.readFileSync(path.join(ROOT, current), "utf8");
    for (const match of source.matchAll(/<a\b[^>]*href="([^"]+)"[^>]*>/g)) {
      const target = internalTarget(current, match[1]);
      if (nodes.has(target) && !reached.has(target)) {
        reached.add(target);
        pending.push(target);
      }
    }
  }
  const reachedRequired = [...required].filter((node) => reached.has(node));
  assert.equal(reachedRequired.length, 150);
});
