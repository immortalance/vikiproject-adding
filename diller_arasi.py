"""Diller arasi baglanti donusturucu (AWB modulu V1.4'un duzeltilmis Python karsiligi).

Yazar: Immortalance
Islev: [[:en:Sayfa|Metin]] bicimindeki baglantilari, Turkce karsiligi varsa yerel vikilinke,
yoksa {{diller arasi baglanti}} sablonuna donusturur.

Ag istegi yoktur: Turkce karsiliklar disaridan (bot.py) bir sozluk olarak verilir.
"""
import re

from vikiproje import mask

# [[:dil:Baslik]] veya [[:dil:Baslik|Metin]] ; dil kodu dogrulamasi sonradan yapilir.
LINK = re.compile(r"\[\[[ \t]*:[ \t]*([A-Za-z][A-Za-z-]{0,19})[ \t]*:([^\[\]|\n]+?)(?:\|([^\[\]\n]*))?\]\]")
SABLON = "diller arası bağlantı"


class Link:
    __slots__ = ("start", "end", "lang", "title", "display", "piped")

    def __init__(self, start, end, lang, title, display, piped):
        self.start, self.end = start, end
        self.lang, self.title, self.display, self.piped = lang, title, display, piped

    @property
    def key(self):
        return (self.lang, self.title)


def find_links(text, languages):
    """Yorum/nowiki/pre disindaki gecerli dil baglantilarini bulur.

    languages: gecerli Vikipedi dil kodlari kumesi (kucuk harf).
    Kardes proje onekleri (s:, wikt: ...) dil kodu olmadigi icin burada elenir;
    [[:en:s:...]] gibi baslik icindeki onekler bot.py'de API ile elenir.
    """
    masked = mask(text)
    out = []
    for m in LINK.finditer(masked):
        lang = m.group(1).lower()
        if lang not in languages:
            continue
        s, e = m.span()
        raw = text[s:e]
        # Maskeli metinle ayni konumlardaki ozgun parcalari al.
        mm = LINK.fullmatch(raw)
        if not mm:
            continue
        title = mm.group(2).strip().replace("_", " ")
        title = re.sub(r"\s+", " ", title)
        if not title or "#" in title:
            continue  # bolum baglantilari belirsiz; dokunma
        piped = mm.group(3) is not None and mm.group(3).strip() != ""
        display = mm.group(3).strip() if piped else title
        out.append(Link(s, e, lang, title, display, piped))
    return out


def _param(value, index):
    return ("%d=%s" % (index, value)) if "=" in value else value


def template(tr_title, lang, foreign=None):
    args = [_param(tr_title, 1), _param(lang, 2)]
    if foreign is not None:
        args.append(_param(foreign, 3))
    return "{{" + SABLON + "|" + "|".join(args) + "}}"


def local_link(tr_title, display):
    if display == tr_title:
        return "[[" + tr_title + "]]"
    return "[[" + tr_title + "|" + display + "]]"


def replacement(link, info):
    """Bir baglantinin yeni bicimini dondurur; dokunulmayacaksa None.

    info: {"skip": bool, "tr": Turkce baslik veya None, "local": bool}
    """
    if info is None or info.get("skip"):
        return None
    tr = info.get("tr")
    if tr:
        # Pipe yoksa okura Turkce madde adini goster.
        display = link.display if link.piped else tr
        return local_link(tr, display)
    if link.lang == "tr":
        return None  # yerel sayfa ad alani dogrulanamadi; dokunma
    # Sablon parametrelerini bozabilecek metinlere dokunma.
    if any(ch in link.display for ch in "|{}"):
        return None
    if not link.piped or link.display == link.title or link.display.lower() == link.lang:
        return template(link.title, link.lang)
    # Gorunen metin Turkce baslik olarak kullanilir (AWB modulundeki davranis).
    return template(link.display, link.lang, link.title)


def apply(text, links, infos):
    """Baglantilari sondan basa degistirir. (yeni_metin, yerel_sayi, sablon_sayi) dondurur."""
    result = text
    local = tmpl = 0
    for link in sorted(links, key=lambda l: l.start, reverse=True):
        new = replacement(link, infos.get(link.key))
        if new is None or new == result[link.start:link.end]:
            continue
        result = result[:link.start] + new + result[link.end:]
        if new.startswith("[["):
            local += 1
        else:
            tmpl += 1
    return result, local, tmpl


def summary(local, tmpl):
    parts = []
    if local:
        parts.append("%d yerel bağlantı" % local)
    if tmpl:
        parts.append("%d diller arası bağlantı şablonu" % tmpl)
    return "Diller arası bağlantılar dönüştürüldü (" + ", ".join(parts) + ")"
