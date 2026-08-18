# 🚗 Türkiye Araç Değer Kaybı Analizi

**🔴 Canlı Dashboard: [turkiye-arac-deger-kaybi.vercel.app](https://turkiye-arac-deger-kaybi.vercel.app/)**

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-veri%20analizi-150458?logo=pandas)
![Chart.js](https://img.shields.io/badge/Chart.js-dashboard-FF6384?logo=chartdotjs&logoColor=white)
![Veri](https://img.shields.io/badge/ilan-38.868-green)
![Model](https://img.shields.io/badge/model-175-orange)

Türkiye ikinci el otomobil piyasasında **gerçek değer kaybını** üç ölçümle hesaplayan uçtan uca veri projesi:

| Ölçüm | Cevapladığı soru |
|---|---|
| 💵 **Bugünkü TL** (kesitsel) | Bugün hangi yaştaki aracı alırsam önümüzdeki yıl % kaç kaybederim? |
| 💲 **USD** | O yıl sıfır alan, bugüne kadar dolar bazında % kaç kaybetti? |
| 📉 **TÜFE-reel** | Enflasyondan arındırınca gerçek kayıp ne? |

> **Ana bulgu:** Türkiye'de araba almanın en rasyonel penceresi **4–6 yaş**. En dik kayıp 0–3 yaş arasında (yılda %7,5–8,5); 4–5 yaştan sonra %6,5 altına iner, 6 yaş kohortlarının USD bazlı yıllık kaybı ~%0. Ve evet: 2023–2025'te sıfır alanların çoğu **nominal TL bazında bile** zararda — "araba enflasyondan korur" tezi 2020–2021'e özgüydü.

## 📊 Dashboard

<a href="https://turkiye-arac-deger-kaybi.vercel.app/">
<img alt="Dashboard" src="https://img.shields.io/badge/▶_Canlı_Demo-turkiye--arac--deger--kaybi.vercel.app-3ecf8e?style=for-the-badge" />
</a>

- 175 model + 183 motor varyantı, arama kutusu ve varyant seçici
- Yaş–fiyat eğrileri (km-kontrollü) + bugünkü sıfır fiyat çapası
- Marjinal yıllık kayıp grafikleri, optimal alım yaşı vurgusu
- Model bazlı "sıfır alan ne kaybetti" tablosu (nominal / USD / TÜFE-reel)
- Optimal alım yaşına göre tıklanabilir sıralama tablosu

## 🗃️ Veri Seti

Bildiğimiz kadarıyla Türkiye'nin **geçmişten günümüze sıfır km fiyat arşivini** içeren ilk açık veri seti.

| Dosya | İçerik |
|---|---|
| `data/veri_tum_ilanlar.csv` | 38.868 temiz ikinci el ilanı — 241 model, 2015–2026 (fiyat, yıl, km, varyant) |
| `data/veri_sifir_fiyatlar.csv` | **Tarihsel sıfır km fiyatları** — 45 model × 2020–2026, Wayback Machine + aynı günün TCMB USD kuru |
| `data/veri_sifir_guncel.csv` | Bugünkü sıfır km fiyat aralıkları — 194 model, 33 marka |
| `data/veri_kohort_usd_tufe.csv` | Kohort analizi — 176 kohort, 41 model: nominal/USD/TÜFE-reel kayıplar |
| `data/veri_ilanlar.csv` | Pilot çalışma: C-SUV segmenti |

## ⚙️ Pipeline

```
katalog → rank → scrape → sifir → wayback → analiz
```

```bash
pip install curl_cffi beautifulsoup4 pandas numpy
cd scripts
python deger_kaybi_full.py katalog   # 471 model kataloğu
python deger_kaybi_full.py rank      # ilan hacmi ölçümü
python deger_kaybi_full.py scrape    # ikinci el kazıma (resumable — kesip devam edebilirsin)
python deger_kaybi_full.py sifir     # bugünkü sıfır km fiyatları
python deger_kaybi_full.py wayback   # tarihsel sıfır fiyatlar (yavaş, resumable)
python deger_kaybi_full.py analiz    # eğriler + kohort + Türkiye özeti
```

> `curl_cffi` şart — standart `requests` Cloudflare TLS parmak izi kontrolünden 403 yer. `CUR_RATE` (TCMB kuru) ve `TUFE_YOY` sözlüğünü güncel tutun.

## 🔬 Metodoloji

1. **Kesitsel yaklaşım:** Aynı modelin farklı yaşları *bugünkü* fiyatlarla kıyaslanır → enflasyon etkisi tasarım gereği elenir.
2. **Km kontrolü:** `log(fiyat) ~ yaş + yaş² + km-sapması` OLS; eğri, yaşına göre tipik km'li araç içindir.
3. **Optimal alım yaşı:** Marjinal yıllık kaybın %5 altına indiği ilk yaş (düzleşme eşiği %3).
4. **USD katmanı:** Kohortun sıfır fiyatı Wayback arşivinden, kur aynı günün TCMB satış kuru.
5. **TÜFE katmanı:** TÜİK Temmuz YoY zinciri (2020–2026).
6. **Kalite kontrol:** Model-yıl bazında IQR outlier temizliği; kısa geçmişli modellere lineer fallback; `atipik` / `kısa geçmiş` / `sınırlı veri` bayrakları; bağımsız yeniden hesaplama ve formül doğrulama testleri.

Ayrıntılar: `reports/rapor_tum_araclar.xlsx` → *Metodoloji* sayfası.

## ⚠️ Sınırlamalar

- Model-yıl başına ~50 ilan örneği (ilk sayfa); jenerasyon değişimleri smooth eğriyle kısmen emilir.
- "Sıfırdan ilk yıl kaybı" liste fiyatı bazlıdır; trim karması farkı içerebilir (`geniş aralık` bayrağına dikkat — örn. VW Golf sıfırda yalnız üst trimlerle satılıyor).
- Tramer/hasar verisi yoktur; IQR filtresi kabaca telafi eder.
- Veriler Temmuz 2026 anlık görüntüsüdür.

## 📚 Kaynaklar

[arabam.com](https://www.arabam.com) · [TCMB kur arşivi](https://www.tcmb.gov.tr/kurlar/) · [TÜİK/BTSO TÜFE](https://www.btso.org.tr/en/bilgi-bankasi/istatistikler-ve-raporlar/ufe-tufe-oranlari) · [Wayback Machine](https://web.archive.org)

Veriler yalnızca araştırma/eğitim amaçlıdır. İlan verileri arabam.com'a aittir.

Bu proje ticari bir amaç taşımayıp sadece kişisel/akademik portfolyo çalışmasıdır. İlgili hak sahiplerinin talebi doğrultusunda içerik derhal kaldırılabilir.

---

*Kutlu Berke Yıldırım — [github.com/kutluberke](https://github.com/kutluberke) · 2026*
