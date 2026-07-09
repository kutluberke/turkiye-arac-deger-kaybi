# 🚗 Türkiye Araç Değer Kaybı Analizi

Türkiye ikinci el otomobil piyasasında **gerçek değer kaybını** üç ölçümle (bugünkü TL, USD, TÜFE-reel) hesaplayan uçtan uca veri projesi. "Hangi arabayı kaç yaşında almalıyım?" sorusuna veriyle cevap verir.

**Canlı dashboard:** `index.html` — 175 model, 183 motor varyantı, arama + interaktif grafikler.

## Ana Bulgular (Temmuz 2026)

- **Türkiye geneli önerilen alım bandı: 4–6 yaş.** En dik kayıp 0–3 yaş arası (yılda %7,5–8,5); 4–5 yaştan sonra %6,5 altına iner, kohort verisinde 6 yaş alımların USD bazlı yıllık kaybı ~%0.
- Model bazlı sweet spot medyanı 8 yaş (P25=5, P75=11) — marka bağımlı: Corolla/i20 değer tutar, Alman premiumları 11 yaşa kadar kaybetmeye devam eder.
- 2023–2025'te sıfır alan kohortların çoğu **nominal TL bazında bile** zararda; "araba enflasyondan korur" tezi 2020–2021 dönemine özgüydü.

## Veri Seti

Bildiğimiz kadarıyla Türkiye'nin **geçmişten günümüze sıfır km fiyat arşivini** içeren ilk açık veri seti (`data/veri_sifir_fiyatlar.csv`, 2020–2026, Wayback Machine + TCMB kuru eşleştirmeli).

| Dosya | İçerik |
|---|---|
| `data/veri_tum_ilanlar.csv` | 38.868 temiz ikinci el ilanı (241 model, 2015–2026): fiyat, yıl, km, varyant |
| `data/veri_sifir_fiyatlar.csv` | Tarihsel sıfır km fiyat aralıkları (45 model × 2020–2026) + aynı günün TCMB USD kuru |
| `data/veri_sifir_guncel.csv` | Bugünkü sıfır km fiyat aralıkları (194 model, 33 marka) |
| `data/veri_kohort_usd_tufe.csv` | Kohort analizi: o yıl sıfır alanın nominal/USD/TÜFE-reel kaybı (176 kohort, 41 model) |
| `data/veri_ilanlar.csv` | İlk pilot: C-SUV segmenti ilanları |

## Metodoloji

1. **Kesitsel yaklaşım:** Aynı modelin farklı yaşları bugünkü fiyatlarla kıyaslanır → enflasyon etkisi otomatik elenir.
2. **Km kontrolü:** `log(fiyat) ~ yaş + yaş² + km-sapması` OLS regresyonu; eğri, yaşına göre tipik km'li araç içindir.
3. **Optimal alım yaşı:** Marjinal yıllık kaybın %5 altına indiği ilk yaş; düzleşme eşiği %3.
4. **USD katmanı:** Her kohortun sıfır fiyatı Wayback arşivinden, kur aynı günün TCMB satış kuru.
5. **TÜFE katmanı:** TÜİK Temmuz YoY zinciriyle reel kayıp.
6. **Kalite katmanları:** IQR outlier temizliği; kısa geçmişli modellere lineer fallback; `atipik` / `kısa geçmiş` / `sınırlı veri` bayrakları.

Detaylar: `reports/rapor_tum_araclar.xlsx` → Metodoloji sayfası.

## Kullanım

```bash
pip install curl_cffi beautifulsoup4 pandas numpy

cd scripts
python deger_kaybi_full.py katalog   # marka/model kataloğu
python deger_kaybi_full.py rank      # ilan hacmi ölçümü
python deger_kaybi_full.py scrape    # ikinci el kazıma (resumable)
python deger_kaybi_full.py sifir     # bugünkü sıfır fiyatlar
python deger_kaybi_full.py wayback   # tarihsel sıfır fiyatlar (yavaş, resumable)
python deger_kaybi_full.py analiz    # eğriler + kohort + özet
```

Not: `curl_cffi` şart (Cloudflare TLS parmak izi). `CUR_RATE` ve `TUFE_YOY` değerlerini güncel tutun.

## Sınırlamalar

- Model-yıl başına ~50 ilan örneği (ilk sayfa); jenerasyon değişimleri smooth eğriyle kısmen emilir.
- "Sıfırdan ilk yıl kaybı" liste fiyatı bazlıdır, trim karması farkı içerebilir (`geniş aralık` bayrağına dikkat).
- Tramer/hasar verisi yoktur.

## Kaynaklar

[arabam.com](https://www.arabam.com) · [TCMB kur arşivi](https://www.tcmb.gov.tr/kurlar/) · [TÜİK/BTSO TÜFE](https://www.btso.org.tr/en/bilgi-bankasi/istatistikler-ve-raporlar/ufe-tufe-oranlari) · [Wayback Machine](https://web.archive.org)

Veriler yalnızca araştırma/eğitim amaçlıdır. İlan verileri arabam.com'a aittir.

---
*Kutlu Berke Yıldırım — 2026*
