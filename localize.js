(() => {
  "use strict";

  const locales = window.ZODIRA_LOCALES;
  if (!locales || typeof locales !== "object") {
    throw new Error("Zodira locale dictionary is unavailable");
  }

  const STATIC_LOCALE_ROUTES = Object.freeze({
    "ar-SA": "ar-SA",
    "bn-BD": "bn-BD",
    "ca": "ca",
    "zh-Hans": "zh-Hans",
    "zh-Hant": "zh-Hant",
    "hr": "hr",
    "cs": "cs",
    "da": "da",
    "nl-NL": "nl-NL",
    "en-AU": "en-AU",
    "en-CA": "en-CA",
    "en-GB": "en-GB",
    "en-US": "en-US",
    "fi": "fi",
    "fr-CA": "fr-CA",
    "fr-FR": "fr-FR",
    "de-DE": "de-DE",
    "el": "el",
    "gu-IN": "gu-IN",
    "he": "he",
    "hi": "hi",
    "hu": "hu",
    "id": "id",
    "it": "it",
    "ja": "ja",
    "kn-IN": "kn-IN",
    "ko": "ko",
    "ms": "ms",
    "ml-IN": "ml-IN",
    "mr-IN": "mr-IN",
    "no": "no",
    "or-IN": "or-IN",
    "pl": "pl",
    "pt-BR": "pt-BR",
    "pt-PT": "pt-PT",
    "pa-IN": "pa-IN",
    "ro": "ro",
    "ru": "ru",
    "sk": "sk",
    "sl-SI": "sl-SI",
    "es-MX": "es-MX",
    "es-ES": "es-ES",
    "sv": "sv",
    "ta-IN": "ta-IN",
    "te-IN": "te-IN",
    "th": "th",
    "tr": "tr",
    "uk": "uk",
    "ur-PK": "ur-PK",
    "vi": "vi"
  });
  const STATIC_SURFACES = Object.freeze({
    "index": "support.html",
    "privacy": "privacy.html"
  });
  const supported = Object.keys(STATIC_LOCALE_ROUTES);
  const dictionaryLocales = Object.keys(locales);
  if (
    dictionaryLocales.length !== supported.length
    || dictionaryLocales.some((code, index) => code !== supported[index])
  ) {
    throw new Error("Zodira locale dictionary and static route map differ");
  }

  const params = new URLSearchParams(window.location.search);
  const requested = params.get("lang");
  const page = document.documentElement.dataset.page;
  const surface = Object.hasOwn(STATIC_SURFACES, page)
    ? STATIC_SURFACES[page]
    : null;

  const staticSurfaceURL = (localeCode) => {
    if (!surface || !Object.hasOwn(STATIC_LOCALE_ROUTES, localeCode)) {
      return null;
    }
    const next = new URL(
      `${STATIC_LOCALE_ROUTES[localeCode]}/${surface}`,
      window.location.href,
    );
    const preserved = new URLSearchParams(window.location.search);
    preserved.delete("lang");
    next.search = preserved.toString();
    next.hash = window.location.hash;
    return next;
  };

  if (requested && Object.hasOwn(STATIC_LOCALE_ROUTES, requested)) {
    const target = staticSurfaceURL(requested);
    if (target) {
      const canonical = document.querySelector('link[rel="canonical"]');
      if (canonical) {
        const staticCanonical = new URL(target.href);
        staticCanonical.search = "";
        staticCanonical.hash = "";
        canonical.href = staticCanonical.href;
      }
      window.location.replace(target.href);
      return;
    }
  }

  const locale = "en-US";
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
      const next = staticSurfaceURL(select.value);
      if (next) {
        window.location.assign(next.href);
      }
    });
  }

  document.documentElement.dataset.localeReady = locale;
})();
