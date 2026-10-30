# vikiproject adding

Bu bot, Türkçe Vikipedi'deki **madde, şablon ve kategori** tartışma sayfalarına `{{Vikiproje}}` şablonlarını ekler. Hangi projelerin ekleneceğini ve önem derecelerini İngilizce Vikipedi'deki karşılığın tartışma sayfasından alır. AWB özel modülünün GitHub Actions üzerinde çalışan Python sürümüdür. Kurallar aynıdır: yinelenen proje, birden fazla `{{tartışma}}` şablonu ya da çelişen önem derecesi görürse sayfayı değiştirmez ve hatayı rapora yazar.

## Dosyalar

| Dosya | Görevi |
|---|---|
| `vikiproje.py` | Şablon ayrıştırma ve düzenleme kuralları (C# modülündeki mantığın aynısı) |
| `eslestirme.tsv` | İngilizce şablon → Türkçe proje eşleştirme tablosu (sekmeyle ayrılmış 4 sütun) |
| `bot.py` | Giriş, sayfa listesi, API istekleri, kaydetme |
| `test_vikiproje.py` | Her çalıştırmadan önce koşan testler |
| `sayfalar.txt` | "liste" kaynağı için başlık listesi |
| `.github/workflows/vikiproject-adding.yml` | Zamanlama ve elle çalıştırma |

## Kurulum

1. GitHub'da yeni bir depo açın (ör. `vikiproject-adding`) ve bu klasördeki dosyaları içine yükleyin. `.github` klasörünü de yüklemeyi unutmayın.
2. Vikipedi'de **Özel:BotŞifreleri** sayfasından `vikiproject-adding` adlı bir bot şifresi oluşturun. İzinler: *Basic rights*, *High-volume editing*, *Edit existing pages*, *Create, edit, and move pages*.
3. Depoda **Settings → Secrets and variables → Actions → New repository secret** yolunu izleyerek şu iki gizli değişkeni ekleyin:
   - `BOT_USER` = `KullanıcıAdı@vikiproject-adding`
   - `BOT_PASS` = oluşturulan şifre
4. **Actions** sekmesinden iş akışlarını etkinleştirin.

## Çalıştırma

- **Otomatik:** Her gün 04:37'de (Türkiye saati) son 25 saatte açılan madde, şablon ve kategorilerin tartışma sayfalarını işler. Tartışma sayfası yoksa oluşturur.
- **Elle:** Actions → *vikiproject adding* → **Run workflow**.
  - `yeni`: değer olarak saat sayısı girilir (ör. `168` = son 1 hafta).
  - `kategori`: değer olarak kategori adı girilir. Kategorideki madde, şablon, kategori ve tartışma sayfaları işlenir.
  - `liste`: `sayfalar.txt` dosyasındaki başlıklar işlenir.
  - `sayfa`: `Başlık1|Başlık2` biçiminde başlıklar girilir.
  - **Kuru çalışma** elle başlatmada varsayılan olarak açıktır. Hiçbir şey kaydetmez, yalnızca farkları kayıtta gösterir. Sonuç doğruysa kutuyu kaldırıp yeniden çalıştırın.

Her çalıştırmanın özeti ve hatalı sayfalar, Actions çalıştırma sayfasındaki **Summary** bölümünde görünür.

## Güvenlik ve sınırlar

- Varsayılan olarak bir çalıştırmada en fazla 100 kayıt yapılır ve iki kayıt arasında 10 saniye beklenir. Hesapta bot hakkı yoksa bu bekleme 15 saniyeye çıkar. `maxlag=5`, `Retry-After` ve hız sınırı hatalarına uyulur.
- Kayıtlar `basetimestamp` ile yapılır, böylece araya giren bir düzenlemenin üzerine yazılmaz. Hesapta bot hakkı varsa düzenlemeler bot olarak işaretlenir.
- Büyük ölçekte çalıştırmadan önce *Vikipedi:Bot onay talepleri* sayfasından onay alın.
- Açık (public) depolarda 60 gün boyunca hiç commit olmazsa GitHub zamanlanmış işleri durdurur. Böyle olursa Actions sekmesinden yeniden etkinleştirin.

## Eşleştirme tablosunu güncellemek

`eslestirme.tsv` dosyasındaki her satır **sekmeyle** ayrılmış 4 sütundan oluşur. Bu sütunlar AWB modülündeki `VPEmbeddedData` ile aynıdır:

```
İngilizce şablon adı <TAB> Türkçe proje <TAB> koşul parametreleri <TAB> önem parametreleri
```

Koşul sütunu boş bırakılabilir. Önem sütununa `-` yazılırsa önem derecesi aktarılmaz.

## Görev 2: Diller arası bağlantılar (`diller-arasi`)

Maddelerdeki `[[:en:Sayfa|Metin]]` biçimindeki bağlantıları dönüştürür:

- Kaynak dildeki sayfanın **Türkçe karşılığı varsa** (dil bağlantılarından bulunur, yönlendirmeler izlenir) yerel bağlantıya çevirir: `[[Türkçe başlık|Metin]]`.
- Karşılığı **yoksa** `{{diller arası bağlantı|Başlık|dil}}` ya da görünen metin farklıysa `{{diller arası bağlantı|Başlık|dil|lt=Metin}}` yapar (görünen metin Türkçe başlık olarak kullanılmaz; böylece "2025", "Boyat," gibi hatalı kırmızı bağlantılar oluşmaz).
- `[[:tr:X]]` bağlantıları `[[X]]` olur.
- Kardeş projelere (`[[:en:s:...]]` gibi), başka ad alanlarına (kategori, dosya…), bölüm bağlantılarına (`#`) ve yorum/nowiki içindekilere dokunmaz.
- Dil kodları Türkçe Vikipedi'nin dil tablosundan alınır (`simple`, `zh-yue`, `be-tarask` dahil).
- Herhangi bir API sorgusu hata verirse sayfa hiç değiştirilmez ve rapora yazılır.

İş akışı: **Actions → diller arasi baglanti → Run workflow**. Varsayılan kaynak `arama`dır (tüm `[[:dil:...]]` bağlantısı içeren maddeleri bulur). Zamanlama, bot onayı alınana kadar kapalıdır; açmak için `.github/workflows/diller-arasi.yml` içindeki `schedule` satırlarının başındaki `#` işaretlerini kaldırın.
