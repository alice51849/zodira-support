(() => {
  "use strict";

  const locales = window.ZODIRA_LOCALES;
  if (!locales || typeof locales !== "object") {
    throw new Error("Zodira locale dictionary is unavailable");
  }

  const supported = Object.keys(locales);
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("lang");
  const locale = requested && Object.hasOwn(locales, requested) ? requested : "en-US";
  const copy = locales[locale];
  if (!copy) {
    throw new Error(`Missing Zodira locale: ${locale}`);
  }

  const required = [
    "languageName", "name", "subtitle", "description", "workflow",
    "support", "privacy", "local", "lens", "purchase", "noSubscription",
    "restore", "delete", "noCollection", "deletion", "restoreHelp",
    "titleSupport", "titlePrivacy",
  ];
  for (const key of required) {
    if (typeof copy[key] !== "string" || !copy[key].trim()) {
      throw new Error(`Incomplete Zodira locale ${locale}: ${key}`);
    }
  }

  document.documentElement.lang = locale;
  document.documentElement.dir = ["ar-SA", "he", "ur-PK"].includes(locale)
    ? "rtl"
    : "ltr";

  for (const element of document.querySelectorAll("[data-i18n]")) {
    const key = element.dataset.i18n;
    if (!Object.hasOwn(copy, key)) {
      throw new Error(`Unknown Zodira locale key ${locale}: ${key}`);
    }
    element.textContent = copy[key];
  }

  for (const element of document.querySelectorAll("[data-i18n-content]")) {
    const key = element.dataset.i18nContent;
    if (!Object.hasOwn(copy, key)) {
      throw new Error(`Unknown Zodira content key ${locale}: ${key}`);
    }
    element.setAttribute("content", copy[key].replace(/\s+/g, " ").trim());
  }

  const select = document.querySelector("#locale-select");
  if (select) {
    for (const optionLocale of supported) {
      const option = document.createElement("option");
      option.value = optionLocale;
      option.textContent = locales[optionLocale].languageName;
      option.selected = optionLocale === locale;
      select.append(option);
    }
    select.addEventListener("change", () => {
      const next = new URL(window.location.href);
      next.searchParams.set("lang", select.value);
      window.location.assign(next.href);
    });
  }

  for (const anchor of document.querySelectorAll("a[data-localized-link]")) {
    const href = anchor.getAttribute("href");
    if (!href) continue;
    const localized = new URL(href, window.location.href);
    localized.searchParams.set("lang", locale);
    anchor.href = localized.href;
  }

  if (requested === locale) {
    const canonical = document.querySelector('link[rel="canonical"]');
    if (canonical) {
      const localizedCanonical = new URL(canonical.href);
      localizedCanonical.searchParams.set("lang", locale);
      canonical.href = localizedCanonical.href;
    }
  }

  document.documentElement.dataset.localeReady = locale;
})();
