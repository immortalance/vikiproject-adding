"""Vikiproje ekleme mantigi (AWB C# modulunun birebir Python karsiligi).

Yazar: Immortalance
Islev: Ingilizce Vikipedi'deki onem derecelerine gore tartisma sablonuna vikiprojeleri ekler.

Bu dosyada ag istegi yoktur; yalnizca vikimetin isleme kurallari bulunur.
"""
import os
import re

_WS = re.compile(r"\s+")
_MASK = re.compile(
    r"<!--[\s\S]*?(?:-->|$)|<(nowiki|pre|source|syntaxhighlight)\b[^>]*>[\s\S]*?</\1\s*>|<nowiki\s*/\s*>",
    re.IGNORECASE,
)


class VPError(Exception):
    """Sayfanin degistirilmeden atlanmasini gerektiren hata."""


def _lower(s):
    # .NET ToLowerInvariant ile ayni sonuc: 'İ' -> 'i' (Python'da 'i̇' olurdu).
    return s.replace("İ", "i").lower()


def norm(s):
    return _lower(_WS.sub(" ", s.replace("_", " ").strip()))


def mask(s):
    """Yorum ve ham metin bloklarini ayni uzunlukta bosluklarla maskeler."""
    return _MASK.sub(lambda m: " " * len(m.group(0)), s)


class Span:
    __slots__ = ("start", "length")

    def __init__(self, start, length):
        self.start, self.length = start, length

    @property
    def end(self):
        return self.start + self.length


class Part:
    __slots__ = ("start", "length", "key", "value")


def templates(text):
    """Tum (ic ice dahil) {{...}} sablonlarinin konumlarini baslangica gore sirali dondurur."""
    s = mask(text)
    result, starts, widths = [], [], []
    i, n = 0, len(s)
    while i < n - 1:
        if s[i] == "{" and s[i + 1] == "{":
            w = 3 if i + 2 < n and s[i + 2] == "{" else 2
            starts.append(i)
            widths.append(w)
            i += w - 1
        elif s[i] == "}" and s[i + 1] == "}" and widths:
            w = widths[-1]
            if w == 3 and (i + 2 >= n or s[i + 2] != "}"):
                i += 1
                continue
            start = starts.pop()
            widths.pop()
            if w == 2:
                result.append(Span(start, i + 2 - start))
            i += w - 1
        i += 1
    result.sort(key=lambda sp: sp.start)
    return result


def _make_part(text, start, length):
    p = Part()
    p.start, p.length = start, length
    raw = text[start:start + length]
    eq = mask(raw).find("=")
    p.key = "" if eq < 0 else norm(mask(raw[:eq]))
    p.value = raw.strip() if eq < 0 else raw[eq + 1:].strip()
    return p


def parts(template):
    """Yalnizca ust duzey | ayiricilarini boler; ic sablonlari ve vikilinkleri korur."""
    s = mask(template)
    out = []
    start, depth, links = 2, 0, 0
    i = 2
    while i < len(s) - 2:
        two = s[i:i + 2]
        if two == "{{":
            depth += 1
            i += 1
        elif two == "}}":
            depth -= 1
            i += 1
        elif two == "[[":
            links += 1
            i += 1
        elif two == "]]":
            links -= 1
            i += 1
        elif s[i] == "|" and depth == 0 and links == 0:
            out.append(_make_part(template, start, i - start))
            start = i + 1
        i += 1
    out.append(_make_part(template, start, len(s) - 2 - start))
    return out


def name(template):
    n = norm(mask(parts(template)[0].value))
    if n.startswith("şablon:"):
        n = n[7:].strip()
    if n.startswith("template:"):
        n = n[9:].strip()
    return n


def param(template, key):
    found = None
    ps = parts(template)
    k = norm(key)
    for p in ps[1:]:
        if p.key == k:
            if found is not None:
                raise VPError("Yinelenen parametre: " + key)
            found = p
    return found


def value(template, key):
    p = param(template, key)
    return "" if p is None else mask(p.value).strip()


def importance(v):
    n = norm(v)
    table = {"top": "En", "high": "Çok", "mid": "Orta", "low": "Az"}
    if n in table:
        return table[n]
    if n in ("", "unknown", "unassessed", "na", "n/a"):
        return ""
    raise VPError("Taninmayan importance degeri: " + v)


# ---------------------------------------------------------------- eslestirme

class Rule:
    __slots__ = ("project", "flags", "importance_keys")

    def __init__(self, project, flags, importance_keys):
        self.project, self.flags, self.importance_keys = project, flags, importance_keys


class Rating:
    __slots__ = ("project", "importance")

    def __init__(self, project, imp):
        self.project, self.importance = project, imp


def template_key(n):
    s = _WS.sub(" ", n.replace("_", " ").strip())
    if s[:9].lower() == "template:":
        s = s[9:].strip()
    # MediaWiki'de yalniz ilk harf esdegerdir; WP Bio ve Wp bio farkli sablonlardir.
    return s if not s else s[0].upper() + s[1:]


_RULES = None


def load_rules(path=None):
    global _RULES
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eslestirme.tsv")
    rules = {}
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.rstrip("\r\n")
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            cols = raw.split("\t")
            if len(cols) != 4:
                raise ValueError("Bozuk eslestirme satiri: " + raw)
            rules.setdefault(template_key(cols[0]), []).append(Rule(cols[1], cols[2], cols[3]))
    _RULES = rules
    return rules


def _rules():
    return _RULES if _RULES is not None else load_rules()


def first_parameter(template, names):
    # Ic ice varsayilanlarda ilk TANIMLI parametre kullanilir; bos deger de tanimlidir.
    for n in names.split(","):
        p = param(template, n)
        if p is not None:
            return mask(p.value).strip()
    return ""


def enabled(v):
    return norm(v) in ("yes", "y", "1", "true", "t", "on")


def extract(template):
    result = []
    n = mask(parts(template)[0].value).strip()
    rules = _rules().get(template_key(n))
    if not rules:
        return result
    for rule in rules:
        if rule.flags and not enabled(first_parameter(template, rule.flags)):
            continue
        imp = ""
        if rule.importance_keys != "-":
            try:
                imp = importance(first_parameter(template, rule.importance_keys))
            except VPError:
                imp = ""
        result.append(Rating(rule.project, imp))
    return result


def ratings_from_english(source):
    """Ingilizce tartisma sayfasinin ilk basliktan onceki bolumunden projeleri cikarir."""
    ratings, unique = [], {}
    heading = re.search(r"(?m)^==", mask(source))
    for span in templates(source):
        if heading and span.start >= heading.start():
            continue
        t = source[span.start:span.end]
        for r in extract(t):
            key = norm(r.project)
            prev = unique.get(key)
            if prev is not None:
                if prev.importance and r.importance and prev.importance != r.importance:
                    raise VPError("Ayni projeye celisen onemler eslendi: " + r.project)
                if not prev.importance:
                    prev.importance = r.importance
            else:
                unique[key] = r
                ratings.append(r)
    return ratings


# ---------------------------------------------------------------- duzenleme

NL = "\n"  # MediaWiki API metni \n ile verir (AWB \r\n kullanir).


def edit(text, project, imp):
    existing = wrapper = None
    for span in templates(text):
        t = text[span.start:span.end]
        n = name(t)
        if (n == "vikiproje" and norm(value(t, "Proje")) == norm(project)) or n == "vikiproje " + norm(project):
            if existing is not None:
                raise VPError("Yinelenen yerel proje: " + project)
            existing = span
        if n == "tartışma":
            if wrapper is not None:
                raise VPError("Birden fazla tartisma sablonu var.")
            wrapper = span
    if existing is not None:
        t = text[existing.start:existing.end]
        if value(t, "Önem") != "" or imp == "":
            return text
        p = param(t, "Önem")
        if p is None:
            updated = t[:-2] + " | Önem = " + imp + " " + t[-2:]
        else:
            raw = t[p.start:p.start + p.length]
            pos = p.start + mask(raw).find("=") + 1
            updated = t[:pos] + " " + imp + " " + t[pos:]
        return text[:existing.start] + updated + text[existing.end:]
    banner = "{{Vikiproje | Proje = " + project + " | Sınıf = | Önem = " + imp + " }}"
    if wrapper is None:
        return "{{tartışma" + NL + "| proje =" + NL + banner + NL + "}}" + NL + text
    outer = text[wrapper.start:wrapper.end]
    pf = param(outer, "proje")
    if pf is None:
        outer = outer[:-2] + NL + "| proje =" + NL + banner + NL + outer[-2:]
    else:
        field = outer[pf.start:pf.start + pf.length].rstrip(" \t\r\n")
        outer = outer[:pf.start] + field + NL + banner + NL + outer[pf.start + pf.length:]
    return text[:wrapper.start] + outer + text[wrapper.end:]


def compact_projects(text):
    """Yalniz proje alaninda, komsu proje sablonlari arasindaki bos satirlari kaldirir."""
    for wrapper in templates(text):
        outer = text[wrapper.start:wrapper.end]
        if name(outer) != "tartışma":
            continue
        field = param(outer, "proje")
        if field is None:
            continue
        raw = outer[field.start:field.start + field.length]
        eq = mask(raw).find("=")
        if eq < 0:
            continue
        val = raw[eq + 1:]
        newline = "\r\n" if "\r\n" in val else "\n"
        projects, covered = [], 0
        for span in templates(val):
            if span.start < covered:
                continue
            covered = span.end
            n = name(val[span.start:span.end])
            if n == "vikiproje" or n.startswith("vikiproje "):
                projects.append(span)
        # Sagdan sola degistir: onceki konumlar sabit kalir.
        for i in range(len(projects) - 1, 0, -1):
            start = projects[i - 1].end
            length = projects[i].start - start
            if val[start:start + length].strip():
                continue
            val = val[:start] + newline + val[start + length:]
        changed = raw[:eq + 1] + val
        if changed == raw:
            continue
        outer = outer[:field.start] + changed + outer[field.start + field.length:]
        return text[:wrapper.start] + outer + text[wrapper.end:]
    return text


_REDIRECT = re.compile(r"^\s*#(?:REDIRECT|YÖNLENDİRME|YÖNLENDIRME)\b", re.IGNORECASE)


def is_redirect(text):
    return bool(_REDIRECT.match(mask(text)))


def process(text, en_source, en_talk_title):
    """Yerel tartisma metnini isler. (yeni_metin, ozet) dondurur; degisiklik yoksa ozet bos."""
    ratings = ratings_from_english(en_source)
    result = text
    for r in ratings:
        result = edit(result, r.project, r.importance)
    before_spacing = result
    result = compact_projects(result)
    if result == text:
        return text, ""
    if before_spacing == text:
        return result, "Vikiproje şablonları arasındaki boş satırlar kaldırıldı"
    return result, "Vikiprojeler ve önem dereceleri İngilizce Vikipedi'den aktarıldı ([[en:" + en_talk_title + "]])"
