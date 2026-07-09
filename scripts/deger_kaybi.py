# -*- coding: utf-8 -*-
"""
C-SUV Segmenti Gercek Deger Kaybi Analizi
==========================================
Asamalar:
  python deger_kaybi.py scrape    -> arabam.com ilanlarini toplar (resumable, listings.csv)
  python deger_kaybi.py wayback   -> tarihsel sifir km fiyatlari + TCMB kurlari (new_prices.csv)
  python deger_kaybi.py analiz    -> egriler + USD katmani (results.json, usd_clean.csv)

Gereksinimler: pip install curl_cffi beautifulsoup4 pandas numpy openpyxl
Not: curl_cffi, Cloudflare TLS parmak izi kontrolunu asmak icin sart (duz requests 403 yer).
"""
import csv, json, os, re, sys, time, random
from datetime import datetime, timedelta

import pandas as pd, numpy as np

MODELS = {
    "toyota-corolla-cross": "Toyota Corolla Cross", "kia-sportage": "Kia Sportage",
    "opel-mokka": "Opel Mokka", "hyundai-tucson": "Hyundai Tucson",
    "nissan-qashqai": "Nissan Qashqai", "volkswagen-t-roc": "VW T-Roc",
    "peugeot-3008": "Peugeot 3008", "renault-austral": "Renault Austral",
    "ford-kuga": "Ford Kuga", "dacia-duster": "Dacia Duster",
}
YEARS = list(range(2016, 2027))
CUR_YEAR = datetime.now().year
MAX_PAGES = 3

# ----------------------------- SCRAPE -----------------------------
def stage_scrape():
    from curl_cffi import requests
    from bs4 import BeautifulSoup
    BASE = "https://www.arabam.com/ikinci-el/arazi-suv-pick-up/{slug}"

    def parse_int(t):
        t = t.replace(".", "").replace("TL", "").strip()
        return int(t) if t.isdigit() else None

    def scrape_page(s, slug, year, page):
        url = BASE.format(slug=slug) + f"?minYear={year}&maxYear={year}&take=50&page={page}"
        r = s.get(url, timeout=25, impersonate="chrome",
                  headers={"Accept-Language": "tr-TR,tr;q=0.9"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for row in soup.select("tr.listing-list-item"):
            tds = row.select("td")
            if len(tds) < 7: continue
            title = tds[1].get_text(" ", strip=True)
            y = tds[3].get_text(strip=True)
            km = parse_int(tds[4].get_text(strip=True))
            price = None
            for td in tds[5:]:  # fiyat kolonu sabit degil, TL ile biteni bul
                t = td.get_text(strip=True)
                if t.endswith("TL"):
                    price = parse_int(t); break
            if y.isdigit() and price:
                out.append([slug, MODELS[slug], title, int(y), km, price])
        m = re.search(r'js-hook-for-total-page-count">(\d+)', r.text)
        return out, (int(m.group(1)) if m else 1)

    done = set(json.load(open("state.json"))) if os.path.exists("state.json") else set()
    newf = not os.path.exists("listings.csv")
    f = open("listings.csv", "a", newline="", encoding="utf-8")
    w = csv.writer(f)
    if newf: w.writerow(["slug", "model", "title", "year", "km", "price_tl"])
    s = requests.Session()
    for slug in MODELS:
        for year in YEARS:
            key = f"{slug}|{year}"
            if key in done: continue
            page, total, n = 1, 1, 0
            try:
                while page <= min(total, MAX_PAGES):
                    rows, total = scrape_page(s, slug, year, page)
                    w.writerows(rows); n += len(rows); page += 1
                    time.sleep(random.uniform(0.5, 1.0))
                done.add(key); print(f"{key}: {n}")
            except Exception as e:
                print(f"HATA {key}: {e}"); time.sleep(3)
            f.flush(); json.dump(sorted(done), open("state.json", "w"))
    f.close(); print("Scrape tamam.")

# ----------------------------- WAYBACK -----------------------------
def stage_wayback():
    import requests as rq

    def tcmb_rate(dt):
        for off in range(6):
            d = dt - timedelta(days=off)
            url = f"https://www.tcmb.gov.tr/kurlar/{d.strftime('%Y%m')}/{d.strftime('%d%m%Y')}.xml"
            try:
                r = rq.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    m = re.search(r'CurrencyCode="USD".*?<ForexSelling>([\d.]+)</ForexSelling>', r.text, re.S)
                    if m: return float(m.group(1))
            except Exception: pass
        return None

    done = set(json.load(open("wb_state.json"))) if os.path.exists("wb_state.json") else set()
    newf = not os.path.exists("new_prices.csv")
    f = open("new_prices.csv", "a", newline="")
    w = csv.writer(f)
    if newf: w.writerow(["slug", "year", "snapshot", "price_min_tl", "price_max_tl", "usd_rate"])
    for slug in MODELS:
        for y in range(2020, 2027):
            key = f"{slug}|{y}"
            if key in done: continue
            try:
                api = (f"http://archive.org/wayback/available?url=arabam.com/sifir-km/"
                       f"{slug}-fiyat-listesi-yakit-tuketimi&timestamp={y}0701")
                c = rq.get(api, timeout=20).json().get("archived_snapshots", {}).get("closest")
                if c and c.get("available"):
                    ts = c["timestamp"]
                    if abs((datetime.strptime(ts[:8], "%Y%m%d") - datetime(y, 7, 1)).days) <= 550:
                        h = rq.get(c["url"].replace("http://", "https://"), timeout=40).text
                        m = re.search(r'price-range-title">Fiyat Aral[^<]*</span>\s*<span[^>]*>\s*([\d.]+)\s*TL\s*-\s*([\d.]+)\s*TL', h)
                        if m:
                            pmin, pmax = (int(m.group(i).replace(".", "")) for i in (1, 2))
                            rate = tcmb_rate(datetime.strptime(ts[:8], "%Y%m%d"))
                            w.writerow([slug, y, ts, pmin, pmax, rate])
                            print(key, "->", pmin, pmax, rate)
                done.add(key); f.flush()
                json.dump(sorted(done), open("wb_state.json", "w"))
                time.sleep(4)  # wayback rate-limit
            except Exception as e:
                print("HATA", key, e); time.sleep(5)
    f.close(); print("Wayback tamam.")

# ----------------------------- ANALIZ -----------------------------
def stage_analiz():
    CUR_RATE = float(sys.argv[2]) if len(sys.argv) > 2 else 46.67  # TCMB guncel kur
    df = pd.read_csv("listings.csv").dropna(subset=["price_tl"])
    df["km"] = df["km"].fillna(0)
    df["age"] = CUR_YEAR - df["year"]

    def iqr_clean(g):
        if len(g) < 8: return g
        q1, q3 = g.price_tl.quantile([.25, .75]); iqr = q3 - q1
        return g[(g.price_tl >= q1 - 1.5*iqr) & (g.price_tl <= q3 + 1.5*iqr)]
    df = df.groupby(["model", "year"], group_keys=False).apply(iqr_clean)

    results = {}
    for model, g in df.groupby("model"):
        valid = [a for a in sorted(g.age.unique()) if (g.age == a).sum() >= 10]
        g = g[g.age.isin(valid)].copy()
        if len(valid) < 4:
            print(f"{model}: yetersiz veri, atlandi"); continue
        med_km = g.groupby("age")["km"].median()
        g["km_dev"] = np.log1p(g.km) - g.age.map(np.log1p(med_km))
        # log(fiyat) ~ yas + yas^2 + km sapmasi  (quadratic yas etkisi)
        X = np.column_stack([np.ones(len(g)), g.age, g.age**2, g.km_dev])
        b, *_ = np.linalg.lstsq(X, np.log(g.price_tl.values), rcond=None)
        a0, b1, b2, _ = b
        amin, amax = int(min(valid)), int(max(valid))
        smooth = {a: float(np.exp(a0 + b1*a + b2*a*a)) for a in range(amin, amax+1)}
        marg = {a: round(max(100*(1 - smooth[a+1]/smooth[a]), 0.0), 2)
                for a in range(amin, amax)}
        sweet = next((a for a in sorted(marg) if marg[a] < 5.0), amax)
        flat = next((a for a in sorted(marg) if marg[a] < 3.0), None)
        results[model] = {
            "smooth_curve": smooth, "smooth_marginal": marg,
            "median_raw": {int(k): float(v) for k, v in g.groupby("age")["price_tl"].median().items()},
            "counts": {int(k): int(v) for k, v in g.groupby("age").size().items()},
            "sweet_age": int(sweet), "sweet_year": CUR_YEAR - int(sweet),
            "flat_age": int(flat) if flat is not None else None,
        }

    # USD katmani
    npdf = pd.read_csv("new_prices.csv")
    npdf["mid_tl"] = (npdf.price_min_tl + npdf.price_max_tl) / 2
    npdf["new_usd"] = npdf.mid_tl / npdf.usd_rate
    slug2model = dict(df.groupby("slug")["model"].first())
    rows = []
    for _, r in npdf.iterrows():
        model = slug2model.get(r.slug)
        if not model or model not in results: continue
        cohort = df[(df.model == model) & (df.year == int(r.year))]
        if len(cohort) < 10 or r.new_usd <= 0: continue
        used = cohort.price_tl.median() / CUR_RATE
        age = max(CUR_YEAR - int(r.year), 1)
        rows.append({"model": model, "year": int(r.year), "age": CUR_YEAR - int(r.year),
                     "new_usd": round(float(r.new_usd)), "used_usd_today": round(float(used)),
                     "total_loss_pct": round(100*(1 - used/r.new_usd), 1),
                     "annual_loss_pct": round(100*(1 - (used/r.new_usd)**(1/age)), 1),
                     "snapshot": str(r.snapshot)[:8], "n": len(cohort)})
    usd = pd.DataFrame(rows).drop_duplicates(["model", "year"])
    usd["snap_year"] = usd.snapshot.str[:4].astype(int)
    usd = usd[(usd.new_usd.between(15000, 80000)) & ((usd.snap_year - usd.year).abs() <= 1)]

    json.dump(results, open("results.json", "w"), ensure_ascii=False, indent=1)
    usd.to_csv("usd_clean.csv", index=False)
    print("\n=== OPTIMAL ALIM YASI ===")
    for m, r in sorted(results.items()):
        print(f"{m}: {r['sweet_age']} yas ({r['sweet_year']} model) | "
              f"duzlesme: {r['flat_age']} | o yastaki yillik kayip: %{r['smooth_marginal'].get(r['sweet_age'], '-')}")

if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "analiz"
    {"scrape": stage_scrape, "wayback": stage_wayback, "analiz": stage_analiz}[stage]()
