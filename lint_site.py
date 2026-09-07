#!/usr/bin/env python3
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
import json
import os
import re
import sys
import unicodedata

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
PRIVACY_DISCLOSURE_KEYS = (
    "localHeading", "localData", "commerceHeading", "commerce",
    "watchHeading", "watchTransfer", "watchFieldsHeading", "watchRetention",
    "sharingHeading", "sharing", "externalHeading", "external",
    "contact", "keychain", "backups",
)
PRIVACY_COPY_KEYS = (
    "local", "noCollection", "delete", "deletion", *PRIVACY_DISCLOSURE_KEYS,
)
PRIVACY_UPDATED = "2026-09-08"
WATCH_PAYLOAD_FIELDS = (
    "schemaVersion", "sourceID", "revision", "operation", "recordID",
    "nextAction", "nextActionWasCondensed", "outcome", "recordUpdatedAt", "issuedAt",
)
PRIVACY_DATAFLOW_TOKENS = {
    "local": ("Apple Watch",),
    "noCollection": ("Zodira", "Apple"),
    "commerce": ("StoreKit", "Apple"),
    "watchTransfer": ("WatchConnectivity", "Apple Watch", "180"),
    "watchRetention": ("Watch", "tombstone"),
    "sharing": ("ShareLink", "JSON", "Watch"),
    "external": ("EULA", "IP", "GitHub Pages", "Apple"),
    "contact": ("hourstag.app@gmail.com", "Gmail"),
    "deletion": ("Zodira", "Keychain", "Watch", "Apple"),
    "keychain": ("Keychain", "operationID", "feature", "consumedAt"),
    "backups": ("Apple", "Zodira"),
}
DATAFLOW_TOKEN_FORMS = {
    ("hr", "Zodira"): ("Zodira", "Zodire"),
    ("cs", "Zodira"): ("Zodira", "Zodiry"),
    ("hu", "Zodira"): ("Zodira", "Zodirának"),
    ("pl", "Zodira"): ("Zodira", "Zodiry"),
    ("sk", "Zodira"): ("Zodira", "Zodiry"),
    ("sl-SI", "Zodira"): ("Zodira", "Zodire"),
    ("sl-SI", "Apple"): ("Apple", "Appla"),
}
REQUIRED_LOCALE_KEYS = frozenset(
    {
        "languageName", "name", "subtitle", "description", "workflow",
        "support", "privacy", "local", "lens", "purchase", "noSubscription",
        "restore", "delete", "noCollection", "deletion", "restoreHelp",
        "titleSupport", "titlePrivacy", *PRIVACY_DISCLOSURE_KEYS,
    }
)
CRITICAL_TRANSLATED_KEYS = (
    "support", "privacy", "local", "lens", "purchase", "noSubscription",
    "restore", "delete", "noCollection", "deletion",
    *PRIVACY_DISCLOSURE_KEYS,
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
    re.IGNORECASE,
)
LEGACY_TOKENS = (
    "astrea" + "-support",
    "sup_" + "astrea",
    "legacy public" + " path",
)

# These guards preserve decisive qualifications, not runtime or native-review evidence.
PRIVACY_SEMANTIC_FIELDS = (
    "noCollection", "commerce", "watchTransfer", "watchRetention",
    "sharing", "keychain", "backups", "contact",
)
PRIVACY_MARKER_ROWS = {
    "en-US": (
        ("We do not collect", "are separate"),
        ("product and price loading", "verification and restores", "retention rules"),
        ("minimal journal snapshot", "not to a developer server", "excludes the birth profile"),
        ("after the Watch receives and accepts it", "disconnected Watch can retain"),
        ("complete record in JSON", "only the question", "Local deletion does not recall"),
        ("outside the app container", "can survive", "does not guarantee"),
        ("Existing backups are not erased",),
        ("we receive", "request deletion"),
    ),
    "zh-Hans": (
        ("不会通过 App 收集", "不同的情形"),
        ("加载商品和价格", "购买验证及恢复购买", "保留规则由 Apple 决定"),
        ("精简的单条手记摘要", "而不是开发者服务器", "不包含出生资料"),
        ("收到并接受清除消息", "可能仍保留先前的副本"),
        ("完整单条记录", "只分享问题", "不会撤回这些副本"),
        ("独立于 App 容器", "可能在删除或重新安装 App 后继续保留", "不保证清除此账本"),
        ("不会清除已有备份",),
        ("我们会", "收到你的邮箱地址", "申请删除"),
    ),
    "zh-Hant": (
        ("不會透過 App 蒐集", "不同的情形"),
        ("載入商品與價格", "購買驗證及回復購買項目", "保留規則由 Apple 決定"),
        ("精簡的單筆手札摘要", "而不是開發者伺服器", "不包含出生資料"),
        ("收到並接受清除訊息", "可能仍保留先前的副本"),
        ("完整單筆記錄", "只分享問題", "不會收回這些副本"),
        ("獨立於 App 容器", "可能在刪除或重新安裝 App 後繼續保留", "不保證清除此帳本"),
        ("不會清除既有備份",),
        ("我們會", "收到你的電子郵件地址", "申請刪除"),
    ),
    "ja": (
        ("収集することはありません", "これとは区別して"),
        ("商品の情報や価格", "購入の復元", "保持については Apple が定めます"),
        ("必要最小限", "転送先は開発者のサーバーではありません", "出生プロフィール"),
        ("受信して受け入れた後", "以前のコピーが残ることがあります"),
        ("記録全体", "質問だけ", "取り消すことはできません"),
        ("アプリコンテナの外", "再インストール後も残る場合", "消去は保証されません"),
        ("既存のバックアップは消去されません",),
        ("メールアドレス", "届きます", "削除を依頼できます"),
    ),
    "ko": (
        ("수집하지 않습니다", "이와 구분하여"),
        ("상품 및 가격 불러오기", "구매 복원", "보관 기준도 Apple이 정합니다"),
        ("최소한의 일지 요약", "개발자 서버가 아닌", "포함하지 않습니다"),
        ("받고 승인한 뒤", "이전 사본이 남아 있을 수 있습니다"),
        ("기록 한 건 전체", "질문만", "사본은 회수되지 않습니다"),
        ("앱 컨테이너 밖", "다시 설치한 후에도 남을 수", "지워진다는 보장은 없습니다"),
        ("기존 백업은 지워지지 않습니다",),
        ("받게 됩니다", "삭제를 요청할 수 있습니다"),
    ),
    "ca": (
        ("No recollim", "casos diferents"),
        ("productes i preus", "restauració de compres", "regles de conservació"),
        ("resum mínim", "no a un servidor", "No inclou el perfil"),
        ("després que el Watch el rebi i l’accepti", "pot conservar una còpia anterior"),
        ("entrada completa", "només es comparteix la pregunta", "no retira aquestes còpies"),
        ("fora del contenidor", "pot persistir", "no garanteix l’eliminació"),
        ("no elimina les còpies de seguretat existents",),
        ("rebem la teva adreça", "demanar-ne l’eliminació"),
    ),
    "de-DE": (
        ("keine Geburtsdaten", "Davon zu unterscheiden"),
        ("Produkten und Preisen", "Wiederherstellung von Käufen", "Aufbewahrungsregeln"),
        ("auf das Nötigste beschränkten", "nicht an einen Server", "sind nicht enthalten"),
        ("empfangen und akzeptiert hat", "kann noch eine frühere Kopie enthalten"),
        ("vollständigen Eintrag", "nur die Frage", "ruft diese Kopien nicht zurück"),
        ("außerhalb des App-Containers", "überdauern", "garantiert daher nicht"),
        ("entfernt keine bestehenden Backups",),
        ("erhalten wir", "Löschung anfordern"),
    ),
    "fr-FR": (
        ("Nous ne collectons pas", "cas distincts"),
        ("produits et des prix", "restauration", "règles de conservation"),
        ("extrait minimal", "non à un serveur", "Il exclut le profil"),
        ("après réception et acceptation", "peut conserver une ancienne copie"),
        ("entrée complète", "seule la question", "n’efface pas les copies déjà envoyées"),
        ("hors du conteneur", "peut subsister", "ne garantit donc pas"),
        ("n’efface pas les sauvegardes existantes",),
        ("nous recevons", "demander leur suppression"),
    ),
    "fr-CA": (
        ("Nous ne recueillons pas", "situations distinctes"),
        ("produits et des prix", "restauration", "règles de conservation"),
        ("extrait minimal", "non à un serveur", "Il exclut le profil"),
        ("après réception et acceptation", "peut conserver une ancienne copie"),
        ("entrée complète", "seule la question", "n’efface pas les copies déjà envoyées"),
        ("hors du conteneur", "peut subsister", "ne garantit donc pas"),
        ("n’efface pas les sauvegardes existantes",),
        ("nous recevons", "demander leur suppression"),
    ),
    "it": (
        ("Non raccogliamo", "casi distinti"),
        ("prodotti e prezzi", "ripristino", "regole di conservazione"),
        ("sintesi minima", "non a un server", "Non include il profilo"),
        ("dopo che il Watch lo ha ricevuto e accettato", "può conservare una copia precedente"),
        ("voce completa", "solo la domanda", "non ritira queste copie"),
        ("fuori dal contenitore", "può rimanere", "non garantisce la cancellazione"),
        ("non cancella i backup esistenti",),
        ("riceviamo", "richiederne l’eliminazione"),
    ),
    "pt-BR": (
        ("Não coletamos", "situações distintas"),
        ("produtos e preços", "restauração de compras", "regras de retenção"),
        ("resumo mínimo", "não a um servidor", "Não inclui o perfil"),
        ("depois que o Watch a recebe e aceita", "pode manter uma cópia anterior"),
        ("registro completo", "apenas a pergunta", "não recolhe essas cópias"),
        ("fora do contêiner", "pode permanecer", "não garante a remoção"),
        ("não exclui os backups existentes",),
        ("receberemos", "pedir a exclusão"),
    ),
    "pt-PT": (
        ("Não recolhemos", "situações distintas"),
        ("produtos e preços", "restauro de compras", "regras de conservação"),
        ("resumo mínimo", "não para um servidor", "Não inclui o perfil"),
        ("depois de o Watch a receber e aceitar", "pode conservar uma cópia anterior"),
        ("entrada completa", "apenas a pergunta", "não retira essas cópias"),
        ("fora do contentor", "pode subsistir", "não garante a remoção"),
        ("não elimina as cópias de segurança existentes",),
        ("recebemos", "pedir a eliminação"),
    ),
    "es-ES": (
        ("No recopilamos", "casos distintos"),
        ("productos y precios", "restauración", "reglas de conservación"),
        ("resumen mínimo", "no a un servidor", "No incluye el perfil"),
        ("después de que el Watch lo reciba y acepte", "puede conservar una copia anterior"),
        ("entrada completa", "solo se comparte la pregunta", "no retira esas copias"),
        ("fuera del contenedor", "puede permanecer", "no garantiza que se elimine"),
        ("no elimina las copias de seguridad existentes",),
        ("recibimos", "solicitar su eliminación"),
    ),
    "es-MX": (
        ("No recopilamos", "situaciones distintas"),
        ("productos y precios", "restauración", "reglas de conservación"),
        ("resumen mínimo", "no a un servidor", "No incluye el perfil"),
        ("después de que el Watch lo recibe y acepta", "puede conservar una copia anterior"),
        ("entrada completa", "solo se comparte la pregunta", "no retira esas copias"),
        ("fuera del contenedor", "puede permanecer", "no garantiza que se elimine"),
        ("no elimina los respaldos existentes",),
        ("recibimos", "solicitar su eliminación"),
    ),
    "da": (
        ("Vi indsamler ikke", "særskilte forhold"),
        ("produkter og priser", "gendannelse af køb", "reglerne for opbevaring"),
        ("begrænset dagbogsuddrag", "ikke til en server", "er ikke med"),
        ("efter at Watch har modtaget og accepteret den", "kan stadig have en tidligere kopi"),
        ("hele posten", "deles kun spørgsmålet", "trækker ikke disse kopier tilbage"),
        ("uden for appens beholder", "kan bestå", "garanterer derfor ikke"),
        ("fjerner ikke eksisterende sikkerhedskopier",),
        ("modtager vi", "bede om sletning"),
    ),
    "no": (
        ("Vi samler ikke inn", "egne forhold"),
        ("produkter og priser", "gjenoppretting av kjøp", "reglene for oppbevaring"),
        ("minimalt dagbokutdrag", "ikke til en server", "er ikke med"),
        ("etter at Watch har mottatt og godtatt den", "kan fortsatt ha en tidligere kopi"),
        ("hele innlegget", "deles bare spørsmålet", "trekker ikke tilbake disse kopiene"),
        ("utenfor appens databeholder", "kan bestå", "garanterer derfor ikke"),
        ("fjerner ikke eksisterende sikkerhetskopier",),
        ("mottar vi", "be om sletting"),
    ),
    "sv": (
        ("Vi samlar inte in", "separata fall"),
        ("produkter och priser", "återställning av köp", "lagringsreglerna"),
        ("begränsat dagboksutdrag", "inte till en server", "ingår inte"),
        ("efter att Watch har tagit emot och godkänt det", "kan ha kvar en tidigare kopia"),
        ("hela anteckningen", "delas bara frågan", "återkallar inte dessa kopior"),
        ("utanför appens behållare", "kan finnas kvar", "garanterar därför inte"),
        ("tar inte bort befintliga säkerhetskopior",),
        ("får vi", "begära radering"),
    ),
    "fi": (
        ("Emme kerää", "erillisiä tapauksia"),
        ("tuotteiden ja hintojen", "palauttamisen", "säilytyksestä"),
        ("suppean päiväkirjaotteen", "ei kehittäjän palvelimelle", "Se ei sisällä"),
        ("Watch on vastaanottanut ja hyväksynyt viestin", "voi jäädä aiempi kopio"),
        ("koko merkinnän", "vain kysymys", "ei peruuta jo jaettuja kopioita"),
        ("ulkopuolella", "voi säilyä", "ei siis takaa"),
        ("ei poista olemassa olevia varmuuskopioita",),
        ("saamme", "pyytää poistamista"),
    ),
    "nl-NL": (
        ("We verzamelen", "niet via de app", "afzonderlijke situaties"),
        ("producten en prijzen", "herstellen van aankopen", "bewaarregels"),
        ("minimaal dagboekuittreksel", "niet naar een server", "zijn niet inbegrepen"),
        ("nadat de Watch het bericht heeft ontvangen en geaccepteerd", "nog een eerdere kopie bewaren"),
        ("volledige notitie", "alleen de vraag", "haalt die kopieën niet terug"),
        ("buiten de appcontainer", "kan blijven bestaan", "garandeert daarom niet"),
        ("verwijdert geen bestaande reservekopieën",),
        ("ontvangen we", "om verwijdering vragen"),
    ),
    "el": (
        ("Δεν συλλέγουμε", "διαφορετικές περιπτώσεις"),
        ("προϊόντων και τιμών", "επαναφορά αγορών", "διατήρηση"),
        ("ελάχιστο απόσπασμα", "όχι σε διακομιστή", "Δεν περιλαμβάνει"),
        ("αφού το Watch το λάβει και το αποδεχθεί", "μπορεί να διατηρεί παλαιότερο αντίγραφο"),
        ("πλήρης εγγραφή", "μόνο η ερώτηση", "δεν ανακαλεί αυτά τα αντίγραφα"),
        ("εκτός του περιέκτη", "μπορεί να παραμείνει", "δεν εγγυάται τη διαγραφή"),
        ("δεν αφαιρεί υπάρχοντα αντίγραφα ασφαλείας",),
        ("λαμβάνουμε", "ζητήσετε διαγραφή"),
    ),
    "hu": (
        ("nem gyűjtjük", "külön kezelendők"),
        ("termékek és árak", "visszaállítását", "megőrzési szabályait"),
        ("minimális naplókivonatot", "nem a fejlesztő szerverére", "Nem tartalmazza"),
        ("miután a Watch megkapta és elfogadta", "megőrizhet egy korábbi másolatot"),
        ("teljes bejegyzés", "csak a kérdés", "nem vonja vissza"),
        ("tárolóján kívül", "után is megmaradhat", "nem garantálja"),
        ("nem törli a meglévő mentéseket",),
        ("megkapjuk", "kérheted a törlést"),
    ),
    "hr": (
        ("ne prikupljamo", "zasebni su slučajevi"),
        ("proizvoda i cijena", "obnovu", "rokove čuvanja"),
        ("minimalan izvadak", "a ne na poslužitelj", "Ne sadrži"),
        ("nakon što je Watch primi i prihvati", "može zadržati raniju kopiju"),
        ("cijeli zapis", "samo pitanje", "ne povlači te kopije"),
        ("izvan spremnika", "može ostati", "ne jamči uklanjanje"),
        ("ne uklanja postojeće sigurnosne kopije",),
        ("primamo", "Brisanje možete zatražiti"),
    ),
    "cs": (
        ("neshromažďujeme", "odlišné případy"),
        ("produktů a cen", "obnovení", "pravidla uchovávání"),
        ("minimální výňatek", "nikoli na server", "Neobsahuje"),
        ("poté, co ji Watch obdrží a přijmou", "mohou uchovávat starší kopii"),
        ("celý záznam", "pouze otázka", "nestáhne zpět"),
        ("mimo kontejner", "může přetrvat", "nezaručuje vymazání"),
        ("neodstraní existující zálohy",),
        ("obdržíme", "O smazání můžete požádat"),
    ),
    "sk": (
        ("nezhromažďujeme", "odlišné prípady"),
        ("produktov a cien", "obnovenie", "pravidlá uchovávania"),
        ("minimálny výňatok", "nie na server", "Neobsahuje"),
        ("keď ju Watch dostanú a prijmú", "môžu uchovávať staršiu kópiu"),
        ("celý záznam", "iba otázka", "nestiahne späť"),
        ("mimo kontajnera", "môže pretrvať", "nezaručuje odstránenie"),
        ("neodstráni existujúce zálohy",),
        ("dostaneme", "O vymazanie môžete požiadať"),
    ),
    "sl-SI": (
        ("ne zbiramo", "ločeni primeri"),
        ("izdelkov in cen", "obnovitev nakupov", "pravila hrambe"),
        ("minimalen izvleček", "ne na razvijalčev strežnik", "Ne vključuje"),
        ("potem ko ga Watch prejme in sprejme", "lahko še vedno hrani starejšo kopijo"),
        ("celoten zapis", "le vprašanje", "teh kopij ne prekliče"),
        ("zunaj vsebnika", "lahko ostane", "ne zagotavlja izbrisa"),
        ("ne izbriše obstoječih varnostnih kopij",),
        ("prejmemo", "Izbris lahko zahtevate"),
    ),
    "pl": (
        ("Nie zbieramy", "odrębne przypadki"),
        ("produktów i cen", "odtwarzanie", "zasady przechowywania"),
        ("ograniczony wyciąg", "a nie na serwer", "Nie obejmuje"),
        ("gdy Watch go odbierze i zaakceptuje", "może zachować wcześniejszą kopię"),
        ("cały wpis", "tylko pytanie", "nie wycofuje tych kopii"),
        ("poza kontenerem", "może pozostać", "nie gwarantuje"),
        ("nie kasuje istniejących kopii zapasowych",),
        ("otrzymujemy", "poprosić o usunięcie"),
    ),
    "ro": (
        ("Nu colectăm", "situații distincte"),
        ("produselor și prețurilor", "restaurarea", "regulile de păstrare"),
        ("extras minim", "nu către un server", "Nu include"),
        ("după ce Watch îl primește și îl acceptă", "poate păstra o copie anterioară"),
        ("însemnarea completă", "doar întrebarea", "nu retrage aceste copii"),
        ("în afara containerului", "poate rămâne", "nu garantează eliminarea"),
        ("nu elimină backupurile existente",),
        ("primim", "solicita ștergerea"),
    ),
    "ru": (
        ("Мы не собираем", "отдельные случаи"),
        ("товары и цены", "восстановление", "правила хранения"),
        ("минимальную выдержку", "а не на сервер", "не передаются"),
        ("после того, как Watch получат и примут его", "могут сохранять предыдущую копию"),
        ("полную запись", "только вопрос", "не отзывает эти копии"),
        ("вне контейнера", "может сохраняться", "не гарантирует стирания"),
        ("не стирает уже существующие резервные копии",),
        ("мы получаем", "Удаление можно запросить"),
    ),
    "uk": (
        ("Ми не збираємо", "окремі випадки"),
        ("товари й ціни", "відновлення", "правила зберігання"),
        ("мінімальний витяг", "а не на сервер", "не передаються"),
        ("після того, як Watch отримає й прийме його", "може зберігати попередню копію"),
        ("повний запис", "лише запитання", "не відкликає цих копій"),
        ("поза контейнером", "може залишатися", "не гарантує стирання"),
        ("не стирає наявних резервних копій",),
        ("ми отримуємо", "Видалення можна попросити"),
    ),
    "ar-SA": (
        ("لا نجمع", "حالات منفصلة"),
        ("المنتجات والأسعار", "واستعادتها", "قواعد الاحتفاظ"),
        ("مقتطفًا محدودًا", "وليس إلى خادم", "ولا يتضمن ملف الميلاد"),
        ("بعد أن تتلقاها Watch وتقبلها", "فقد تحتفظ Watch غير المتصلة بنسخة سابقة"),
        ("المدخلة كاملة", "السؤال فقط", "ولا يؤدي الحذف المحلي إلى سحب"),
        ("خارج حاوية التطبيق", "وقد تبقى", "لا يضمن مسح"),
        ("لا يمسح النسخ الاحتياطية الموجودة",),
        ("نتلقى عنوان بريدك", "طلب حذفها"),
    ),
    "he": (
        ("איננו אוספים", "מקרים נפרדים"),
        ("מוצרים ומחירים", "שחזור רכישות", "כללי השמירה"),
        ("תמצית מצומצמת", "ולא לשרת", "אינם נכללים"),
        ("לאחר שה-Watch מקבל ומאשר אותה", "עשוי לשמור עותק קודם"),
        ("הרשומה המלאה", "רק השאלה", "אינה מבטלת את העותקים"),
        ("מחוץ למכל", "יכול להישאר", "אינה מבטיחה"),
        ("אינה מוחקת גיבויים קיימים",),
        ("אנו מקבלים", "אפשר לבקש מחיקה"),
    ),
    "tr": (
        ("toplamayız", "ayrı durumlardır"),
        ("ürün ve fiyatların", "geri yüklenmesini", "saklama kurallarını"),
        ("asgari bir günlük özetini", "değil", "dâhil değildir"),
        ("alınıp kabul edildikten sonra", "önceki kopyayı tutabilir"),
        ("tam kayıttır", "yalnızca soru", "bu kopyaları geri çekmez"),
        ("kapsayıcısının dışındadır", "sonra kalabilir", "silineceğini garanti etmez"),
        ("mevcut yedekleri silmez",),
        ("üzerinden alırız", "silme talebinde bulunabilirsiniz"),
    ),
    "id": (
        ("Kami tidak mengumpulkan", "hal terpisah"),
        ("produk dan harga", "pemulihan pembelian", "aturan penyimpanan"),
        ("seminimal mungkin", "bukan ke server", "tidak disertakan"),
        ("setelah Watch menerima dan menyetujuinya", "tetap menyimpan salinan sebelumnya"),
        ("entri lengkap", "hanya pertanyaan", "tidak menarik kembali salinan"),
        ("di luar wadah", "dapat tetap ada", "tidak menjamin"),
        ("tidak menghapus cadangan yang sudah ada",),
        ("kami menerima", "meminta penghapusan"),
    ),
    "ms": (
        ("Kami tidak mengumpulkan", "keadaan berasingan"),
        ("produk dan harga", "pemulihan pembelian", "peraturan penyimpanan"),
        ("petikan jurnal yang minimum", "bukan ke pelayan", "tidak disertakan"),
        ("selepas Watch menerima dan meluluskannya", "mungkin masih menyimpan salinan terdahulu"),
        ("catatan lengkap", "hanya soalan", "tidak menarik balik salinan"),
        ("di luar bekas", "boleh kekal", "tidak menjamin"),
        ("tidak memadam sandaran sedia ada",),
        ("kami menerima", "meminta pemadaman"),
    ),
    "vi": (
        ("Chúng tôi không thu thập", "những trường hợp riêng"),
        ("sản phẩm và giá", "khôi phục giao dịch mua", "lưu giữ hồ sơ"),
        ("phần trích tối thiểu", "không gửi đến máy chủ", "không được gửi kèm"),
        ("sau khi Watch nhận và chấp nhận", "có thể vẫn giữ bản sao cũ"),
        ("toàn bộ mục đó", "chỉ câu hỏi", "không thu hồi những bản sao"),
        ("nằm ngoài vùng chứa", "có thể còn lại", "không bảo đảm"),
        ("không xóa các bản sao lưu hiện có",),
        ("chúng tôi nhận", "yêu cầu xóa"),
    ),
    "th": (
        ("เราไม่เก็บรวบรวม", "เป็นคนละกรณี"),
        ("สินค้าและราคา", "กู้คืนรายการซื้อ", "หลักเกณฑ์การเก็บรักษา"),
        ("เฉพาะส่วนที่จำเป็น", "ไม่ใช่เซิร์ฟเวอร์ของผู้พัฒนา", "ไม่รวมโปรไฟล์การเกิด"),
        ("หลังจาก Watch รับและยอมรับข้อความนั้น", "อาจยังเก็บสำเนาเดิมไว้"),
        ("ฉบับเต็มหนึ่งรายการ", "แชร์เฉพาะคำถาม", "ไม่เรียกคืนสำเนาเหล่านี้"),
        ("อยู่นอกพื้นที่เก็บข้อมูล", "อาจคงอยู่หลังลบ", "ไม่รับประกัน"),
        ("ไม่ลบข้อมูลสำรองที่มีอยู่",),
        ("เราจะได้รับ", "ขอให้ลบข้อมูลได้"),
    ),
    "bn-BD": (
        ("সংগ্রহ করি না", "আলাদা বিষয়"),
        ("পণ্য ও দাম", "পুনরুদ্ধারের", "কত দিন রাখবে"),
        ("ন্যূনতম একটি অংশ", "সার্ভারে নয়", "পুরো লেখা এতে থাকে না"),
        ("গ্রহণ ও অনুমোদন করার পর", "আগের কপি থেকে যেতে পারে"),
        ("সম্পূর্ণ এন্ট্রি", "শুধু প্রশ্নটি", "কপিগুলো ফেরত নেওয়া হয় না"),
        ("সংরক্ষণস্থানের বাইরে", "পরও থাকতে পারে", "মুছে যাওয়ার নিশ্চয়তা নেই"),
        ("আগের ব্যাকআপ মুছে যায় না",),
        ("আমরা আপনার ঠিকানা", "মুছে ফেলার অনুরোধ"),
    ),
    "hi": (
        ("इकट्ठा नहीं करते", "अलग मामले"),
        ("प्रोडक्ट और कीमतें", "रीस्टोर", "रिकॉर्ड रखने के नियम"),
        ("ज़रूरी छोटा हिस्सा", "सर्वर पर नहीं", "शामिल नहीं होता"),
        ("मिलने और उसके स्वीकार होने के बाद", "पुरानी कॉपी रह सकती है"),
        ("पूरी प्रविष्टि", "सिर्फ़ सवाल", "वापस नहीं ली जातीं"),
        ("कंटेनर से बाहर", "के बाद भी रह सकता है", "मिटने की गारंटी नहीं"),
        ("मौजूदा बैकअप नहीं मिटते",),
        ("हमें आपका ईमेल पता", "मिटाने का अनुरोध"),
    ),
    "gu-IN": (
        ("એકત્ર કરતા નથી", "અલગ બાબતો"),
        ("પ્રોડક્ટ અને ભાવ", "પુનઃસ્થાપિત", "રેકોર્ડ રાખવાના નિયમો"),
        ("જરૂરી નાનકડો અંશ", "સર્વર પર નહીં", "તેમાં હોતું નથી"),
        ("મેળવે અને સ્વીકારે ત્યાર પછી", "જૂની નકલ રહી શકે છે"),
        ("સંપૂર્ણ નોંધ", "માત્ર પ્રશ્ન", "નકલો પાછી ખેંચાતી નથી"),
        ("કન્ટેનરની બહાર", "પછી પણ રહી શકે છે", "દૂર થવાની ખાતરી નથી"),
        ("હાલના બૅકઅપ દૂર થતા નથી",),
        ("અમને તમારું ઇમેઇલ સરનામું", "કાઢી નાખવા"),
    ),
    "mr-IN": (
        ("गोळा करत नाही", "स्वतंत्र बाबी"),
        ("उत्पादने आणि किमती", "पुनर्स्थापना", "जतन करण्याचे नियम"),
        ("आवश्यक छोटा भाग", "सर्व्हरवर नाही", "संपूर्ण मजकूर त्यात नसतो"),
        ("मिळाल्यानंतर आणि तो स्वीकारल्यानंतर", "आधीची प्रत राहू शकते"),
        ("संपूर्ण नोंद", "फक्त प्रश्न", "परत मागे घेतल्या जात नाहीत"),
        ("कंटेनरबाहेर", "केल्यानंतरही राहू शकते", "पुसली जाईल याची हमी नाही"),
        ("आधीचे बॅकअप पुसले जात नाहीत",),
        ("आम्हाला तुमचा ईमेल पत्ता", "हटवण्याची विनंती"),
    ),
    "pa-IN": (
        ("ਇਕੱਠੀ ਨਹੀਂ ਕਰਦੇ", "ਵੱਖਰੇ ਮਾਮਲੇ"),
        ("ਉਤਪਾਦ ਅਤੇ ਕੀਮਤਾਂ", "ਮੁੜ ਬਹਾਲ", "ਰਿਕਾਰਡ ਰੱਖਣ ਦੇ ਨਿਯਮ"),
        ("ਘੱਟੋ-ਘੱਟ ਲੋੜੀਂਦਾ ਹਿੱਸਾ", "ਸਰਵਰ ਨੂੰ ਨਹੀਂ", "ਪੂਰੀ ਲਿਖਤ ਇਸ ਵਿੱਚ ਨਹੀਂ"),
        ("ਮਿਲਣ ਅਤੇ ਮਨਜ਼ੂਰ ਹੋਣ ਤੋਂ ਬਾਅਦ", "ਪੁਰਾਣੀ ਕਾਪੀ ਰਹਿ ਸਕਦੀ ਹੈ"),
        ("ਪੂਰੀ ਐਂਟਰੀ", "ਸਿਰਫ਼ ਸਵਾਲ", "ਵਾਪਸ ਨਹੀਂ ਲਈਆਂ ਜਾਂਦੀਆਂ"),
        ("ਕੰਟੇਨਰ ਤੋਂ ਬਾਹਰ", "ਬਾਅਦ ਵੀ ਰਹਿ ਸਕਦਾ ਹੈ", "ਮਿਟਣ ਦੀ ਗਾਰੰਟੀ ਨਹੀਂ"),
        ("ਮੌਜੂਦਾ ਬੈਕਅੱਪ ਨਹੀਂ ਮਿਟਦੇ",),
        ("ਸਾਨੂੰ ਤੁਹਾਡਾ ਈਮੇਲ ਪਤਾ", "ਮਿਟਾਉਣ ਦੀ ਬੇਨਤੀ"),
    ),
    "kn-IN": (
        ("ಸಂಗ್ರಹಿಸುವುದಿಲ್ಲ", "ಬೇರೆ ಸಂದರ್ಭ"),
        ("ಉತ್ಪನ್ನ ಮತ್ತು ಬೆಲೆ", "ಮರುಸ್ಥಾಪಿಸುವುದನ್ನು", "ಉಳಿಸಿಕೊಳ್ಳುವ ನಿಯಮ"),
        ("ಕನಿಷ್ಠ ಅಗತ್ಯ ಭಾಗ", "ಸರ್ವರ್‌ಗೆ ಅಲ್ಲ", "ಇದರಲ್ಲಿ ಇರುವುದಿಲ್ಲ"),
        ("ಸ್ವೀಕರಿಸಿ ಒಪ್ಪಿಕೊಂಡ ಬಳಿಕ", "ಹಿಂದಿನ ಪ್ರತಿ ಉಳಿದಿರಬಹುದು"),
        ("ಸಂಪೂರ್ಣ ನಮೂದು", "ಪ್ರಶ್ನೆಯನ್ನು ಮಾತ್ರ", "ಹಿಂಪಡೆಯಲಾಗುವುದಿಲ್ಲ"),
        ("ಕಂಟೇನರ್‌ನ ಹೊರಗಿದೆ", "ನಂತರವೂ ಉಳಿಯಬಹುದು", "ಅಳಿಯುತ್ತದೆ ಎಂಬ ಖಾತರಿ ಇಲ್ಲ"),
        ("ಈಗಿರುವ ಬ್ಯಾಕಪ್‌ಗಳು ಅಳಿಯುವುದಿಲ್ಲ",),
        ("ನಾವು ಪಡೆಯುತ್ತೇವೆ", "ಅಳಿಸುವಂತೆ ಕೋರಬಹುದು"),
    ),
    "ml-IN": (
        ("ഞങ്ങൾ ശേഖരിക്കുന്നില്ല", "വേറിട്ട സാഹചര്യ"),
        ("ഉൽപ്പന്നങ്ങളും വിലകളും", "പുനഃസ്ഥാപിക്കൽ", "എത്രകാലം സൂക്ഷിക്കണമെന്നും"),
        ("ഏറ്റവും ചെറിയ ഭാഗം", "സർവറിലേക്കല്ല", "ഇതിൽ ഉൾപ്പെടുന്നില്ല"),
        ("സ്വീകരിച്ച് അംഗീകരിച്ചശേഷം", "പഴയ പകർപ്പ് ശേഷിക്കാം"),
        ("പൂർണ കുറിപ്പാണ്", "ചോദ്യം മാത്രം", "പകർപ്പുകൾ തിരിച്ചെടുക്കില്ല"),
        ("കണ്ടെയ്നറിനു പുറത്താണ്", "കഴിഞ്ഞാലും ശേഷിക്കാം", "ഉറപ്പുനൽകുന്നില്ല"),
        ("നിലവിലെ ബാക്കപ്പുകൾ മായില്ല",),
        ("ഞങ്ങൾക്ക് ലഭിക്കും", "ഇല്ലാതാക്കാൻ ആവശ്യപ്പെടാം"),
    ),
    "ta-IN": (
        ("நாங்கள் சேகரிப்பதில்லை", "தனித்தனி நிகழ்வுகள்"),
        ("தயாரிப்புகளையும் விலைகளையும்", "மீட்டமைத்தல்", "எவ்வளவு காலம் வைத்திருக்க"),
        ("குறைந்தபட்சத் தேவையான பகுதியை", "சேவையகத்துக்கு அல்ல", "இதில் இருக்காது"),
        ("பெற்றுக்கொண்டு ஏற்ற பிறகே", "முந்தைய பிரதி இருக்கலாம்"),
        ("முழுப் பதிவு", "கேள்வி மட்டும்", "பிரதிகளைத் திரும்பப் பெறாது"),
        ("பகுதிக்கு வெளியே", "பிறகும் இருக்கலாம்", "உறுதிசெய்யாது"),
        ("காப்புப் பிரதிகள் நீங்காது",),
        ("பெறுகிறோம்", "நீக்கக் கோரலாம்"),
    ),
    "te-IN": (
        ("మేము సేకరించము", "వేర్వేరు సందర్భాలు"),
        ("ఉత్పత్తులు, ధరలు", "పునరుద్ధరించడం", "ఎంతకాలం ఉంచాలో"),
        ("కనీస అవసరమైన భాగాన్ని", "సర్వర్‌కు కాదు", "ఇందులో ఉండదు"),
        ("స్వీకరించి అంగీకరించిన తర్వాత", "పాత కాపీ ఉండవచ్చు"),
        ("పూర్తి నమోదు", "ప్రశ్న మాత్రమే", "ఆ కాపీలు వెనక్కి రావు"),
        ("కంటైనర్ బయట", "ఇన్‌స్టాల్ చేసినా ఉండవచ్చు", "హామీ లేదు"),
        ("ఇప్పటికే ఉన్న బ్యాకప్‌లు తొలగవు",),
        ("మాకు అందుతాయి", "తొలగించాలని కోరవచ్చు"),
    ),
    "or-IN": (
        ("ସଂଗ୍ରହ କରୁନାହୁଁ", "ଅଲଗା ବିଷୟ"),
        ("ଉତ୍ପାଦ ଓ ଦାମ", "କ୍ରୟ ପୁନରୁଦ୍ଧାର", "ରଖିବାର ନିୟମ"),
        ("ଅତି ଆବଶ୍ୟକ ଛୋଟ ଅଂଶ", "ସର୍ଭର୍‌କୁ ନୁହେଁ", "ଏଥିରେ ନଥାଏ"),
        ("ପାଇ ଗ୍ରହଣ କରିବା ପରେ", "ପୁରୁଣା କପି ରହିପାରେ"),
        ("ସମ୍ପୂର୍ଣ୍ଣ ଏଣ୍ଟ୍ରି", "କେବଳ ପ୍ରଶ୍ନ", "ଫେରାଇ ଅଣାଯାଏ ନାହିଁ"),
        ("ସ୍ଥାନ ବାହାରେ", "ପରେ ମଧ୍ୟ ରହିପାରେ", "ନିଶ୍ଚିତ ନୁହେଁ"),
        ("ବ୍ୟାକ୍‌ଅପ୍ ଡିଲିଟ୍ ହୁଏ ନାହିଁ",),
        ("ଆମେ ଆପଣଙ୍କ ଇମେଲ୍ ଠିକଣା", "ଡିଲିଟ୍ ପାଇଁ ଅନୁରୋଧ"),
    ),
    "ur-PK": (
        ("جمع نہیں کرتے", "الگ صورتیں"),
        ("مصنوعات اور قیمتیں", "بحالی", "ریکارڈ رکھنے کے قواعد"),
        ("کم سے کم ضروری حصہ", "سرور کو نہیں", "شامل نہیں ہوتا"),
        ("وصول کرکے قبول کرنے کے بعد", "پرانی نقل رہ سکتی ہے"),
        ("مکمل اندراج", "صرف سوال", "نقول واپس نہیں لی جاتیں"),
        ("کنٹینر سے باہر", "بعد بھی رہ سکتا ہے", "مٹنے کی ضمانت نہیں"),
        ("موجودہ بیک اپ نہیں مٹتے",),
        ("ہمیں آپ کا ای میل پتہ", "حذف کرنے کی درخواست"),
    ),
}
for regional_english in ("en-AU", "en-CA", "en-GB"):
    PRIVACY_MARKER_ROWS[regional_english] = PRIVACY_MARKER_ROWS["en-US"]
PRIVACY_SEMANTIC_MARKERS = {
    locale: dict(zip(PRIVACY_SEMANTIC_FIELDS, row, strict=True))
    for locale, row in PRIVACY_MARKER_ROWS.items()
}
assert set(PRIVACY_SEMANTIC_MARKERS) == LOCALE_SET


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


class DisclosureParser(HTMLParser):
    VOID_TAGS = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[dict] = []
        self.stack: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        parent = self.stack[-1] if self.stack else {}
        style = re.sub(r"\s+", "", values.get("style", "")).casefold()
        hidden = (
            parent.get("hidden", False)
            or tag in {"head", "script", "style", "template"}
            or "hidden" in values
            or values.get("aria-hidden", "").casefold() == "true"
            or bool(re.search(
                r"display:none|visibility:hidden|content-visibility:hidden|"
                r"opacity:0(?:\.0+)?(?:;|$)", style,
            ))
        )
        element = {
            "tag": tag, "attrs": values, "text": [], "hidden": hidden,
            "policy": parent.get("policy", False)
            or (tag == "article" and "policy" in values.get("class", "").split()),
            "watchFields": parent.get("watchFields", False)
            or values.get("id") == "watch-payload-fields",
        }
        self.elements.append(element)
        if tag not in self.VOID_TAGS:
            self.stack.append(element)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        for element in self.stack:
            element["text"].append(data)


def lint_privacy_template(
    locales: dict[str, dict[str, str]],
    privacy_source: str | None = None,
    support_source: str | None = None,
) -> list[str]:
    errors: list[str] = []
    english = locales.get("en-US")
    if not isinstance(english, dict):
        return ["privacy.html: missing English disclosure source"]
    privacy = DisclosureParser()
    privacy.feed(
        privacy_source if privacy_source is not None
        else (ROOT / "privacy.html").read_text(encoding="utf-8")
    )
    support = DisclosureParser()
    support.feed(
        support_source if support_source is not None
        else (ROOT / "index.html").read_text(encoding="utf-8")
    )
    for name, parser, keys in (
        ("privacy.html", privacy, PRIVACY_COPY_KEYS),
        ("index.html", support, ("local", "delete", "deletion")),
    ):
        for key in keys:
            nodes = [
                node for node in parser.elements
                if node["attrs"].get("data-i18n") == key
                and not node["hidden"] and (node["policy"] or name == "index.html")
            ]
            if len(nodes) != 1:
                errors.append(f"{name}: {key} must appear once in visible disclosure content")
                continue
            node = nodes[0]
            fallback = " ".join("".join(node["text"]).split())
            expected = english.get(key)
            if not isinstance(expected, str) or fallback != " ".join(expected.split()):
                errors.append(f"{name}: {key} static disclosure differs from en-US")
            expected_tag = (
                "h2" if name == "privacy.html" else "h3"
            ) if key == "delete" or (
                key.endswith("Heading") and key != "watchFieldsHeading"
            ) else "p"
            if node["tag"] != expected_tag:
                errors.append(f"{name}: {key} must be a {expected_tag}")

    fields = tuple(
        "".join(node["text"]).strip() for node in privacy.elements
        if node["tag"] == "code" and node["watchFields"] and node["policy"]
        and not node["hidden"]
    )
    if fields != WATCH_PAYLOAD_FIELDS:
        errors.append("privacy.html: visible Watch payload fields must match the exact minimal schema")
    containers = [
        node for node in privacy.elements
        if node["attrs"].get("id") == "watch-payload-fields"
    ]
    if len(containers) != 1 or (
        containers[0]["attrs"].get("aria-labelledby") != "watch-payload-label"
        or "payload-fields" not in containers[0]["attrs"].get("class", "").split()
    ):
        errors.append("privacy.html: Watch fields must retain their localized label and bidi isolation")
    labels = [
        node for node in privacy.elements
        if node["attrs"].get("id") == "watch-payload-label"
        and node["attrs"].get("data-i18n") == "watchFieldsHeading"
        and not node["hidden"]
    ]
    if len(labels) != 1:
        errors.append("privacy.html: missing visible localized Watch field label")
    dates = [node for node in privacy.elements if node["tag"] == "time" and not node["hidden"]]
    if len(dates) != 1 or (
        dates[0]["attrs"].get("datetime") != PRIVACY_UPDATED
        or "".join(dates[0]["text"]).strip() != PRIVACY_UPDATED
    ):
        errors.append(f"privacy.html: policy date must be {PRIVACY_UPDATED}")
    descriptions = [
        node for node in privacy.elements
        if node["tag"] == "meta" and node["attrs"].get("name") == "description"
    ]
    if len(descriptions) != 1 or (
        descriptions[0]["attrs"].get("data-i18n-content") != "noCollection"
        or descriptions[0]["attrs"].get("content") != english.get("noCollection")
    ):
        errors.append("privacy.html: metadata must use the qualified collection disclosure")
    return errors


def lint_runtime_schema(loader: str) -> list[str]:
    required = re.search(r"\bconst required\s*=\s*\[([^\]]+)\]", loader)
    keys = re.findall(r'"([^"]+)"', required.group(1)) if required else []
    errors = []
    if set(keys) != REQUIRED_LOCALE_KEYS or len(keys) != len(REQUIRED_LOCALE_KEYS):
        errors.append("localize.js: runtime required keys must match the exact dictionary schema")
    if "supported.length !== 50" not in loader:
        errors.append("localize.js: missing exact-50 runtime guard")
    return errors


def expected_support_url(locale: str) -> str:
    return f"{ASC_SITE_ROOT}?lang={locale}"


def expected_privacy_url(locale: str) -> str:
    return f"{ASC_SITE_ROOT}privacy.html?lang={locale}"


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate dictionary key {key!r}")
        result[key] = value
    return result


def normalized_copy(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKC", value).casefold()
        if character.isalnum()
    )


def english_copy_index(locales: dict[str, dict[str, str]]) -> dict[str, set[str]]:
    return {
        key: {
            normalized_copy(record[key]) for locale, record in locales.items()
            if locale.startswith("en-") and isinstance(record, dict)
            and isinstance(record.get(key), str) and record[key].strip()
        }
        for key in CRITICAL_TRANSLATED_KEYS
    }


def parse_locales(source: str | None = None) -> tuple[dict[str, dict[str, str]], list[str]]:
    if source is None:
        source = (ROOT / "locales.js").read_text(encoding="utf-8")
    prefix = "window.ZODIRA_LOCALES = "
    if not source.startswith(prefix) or not source.endswith(";\n"):
        return {}, ["locales.js: expected one explicit local dictionary assignment"]
    try:
        locales = json.loads(source[len(prefix):-2], object_pairs_hook=_unique_object)
    except ValueError as error:
        return {}, [f"locales.js: invalid dictionary JSON: {error}"]
    if not isinstance(locales, dict):
        return {}, ["locales.js: locale dictionary must be an object"]
    return locales, lint_locales(locales)


def lint_locales(locales: dict[str, dict[str, str]]) -> list[str]:
    errors: list[str] = []
    if set(locales) != LOCALE_SET:
        errors.append(
            "locales.js: exact-50 mismatch "
            f"missing={sorted(LOCALE_SET - set(locales))} "
            f"extra={sorted(set(locales) - LOCALE_SET)}"
        )
        return errors

    english_copies = english_copy_index(locales)
    for locale in OFFICIAL_LOCALES:
        errors.extend(lint_locale_record(locale, locales[locale], english_copies))
    return errors


def lint_locale_record(
    locale: str, record: dict[str, str], english_copies: dict[str, set[str]],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict) or set(record) != REQUIRED_LOCALE_KEYS:
        return [f"locales.js: {locale} schema mismatch"]
    for key, value in record.items():
        if not isinstance(value, str) or not value.strip():
            errors.append(f"locales.js: {locale}/{key} is empty")
        elif "\ufffd" in value or PLACEHOLDER_RE.search(value):
            errors.append(f"locales.js: {locale}/{key} has placeholder text")
        elif value.strip() in REQUIRED_LOCALE_KEYS:
            errors.append(f"locales.js: {locale}/{key} exposes a raw key")
    for key in CRITICAL_TRANSLATED_KEYS:
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        if not locale.startswith("en-"):
            normalized = normalized_copy(value)
            if any(
                english == normalized or (key in PRIVACY_COPY_KEYS and english in normalized)
                for english in english_copies[key]
            ):
                errors.append(f"locales.js: {locale}/{key} falls back to English")
        marker = SCRIPT_MARKERS.get(locale)
        if marker and not re.search(marker, value):
            errors.append(f"locales.js: {locale}/{key} lacks its native script")
    for key, tokens in PRIVACY_DATAFLOW_TOKENS.items():
        value = record.get(key)
        if isinstance(value, str):
            for token in tokens:
                forms = DATAFLOW_TOKEN_FORMS.get((locale, token), (token,))
                if not any(form in value for form in forms):
                    errors.append(f"locales.js: {locale}/{key} missing dataflow token {token!r}")
    description = record.get("description")
    if isinstance(description, str):
        lines = description.splitlines()
        if len(lines) < 4 or lines[3] != record.get("local"):
            errors.append(
                f"locales.js: {locale}/description must reuse the qualified local disclosure"
            )
    for key, markers in PRIVACY_SEMANTIC_MARKERS[locale].items():
        value = record.get(key)
        if isinstance(value, str):
            for marker in markers:
                if marker not in value:
                    errors.append(
                        f"locales.js: {locale}/{key} missing semantic marker {marker!r}"
                    )
    return errors


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
    locale_keys = set(REQUIRED_LOCALE_KEYS)
    for name, canonical in PAGES.items():
        errors.extend(lint_page(name, canonical, locale_keys))
    errors.extend(lint_identity_and_contact())
    errors.extend(lint_store_consistency(locales))
    errors.extend(lint_sitemap_and_robots())
    errors.extend(lint_privacy_template(locales))

    loader = (ROOT / "localize.js").read_text(encoding="utf-8")
    errors.extend(lint_runtime_schema(loader))
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
        "site lint passed: canonical identity, exact-50 localized dictionary, "
        "App Store product consistency, visible privacy/dataflow disclosures, "
        "sitemap, contact and legal bundle exception"
    )


if __name__ == "__main__":
    main()
