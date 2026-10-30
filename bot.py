#!/usr/bin/env python3
"""vikiproject adding - Immortalance'in Vikipedi botu (GitHub Actions icin).

Gorevler (GOREV ortam degiskeni):
  vikiproje     Madde, sablon ve kategori tartisma sayfalarina, Ingilizce Vikipedi'deki
                karsiliklarinin vikiproje sablonlarina gore {{Vikiproje}} ekler.
  diller-arasi  Maddelerdeki [[:dil:Baslik|Metin]] baglantilarini Turkce karsiligi varsa
                yerel baglantiya, yoksa {{diller arasi baglanti}} sablonuna cevirir.

Ortam degiskenleri:
  BOT_USER, BOT_PASS   Ozel:BotSifreleri ile alinan kullanici adi ve sifre (zorunlu, kuru calismada degil)
  GOREV                vikiproje | diller-arasi   (varsayilan: vikiproje)
  KAYNAK               yeni | kategori | arama | liste | sayfa   (varsayilan: yeni)
  DEGER                kaynaga gore: saat sayisi / kategori adi / arama ifadesi / dosya yolu / sayfa basliklari (| ile)
  KURU_CALISMA         1 ise kaydetmez, yalnizca farklari gosterir
  MAKS_DUZENLEME       bir calismadaki en fazla kayit (varsayilan 100)
  DUZENLEME_ARALIGI    iki kayit arasindaki saniye (varsayilan 10)
  SAYFA_OLUSTUR        1 ise olmayan tartisma sayfasini olusturur (varsayilan 1)
"""
import difflib
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

import diller_arasi
import vikiproje

TR = "https://tr.wikipedia.org/w/api.php"
EN = "https://en.wikipedia.org/w/api.php"
UA = "VikiprojectAdding/1.0 (https://tr.wikipedia.org/wiki/User:%C4%B0mmortalance; GitHub Actions)"

# tr konu ad alani -> (tr tartisma on eki, en tartisma on eki)
NAMESPACES = {
    0: ("Tartışma:", "Talk:"),
    10: ("Şablon tartışma:", "Template talk:"),
    14: ("Kategori tartışma:", "Category talk:"),
}
TALK_NS = {1: 0, 11: 10, 15: 14}


def env(name, default=""):
    v = os.environ.get(name, "")
    return v.strip() if v.strip() else default


class Api:
    """maxlag, Retry-After ve gecici hatalara saygili, istekleri araliklayan istemci."""

    def __init__(self, url, interval=1.0):
        self.url = url
        self.interval = interval
        self.next_at = 0.0
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA

    def _wait(self):
        left = self.next_at - time.monotonic()
        if left > 0:
            time.sleep(left)

    def call(self, params, post=False):
        params = dict(params, format="json", formatversion="2", maxlag="5")
        for attempt in range(5):
            self._wait()
            self.next_at = time.monotonic() + self.interval
            retry_after = None
            try:
                if post:
                    r = self.s.post(self.url, data=params, timeout=60)
                else:
                    r = self.s.get(self.url, params=params, timeout=60)
                retry_after = r.headers.get("Retry-After")
                if r.status_code in (429, 502, 503, 504):
                    raise _Temporary("HTTP %d" % r.status_code, r.status_code == 429)
                r.raise_for_status()
                data = r.json()
                err = data.get("error")
                if err:
                    code = err.get("code", "")
                    if code in ("maxlag", "ratelimited", "readonly", "internal_api_error_DBQueryTimeoutError"):
                        raise _Temporary("API " + code, code == "ratelimited")
                    raise RuntimeError("%s: %s" % (code, err.get("info", "")))
                return data
            except (_Temporary, requests.ConnectionError, requests.Timeout) as e:
                limited = isinstance(e, _Temporary) and e.limited
                delay = min(300, (60 if limited else 5) * 2 ** attempt)
                try:
                    delay = max(delay, int(retry_after))
                except (TypeError, ValueError):
                    pass
                if limited:
                    self.interval = max(self.interval, 6.0)
                if attempt == 4:
                    raise RuntimeError("5 deneme basarisiz: %s" % e)
                print("  ! %s; %d sn bekleniyor" % (e, delay + 1))
                self.next_at = time.monotonic() + delay + 1
        raise RuntimeError("API istegi tamamlanamadi")

    def query(self, **params):
        params["action"] = "query"
        return self.call(params)

    def login(self, user, password):
        tok = self.query(meta="tokens", type="login")["query"]["tokens"]["logintoken"]
        r = self.call({"action": "login", "lgname": user, "lgpassword": password, "lgtoken": tok}, post=True)
        if r.get("login", {}).get("result") != "Success":
            raise SystemExit("Giris basarisiz: %s" % r.get("login"))
        info = self.query(meta="userinfo", uiprop="rights")["query"]["userinfo"]
        self.is_bot = "bot" in info.get("rights", [])
        self.csrf = self.query(meta="tokens")["query"]["tokens"]["csrftoken"]
        print("Giris yapildi: %s (bot hakki: %s)" % (info["name"], "var" if self.is_bot else "yok"))


class _Temporary(Exception):
    def __init__(self, msg, limited):
        super().__init__(msg)
        self.limited = limited


# ------------------------------------------------------------ sayfa kaynaklari
# Kaynaklar ham sayfa nesneleri ({ns, title}) uretir; goreve gore basliga cevrilir.

def talk_titles_from_pages(pages):
    """API sayfa nesnelerinden (ns, title) islenecek tartisma basliklarini uretir."""
    for p in pages:
        ns, title = p["ns"], p["title"]
        if ns in TALK_NS:
            yield title
        elif ns in NAMESPACES:
            rest = title.split(":", 1)[1] if ns else title
            yield NAMESPACES[ns][0] + rest


def article_titles_from_pages(pages):
    """Madde basliklarini uretir; madde tartisma sayfasi verilirse maddeye cevirir."""
    for p in pages:
        if p["ns"] == 0:
            yield p["title"]
        elif p["ns"] == 1:
            yield p["title"].split(":", 1)[1]


def _paged(tr, key, params):
    while True:
        d = tr.query(**params)
        yield from d["query"][key]
        if "continue" not in d:
            break
        params.update(d["continue"])


def source_new(tr, hours, namespaces):
    """Son N saatte olusturulan sayfalar."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _paged(tr, "recentchanges", dict(list="recentchanges", rctype="new", rcnamespace=namespaces,
                                             rcshow="!redirect", rcprop="title", rclimit="500",
                                             rcdir="newer", rcstart=since))


def source_category(tr, category, namespaces):
    if not category.lower().startswith("kategori:"):
        category = "Kategori:" + category
    return _paged(tr, "categorymembers", dict(list="categorymembers", cmtitle=category,
                                               cmnamespace=namespaces, cmprop="title", cmlimit="500"))


def source_search(tr, query):
    """CirrusSearch aramasi (insource: ifadeleri dahil), yalnizca maddeler."""
    return _paged(tr, "search", dict(list="search", srsearch=query, srnamespace="0",
                                      srprop="", srlimit="500", srwhat="text"))


def source_titles(tr, titles):
    """Baslik listesini API ile normallestirir."""
    titles = [t.strip() for t in titles if t.strip() and not t.strip().startswith("#")]
    for i in range(0, len(titles), 50):
        d = tr.query(titles="|".join(titles[i:i + 50]))
        yield from d["query"]["pages"]


# ------------------------------------------------------------ ortak

def load_page(tr, title):
    d = tr.query(titles=title, prop="revisions|info", rvprop="content|timestamp",
                 rvslots="main", curtimestamp="1")
    page = d["query"]["pages"][0]
    missing = bool(page.get("missing"))
    text = "" if missing or not page.get("revisions") else page["revisions"][0]["slots"]["main"]["content"]
    base_ts = None if missing or not page.get("revisions") else page["revisions"][0]["timestamp"]
    return page, text, base_ts, d.get("curtimestamp")


def save(tr, page, old, new, summary, base_ts, start_ts, opts):
    if opts["dry"]:
        diff = "\n".join(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=1))
        return "kaydedildi", "(kuru) " + summary + "\n" + diff
    missing = bool(page.get("missing"))
    params = {"action": "edit", "title": page["title"], "text": new, "summary": summary,
              "token": tr.csrf, "starttimestamp": start_ts, "assert": "user",
              "nocreate" if not missing else "createonly": "1"}
    if base_ts:
        params["basetimestamp"] = base_ts
    if tr.is_bot:
        params["bot"] = "1"
    r = tr.call(params, post=True)
    if r.get("edit", {}).get("result") != "Success":
        raise RuntimeError("Kayit basarisiz: %s" % r.get("edit"))
    return "kaydedildi", summary


# ------------------------------------------------------------ gorev: vikiproje

def handle_vikiproje(tr, ctx, talk_title, opts):
    """(durum, mesaj) dondurur. durum: kaydedildi | degisiklik-yok | atlandi | hata."""
    en = ctx["en"]
    page, text, base_ts, start_ts = load_page(tr, talk_title)
    ns = page["ns"]
    if ns not in TALK_NS or page.get("invalid"):
        return "atlandi", "desteklenmeyen ad alani"
    if page.get("missing") and not opts["create"]:
        return "atlandi", "tartisma sayfasi yok"
    if page.get("redirect") or vikiproje.is_redirect(text):
        return "atlandi", "yonlendirme"

    subject_ns = TALK_NS[ns]
    rest = page["title"].split(":", 1)[1]
    subject = rest if subject_ns == 0 else NAMESPACES[subject_ns][0].replace(" tartışma", "") + rest
    s = tr.query(titles=subject, prop="langlinks", lllang="en", lllimit="1")["query"]["pages"][0]
    if s.get("missing") or s.get("invalid") or s.get("ns") != subject_ns:
        return "atlandi", "konu sayfasi yok"
    links = s.get("langlinks") or []
    if not links:
        return "atlandi", "ingilizce karsiligi yok"
    en_title = links[0]["title"]
    en_rest = en_title.split(":", 1)[1] if subject_ns else en_title
    en_talk = NAMESPACES[subject_ns][1] + en_rest

    e = en.query(titles=en_talk, prop="revisions", rvprop="content", rvslots="main")["query"]["pages"][0]
    if e.get("missing") or not e.get("revisions"):
        return "atlandi", "ingilizce tartisma sayfasi yok"
    source = e["revisions"][0]["slots"]["main"]["content"]

    new, summary = vikiproje.process(text, source, en_talk)
    if not summary:
        return "degisiklik-yok", ""
    return save(tr, page, text, new, summary, base_ts, start_ts, opts)


# ------------------------------------------------------------ gorev: diller arasi

def language_map(tr):
    """Gecerli Vikipedi dil kodlari -> API adresi (tr.wikipedia interwiki tablosundan)."""
    d = tr.query(meta="siteinfo", siprop="interwikimap", sifilteriw="local")
    out = {}
    for iw in d["query"]["interwikimap"]:
        if iw.get("language") and iw["url"].endswith("/wiki/$1"):
            out[iw["prefix"].lower()] = iw["url"][:-len("/wiki/$1")] + "/w/api.php"
    if "en" not in out or "tr" not in out:
        raise SystemExit("Dil tablosu alinamadi.")
    return out


def lookup_turkish(api, titles, own_wiki):
    """{baslik: {"skip":bool, "tr":str|None}} dondurur. Hata olursa istisna firlatir (sayfa atlanir).

    own_wiki=True: tr.wikipedia'nin kendisi; yonlendirme izlenmez, yalnizca ad alani dogrulanir.
    """
    result = {}
    titles = sorted(set(titles))
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        params = dict(titles="|".join(batch))
        if not own_wiki:
            params.update(prop="langlinks", lllang="tr", lllimit="max", redirects="1")
        q = api.query(**params)["query"]
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
        interwiki = {iw["title"] for iw in q.get("interwiki", [])}
        pages = {p["title"]: p for p in q.get("pages", [])}
        for t in batch:
            if t in interwiki or norm.get(t) in interwiki:
                result[t] = {"skip": True}
                continue
            final = norm.get(t, t)
            final = redir.get(final, final)
            p = pages.get(final)
            if p is None or p.get("invalid") or p.get("ns") != 0:
                result[t] = {"skip": True}  # kardes proje, baska ad alani ya da gecersiz baslik
                continue
            if own_wiki:
                result[t] = {"tr": t}  # [[:tr:X]] -> [[X]] (ad alani 0 dogrulandi)
                continue
            ll = [l["title"] for l in p.get("langlinks", []) if l.get("lang") == "tr"]
            result[t] = {"tr": ll[0] if ll else None}
    return result


def handle_interlang(tr, ctx, title, opts):
    page, text, base_ts, start_ts = load_page(tr, title)
    if page.get("missing") or page.get("invalid") or page["ns"] != 0:
        return "atlandi", "madde degil ya da yok"
    if page.get("redirect") or vikiproje.is_redirect(text):
        return "atlandi", "yonlendirme"
    links = diller_arasi.find_links(text, ctx["langs"])
    if not links:
        return "degisiklik-yok", ""
    infos = {}
    by_lang = {}
    for l in links:
        by_lang.setdefault(l.lang, set()).add(l.title)
    for lang, titles in by_lang.items():
        if lang == "tr":
            api, own = tr, True
        else:
            url = ctx["langs"][lang]
            api = ctx["apis"].get(url)
            if api is None:
                api = ctx["apis"][url] = Api(url)
            own = False
        # Bir dilde hata olursa istisna yukari cikar ve sayfa hic degistirilmez.
        for t, info in lookup_turkish(api, titles, own).items():
            infos[(lang, t)] = info
    new, local, tmpl = diller_arasi.apply(text, links, infos)
    if new == text:
        return "degisiklik-yok", ""
    return save(tr, page, text, new, diller_arasi.summary(local, tmpl), base_ts, start_ts, opts)


# ------------------------------------------------------------ ana akis

GOREVLER = {
    # gorev: (isleyici, baslik cevirici, yeni/kategori ad alanlari, varsayilan arama)
    "vikiproje": (handle_vikiproje, talk_titles_from_pages, "0|1|10|11|14|15", None),
    "diller-arasi": (handle_interlang, article_titles_from_pages, "0|1",
                     r"insource:/\[\[ *:[a-z-]+ *:[^\]]/"),
}


def main():
    gorev = env("GOREV", "vikiproje").lower()
    if gorev not in GOREVLER:
        raise SystemExit("Bilinmeyen GOREV: " + gorev)
    handler, to_titles, namespaces, default_search = GOREVLER[gorev]
    kaynak = env("KAYNAK", "yeni").lower()
    deger = env("DEGER")
    opts = {
        "dry": env("KURU_CALISMA", "0") in ("1", "true", "evet"),
        "create": env("SAYFA_OLUSTUR", "1") in ("1", "true", "evet") and gorev == "vikiproje",
    }
    max_edits = int(env("MAKS_DUZENLEME", "100"))
    delay = float(env("DUZENLEME_ARALIGI", "10"))

    tr = Api(TR)
    tr.is_bot = False
    ctx = {"en": Api(EN), "apis": {}}
    if gorev == "vikiproje":
        vikiproje.load_rules()
    if not opts["dry"]:
        user, pw = env("BOT_USER"), env("BOT_PASS")
        if not user or not pw:
            raise SystemExit("BOT_USER ve BOT_PASS gizli degiskenleri tanimli degil.")
        tr.login(user, pw)
        if not tr.is_bot:
            delay = max(delay, 15)
    if gorev == "diller-arasi":
        ctx["langs"] = language_map(tr)
        ctx["apis"][ctx["langs"]["en"]] = ctx["en"]

    if kaynak == "yeni":
        pages = source_new(tr, float(deger or 25), "0" if gorev == "diller-arasi" else "0|10|14")
    elif kaynak == "kategori":
        if not deger:
            raise SystemExit("kategori kaynagi icin DEGER gerekli")
        pages = source_category(tr, deger, namespaces)
    elif kaynak == "arama":
        query = deger or default_search
        if not query:
            raise SystemExit("arama kaynagi icin DEGER (arama ifadesi) gerekli")
        pages = source_search(tr, query)
    elif kaynak == "liste":
        with open(deger or "sayfalar.txt", encoding="utf-8") as f:
            pages = source_titles(tr, f.read().splitlines())
    elif kaynak == "sayfa":
        pages = source_titles(tr, deger.split("|"))
    else:
        raise SystemExit("Bilinmeyen KAYNAK: " + kaynak)
    titles = to_titles(pages)

    print("Gorev: %s | Kaynak: %s %s | kuru calisma: %s | en fazla %d kayit"
          % (gorev, kaynak, deger, opts["dry"], max_edits))
    counts = {"kaydedildi": 0, "degisiklik-yok": 0, "atlandi": 0, "hata": 0}
    errors, seen = [], set()
    for title in titles:
        if title in seen:
            continue
        seen.add(title)
        if counts["kaydedildi"] >= max_edits:
            print("Kayit siniri doldu (%d)." % max_edits)
            break
        try:
            status, msg = handler(tr, ctx, title, opts)
        except vikiproje.VPError as ex:
            status, msg = "hata", str(ex)
        except Exception as ex:  # tek sayfa hatasi botu durdurmasin
            status, msg = "hata", "%s: %s" % (type(ex).__name__, ex)
        counts[status] += 1
        if status in ("kaydedildi", "hata"):
            print("[%s] %s - %s" % (status, title, msg))
        if status == "hata":
            errors.append((title, msg))
        if status == "kaydedildi" and not opts["dry"]:
            time.sleep(delay)

    line = ", ".join("%s: %d" % kv for kv in counts.items())
    print("\nOzet -> " + line)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("## %s\n\n%s\n\n" % (gorev, line))
            if errors:
                f.write("### Hatalar (sayfalar degistirilmedi)\n\n")
                for t, m in errors:
                    f.write("- [[%s]]: %s\n" % (t, m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
