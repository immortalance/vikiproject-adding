"""Calistirmak icin: python -m unittest test_diller_arasi"""
import unittest

import bot
import diller_arasi as d

LANGS = {"en", "de", "fr", "zh", "tr", "simple", "zh-yue", "be-tarask"}

# AWB modulundeki TestRegex metni
METIN = """Bu bir test metnidir.
[[:tr:Osmanlı İmparatorluğu|Osmanlı]] Türkçe sayfa farklı metin.
[[:tr:Atatürk]] Türkçe sayfa aynı metin.
[[:en:Emperor Ming of Han|Han Mingdi]] hakkında bilgi (pipe ile, farklı metin).
[[:en:Emperor Ming of Han]] pipe olmadan.
[[:de:Nationaltheater Mannheim]] pipe olmadan Almanca.
[[:zh:s:新唐書/卷221下|新唐書/卷221下]] Çince Wikisource.
[[:en:s:Alice's Adventures in Wonderland|Alice's Adventures]] İngilizce Wikisource.
[[:en:Jaakko Hintikka|en]] dil kodu aynı.
[[:fr:Page française|fr]] Fransızca dil kodu aynı.
[[Kategori:Tarih]] - bu yakalanmamalı
[[doi:10.1111/j.1095-8339.1970.tb02321.x|DOI]] - bu da yakalanmamalı
<!-- [[:en:Gizli yorum]] --> <nowiki>[[:en:Nowiki içi]]</nowiki>
[[:en:Category:Rivers of Germany|nehirler]] başka ad alanı.
[[:en:Bölüm#Alt]] bölüm bağlantısı.
[[:simple:Basit sayfa]] ve [[:zh-yue:粵語頁]] ve [[:xx:Geçersiz dil]].
[[:en:A=B|Eşittir]] eşittir işareti.
"""

# bot.lookup_turkish sonucuna benzer bilgiler
INFOS = {
    ("tr", "Osmanlı İmparatorluğu"): {"tr": "Osmanlı İmparatorluğu"},
    ("tr", "Atatürk"): {"tr": "Atatürk"},
    ("en", "Emperor Ming of Han"): {"tr": "Ming (Han)"},
    ("de", "Nationaltheater Mannheim"): {"tr": None},
    ("zh", "s:新唐書/卷221下"): {"skip": True},
    ("en", "s:Alice's Adventures in Wonderland"): {"skip": True},
    ("en", "Jaakko Hintikka"): {"tr": None},
    ("fr", "Page française"): {"tr": None},
    ("en", "Category:Rivers of Germany"): {"skip": True},
    ("simple", "Basit sayfa"): {"tr": None},
    ("zh-yue", "粵語頁"): {"tr": None},
    ("en", "A=B"): {"tr": None},
}


class Donusturme(unittest.TestCase):
    def setUp(self):
        self.links = d.find_links(METIN, LANGS)
        self.new, self.local, self.tmpl = d.apply(METIN, self.links, INFOS)

    def test_bulunanlar(self):
        keys = [l.key for l in self.links]
        self.assertNotIn(("en", "Gizli yorum"), keys)
        self.assertNotIn(("en", "Nowiki içi"), keys)
        self.assertNotIn(("en", "Bölüm#Alt"), keys)
        self.assertFalse(any(k[0] == "xx" for k in keys))
        self.assertIn(("zh-yue", "粵語頁"), keys)

    def test_sonuclar(self):
        n = self.new
        self.assertIn("[[Osmanlı İmparatorluğu|Osmanlı]] Türkçe", n)
        self.assertIn("[[Atatürk]] Türkçe", n)
        self.assertIn("[[Ming (Han)|Han Mingdi]] hakkında", n)
        self.assertIn("[[Ming (Han)]] pipe olmadan", n)
        self.assertIn("{{diller arası bağlantı|Nationaltheater Mannheim|de}}", n)
        self.assertIn("[[:zh:s:新唐書/卷221下|新唐書/卷221下]]", n)
        self.assertIn("[[:en:s:Alice's Adventures in Wonderland|Alice's Adventures]]", n)
        self.assertIn("{{diller arası bağlantı|Jaakko Hintikka|en}}", n)
        self.assertIn("{{diller arası bağlantı|Page française|fr}}", n)
        self.assertIn("[[:en:Category:Rivers of Germany|nehirler]]", n)
        self.assertIn("<!-- [[:en:Gizli yorum]] -->", n)
        self.assertIn("{{diller arası bağlantı|Basit sayfa|simple}}", n)
        self.assertIn("{{diller arası bağlantı|Eşittir|en|3=A=B}}", n)
        self.assertIn("[[Kategori:Tarih]]", n)
        self.assertEqual((self.local, self.tmpl), (4, 6))

    def test_ozet(self):
        self.assertEqual(d.summary(4, 7), "Diller arası bağlantılar dönüştürüldü "
                         "(4 yerel bağlantı, 7 diller arası bağlantı şablonu)")

    def test_degisiklik_yoksa_ayni(self):
        new, a, b = d.apply("metin", [], {})
        self.assertEqual((new, a, b), ("metin", 0, 0))


class FakeApi:
    def __init__(self, q):
        self.q = q

    def query(self, **params):
        return {"query": self.q}


class Arama(unittest.TestCase):
    def test_langlinks_cozumleme(self):
        api = FakeApi({
            "interwiki": [{"iw": "s", "title": "s:Alice"}],
            "normalized": [{"from": "emperor Ming of Han", "to": "Emperor Ming of Han"}],
            "redirects": [{"from": "UK", "to": "United Kingdom"}],
            "pages": [
                {"ns": 0, "title": "Emperor Ming of Han", "langlinks": [{"lang": "tr", "title": "Ming (Han)"}]},
                {"ns": 0, "title": "United Kingdom", "langlinks": [{"lang": "tr", "title": "Birleşik Krallık"}]},
                {"ns": 0, "title": "Yok", "missing": True},
                {"ns": 14, "title": "Category:X", "langlinks": [{"lang": "tr", "title": "Kategori:X"}]},
            ]})
        r = bot.lookup_turkish(api, ["emperor Ming of Han", "UK", "Yok", "Category:X", "s:Alice"], False)
        self.assertEqual(r["emperor Ming of Han"], {"tr": "Ming (Han)"})
        self.assertEqual(r["UK"], {"tr": "Birleşik Krallık"})
        self.assertEqual(r["Yok"], {"tr": None})
        self.assertTrue(r["Category:X"]["skip"])
        self.assertTrue(r["s:Alice"]["skip"])


if __name__ == "__main__":
    unittest.main()
