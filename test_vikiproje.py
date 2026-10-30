"""Calistirmak icin: python -m unittest test_vikiproje"""
import unittest

import vikiproje as v

EN = """{{Talk header}}
{{WikiProject banner shell|class=B|1=
{{WikiProject Turkey|importance=High}}
{{WikiProject Biography}}
{{WikiProject Film|American=yes|importance=mid}}
{{WikiProject Military history|WWII=yes}}
<!-- {{WikiProject Chess|importance=top}} -->
}}
== Bir baslik ==
{{WikiProject Physics|importance=top}}
"""


class Testler(unittest.TestCase):
    def test_eslestirme(self):
        r = v.ratings_from_english(EN)
        self.assertEqual([(x.project, x.importance) for x in r], [
            ("Türkiye", "Çok"), ("Biyografi", ""), ("Amerikan sineması", ""),
            ("Sinema", "Orta"), ("II. Dünya Savaşı", "")])

    def test_bos_sayfa(self):
        new, s = v.process("", EN, "Talk:X")
        self.assertTrue(new.startswith("{{tartışma\n| proje =\n{{Vikiproje | Proje = Türkiye | Sınıf = | Önem = Çok }}\n{{Vikiproje | Proje = Biyografi"))
        self.assertIn("aktarıldı", s)

    def test_mevcut_sarmalayici_ve_onem(self):
        text = "{{Tartışma\n| proje =\n{{Vikiproje | Proje = Türkiye | Sınıf = B | Önem = }}\n}}\nmetin"
        new, _ = v.process(text, "{{WikiProject Turkey|importance=low}}", "Talk:X")
        self.assertIn("Önem = Az", new)
        self.assertEqual(new.count("{{Vikiproje"), 1)

    def test_onem_dolu_ise_dokunma(self):
        text = "{{Tartışma\n| proje =\n{{Vikiproje | Proje = Türkiye | Önem = En }}\n}}"
        new, s = v.process(text, "{{WikiProject Turkey|importance=low}}", "Talk:X")
        self.assertEqual((new, s), (text, ""))

    def test_bos_satir_sikistirma(self):
        text = "{{tartışma\n| proje =\n{{Vikiproje | Proje = A }}\n\n\n{{Vikiproje | Proje = B }}\n}}"
        new, s = v.process(text, "", "Talk:X")
        self.assertEqual(new, "{{tartışma\n| proje =\n{{Vikiproje | Proje = A }}\n{{Vikiproje | Proje = B }}\n}}")
        self.assertIn("boş satırlar", s)

    def test_yonlendirme(self):
        self.assertTrue(v.is_redirect("#YÖNLENDİRME [[X]]"))
        self.assertTrue(v.is_redirect("#redirect [[X]]"))

    def test_celisen_onem(self):
        with self.assertRaises(v.VPError):
            v.ratings_from_english("{{WikiProject Turkey|importance=low}}{{WPTR|importance=top}}")

    def test_buyuk_kucuk_harf(self):
        # Wp bio -> Biyoloji, WP Bio -> Biyografi (yalniz ilk harf esdegerdir)
        self.assertEqual(v.extract("{{wp bio}}")[0].project, "Biyoloji")
        self.assertEqual(v.extract("{{WP Bio}}")[0].project, "Biyografi")


if __name__ == "__main__":
    unittest.main()
