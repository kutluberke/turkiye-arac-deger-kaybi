# -*- coding: utf-8 -*-
"""
TURKIYE ARAC DEGER KAYBI PIPELINE'I v2
=======================================
Asamalar (sirayla calistir):
  python deger_kaybi_full.py katalog   -> marka/model katalogu (catalog.json)
  python deger_kaybi_full.py rank      -> ilan hacmi olcumu (rank_state.json)
  python deger_kaybi_full.py scrape    -> yil bazli ikinci el kazima [RESUMABLE]
  python deger_kaybi_full.py sifir     -> bugunku sifir km fiyatlari (sifir_guncel.csv)
  python deger_kaybi_full.py wayback   -> tarihsel sifir fiyatlar + TCMB kuru [RESUMABLE, yavas]
  python deger_kaybi_full.py analiz    -> egriler + kohort (USD/TUFE) + Turkiye ozeti

Gereksinim: pip install curl_cffi beautifulsoup4 pandas numpy
Notlar: curl_cffi sart (duz requests Cloudflare'den 403 yer). Excel aciksa CSV yazma!
TUFE YoY degerlerini yilda bir guncelle (asagida TUFE_YOY).
"""
import csv, json, os, re, sys, time, random, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import pandas as pd, numpy as np

CATS = ["otomobil", "arazi-suv-pick-up"]
YEARS = list(range(2015, 2027))
CUR_YEAR = 2026
CUR_RATE = 46.67          # bugunku TCMB USD satis — guncelle!
TOP_N = None              # None = MIN_VOL ustu tum modeller
MIN_VOL = 30
MAX_WORKERS = 4
# TUIK Temmuz YoY TUFE (%) — her yil guncelle
TUFE_YOY = {2020:11.76, 2021:18.95, 2022:79.60, 2023:47.83, 2024:61.78, 2025:33.52, 2026:32.11}

def get(url, **kw):
    from curl_cffi import requests as cr
    return cr.get(url, impersonate="chrome", timeout=25,
                  headers={"Accept-Language": "tr-TR,tr;q=0.9"}, **kw)

def parse_int(t):
    t = t.replace(".", "").replace("TL", "").strip()
    return int(t) if t.isdigit() else None

MULTI = ["alfa-romeo","aston-martin","mercedes-benz","land-rover","mini-cooper","ds-automobiles"]
def brandize(slug):
    for mb in MULTI:
        if slug.startswith(mb+"-"):
            rest = slug[len(mb):].strip("-").replace("-"," ")
            return mb.replace("-"," ").title() + " " + (rest.upper() if len(rest)<=3 else rest.title())
    p = slug.split("-")
    return p[0].title() + " " + " ".join(x.upper() if len(x)<=2 else x.title() for x in p[1:])

# ------------------------- KATALOG -------------------------
def stage_katalog():
    from bs4 import BeautifulSoup
    allm = {}
    for cat in CATS:
        r = get(f"https://www.arabam.com/ikinci-el/{cat}")
        soup = BeautifulSoup(r.text, "html.parser")
        brands = sorted({a.get("href","").split("?")[0].strip("/").split("/")[2]
                         for a in soup.select(f'a[href^="/ikinci-el/{cat}/"]')
                         if len(a.get("href","").split("?")[0].strip("/").split("/")) == 3})
        for brand in brands:
            try:
                rb = get(f"https://www.arabam.com/ikinci-el/{cat}/{brand}")
                nodes = re.findall(r'\{"Id":(\d+),"Name":"([^"]*)"[^}]*?"ParentId":(\d+)[^}]*?"AbsolutePath":"([^"]*)"', rb.text)
                ids = {int(n): (nm, int(p), pa) for n, nm, p, pa in nodes}
                bids = [i for i,(nm,p,pa) in ids.items() if pa == f"{cat}/{brand}"]
                for i,(nm,p,pa) in ids.items():
                    if p in bids and pa.startswith(f"{cat}/"):
                        slug = pa.split("/")[-1]
                        if any(x in slug for x in ["sahibinden","galeriden","yetkili"]): continue
                        allm[slug] = {"cat": cat, "name": nm}
                print(f"{cat}/{brand} ok ({len(allm)})"); time.sleep(0.4)
            except Exception as e:
                print("HATA", brand, e); time.sleep(2)
    json.dump(allm, open("catalog.json","w"), ensure_ascii=False)
    print(f"Katalog: {len(allm)} model")

# ------------------------- RANK -------------------------
def stage_rank():
    cat_map = json.load(open("catalog.json"))
    state = json.load(open("rank_state.json")) if os.path.exists("rank_state.json") else {}
    def probe(slug):
        r = get(f"https://www.arabam.com/ikinci-el/{cat_map[slug]['cat']}/{slug}?minYear=2015&take=50")
        rows = len(re.findall(r'listing-list-item', r.text))
        m = re.search(r'js-hook-for-total-page-count">(\d+)', r.text)
        return slug, rows, (int(m.group(1)) if m else 1)
    todo = [s for s in cat_map if s not in state]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for f in as_completed({ex.submit(probe, s): s for s in todo}):
            try:
                slug, rows, pages = f.result()
                state[slug] = {"rows": rows, "pages": pages}
                if len(state) % 25 == 0:
                    json.dump(state, open("rank_state.json","w")); print(len(state))
            except Exception: pass
    json.dump(state, open("rank_state.json","w")); print(f"Rank: {len(state)}")

# ------------------------- SCRAPE -------------------------
def stage_scrape():
    from bs4 import BeautifulSoup
    cat_map = json.load(open("catalog.json"))
    rank = json.load(open("rank_state.json"))
    vol = lambda v: v["rows"] if v["pages"] == 1 else v["pages"]*50
    targets = [s for s,v in sorted(rank.items(), key=lambda kv: -vol(kv[1])) if vol(v) >= MIN_VOL][:TOP_N]
    print(f"{len(targets)} model kazinacak")
    done = set(json.load(open("deep_state.json"))) if os.path.exists("deep_state.json") else set()
    newf = not os.path.exists("full_listings.csv")
    fh = open("full_listings.csv", "a", newline="", encoding="utf-8")
    wr = csv.writer(fh); lock = threading.Lock()
    if newf: wr.writerow(["slug","name","cat","title","year","km","price_tl"])
    def job(slug, year):
        cat, name = cat_map[slug]["cat"], cat_map[slug]["name"]
        r = get(f"https://www.arabam.com/ikinci-el/{cat}/{slug}?minYear={year}&maxYear={year}&take=50")
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
            for td in tds[5:]:
                t = td.get_text(strip=True)
                if t.endswith("TL"): price = parse_int(t); break
            if y.isdigit() and price:
                out.append([slug, name, cat, title, int(y), km, price])
        return out
    todo = [(s,y) for s in targets for y in YEARS if f"{s}|{y}" not in done]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(job, s, y): (s,y) for s,y in todo}
        for f in as_completed(futs):
            s, y = futs[f]
            try:
                rows = f.result()
                with lock:
                    wr.writerows(rows); fh.flush(); done.add(f"{s}|{y}")
                if len(done) % 50 == 0:
                    json.dump(sorted(done), open("deep_state.json","w")); print(len(done), end="\r")
            except Exception as e:
                print("HATA", s, y, e)
    json.dump(sorted(done), open("deep_state.json","w")); fh.close()
    print(f"\nScrape tamam: {len(done)}")

# ------------------------- SIFIR (bugunku) -------------------------
def stage_sifir():
    from bs4 import BeautifulSoup
    r = get("https://www.arabam.com/sifir-km")
    soup = BeautifulSoup(r.text, "html.parser")
    brands = sorted({a.get("href","").split("/")[-1].replace("-fiyat-listesi","")
                     for a in soup.select('a[href*="fiyat-listesi"]')
                     if a.get("href","").endswith("fiyat-listesi")})
    # katalogdaki tum markalari da dene
    if os.path.exists("catalog.json"):
        cat_map = json.load(open("catalog.json"))
        brands = sorted(set(brands) | {s.split("-")[0] for s in cat_map} |
                        {mb for mb in MULTI for s in cat_map if s.startswith(mb)})
    rows = []
    for b in brands:
        try:
            rb = get(f"https://www.arabam.com/sifir-km/{b}-fiyat-listesi")
            if rb.status_code != 200: continue
            sp = BeautifulSoup(rb.text, "html.parser")
            for a in sp.select("a[href*='fiyat-listesi-yakit-tuketimi']"):
                slug = a.get("href","").split("/")[-1].replace("-fiyat-listesi-yakit-tuketimi","")
                if not slug.startswith(b.split("-")[0]): continue  # sahte yonlendirme filtresi
                txt = ' '.join(a.get_text(' ',strip=True).split())
                m = re.search(r'([\d.]{7,13})\s*(?:-\s*([\d.]{7,13}))?\s*TL', txt)
                if not m: continue
                pmin = int(m.group(1).replace(".",""))
                pmax = int(m.group(2).replace(".","")) if m.group(2) else pmin
                rows.append([slug, b, txt[:60], pmin, pmax])
            time.sleep(0.4)
        except Exception as e:
            print("HATA", b, e)
    seen, uniq = set(), []
    for r2 in rows:
        if r2[0] not in seen: seen.add(r2[0]); uniq.append(r2)
    with open("sifir_guncel.csv","w",newline="",encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["slug","brand","label","price_min_tl","price_max_tl"]); w.writerows(uniq)
    print(f"Sifir guncel: {len(uniq)} model")

# ------------------------- WAYBACK (tarihsel) -------------------------
def stage_wayback():
    import requests as rq
    # hedef: kazinan en hacimli modeller (rank'tan) — istedigin kadar genislet
    rank = json.load(open("rank_state.json"))
    vol = lambda v: v["rows"] if v["pages"] == 1 else v["pages"]*50
    slugs = [s for s,v in sorted(rank.items(), key=lambda kv: -vol(kv[1])) if vol(v) >= 100][:60]
    def tcmb_rate(dt):
        for off in range(6):
            d = dt - timedelta(days=off)
            url = f"https://www.tcmb.gov.tr/kurlar/{d.strftime('%Y%m')}/{d.strftime('%d%m%Y')}.xml"
            try:
                r = rq.get(url, timeout=12, headers={"User-Agent":"Mozilla/5.0"})
                if r.status_code == 200:
                    m = re.search(r'CurrencyCode="USD".*?<ForexSelling>([\d.]+)</ForexSelling>', r.text, re.S)
                    if m: return float(m.group(1))
            except Exception: pass
        return None
    done = set(json.load(open("wb_state.json"))) if os.path.exists("wb_state.json") else set()
    newf = not os.path.exists("new_prices.csv")
    f = open("new_prices.csv","a",newline="")
    w = csv.writer(f)
    if newf: w.writerow(["slug","year","snapshot","price_min_tl","price_max_tl","usd_rate"])
    for slug in slugs:
        for y in range(2020, CUR_YEAR+1):
            key = f"{slug}|{y}"
            if key in done: continue
            try:
                api = (f"http://archive.org/wayback/available?url=arabam.com/sifir-km/"
                       f"{slug}-fiyat-listesi-yakit-tuketimi&timestamp={y}0701")
                c = rq.get(api, timeout=20).json().get("archived_snapshots",{}).get("closest")
                if c and c.get("available"):
                    ts = c["timestamp"]
                    if abs((datetime.strptime(ts[:8],"%Y%m%d") - datetime(y,7,1)).days) <= 550:
                        h = rq.get(c["url"].replace("http://","https://"), timeout=40).text
                        m = re.search(r'price-range-title">Fiyat Aral[^<]*</span>\s*<span[^>]*>\s*([\d.]+)\s*TL\s*-\s*([\d.]+)\s*TL', h)
                        if m:
                            pmin, pmax = int(m.group(1).replace(".","")), int(m.group(2).replace(".",""))
                        else:
                            ps = [int(p.replace(".","")) for p in re.findall(r'([\d.]{7,13})\s*TL', h)]
                            ps = [p for p in ps if 100_000 <= p <= 60_000_000]
                            pmin, pmax = (min(ps), max(ps)) if ps else (None, None)
                        if pmin:
                            rate = tcmb_rate(datetime.strptime(ts[:8],"%Y%m%d"))
                            w.writerow([slug, y, ts, pmin, pmax, rate]); print(key, pmin, pmax, rate)
                done.add(key); f.flush()
                json.dump(sorted(done), open("wb_state.json","w"))
                time.sleep(2)   # wayback rate-limit
            except Exception as e:
                print("HATA", key, str(e)[:60]); time.sleep(5)
    f.close(); print("Wayback tamam")

# ------------------------- ANALIZ -------------------------
ENG = r'(\d\.\d)\s*(e-?THP|BlueHDi|HDi|dCi|TCe|SCe|CRDI|CRDi|GDI|T-GDI|TSI|TDI|TGI|EcoBoost|TDCi|DIG-T|Hybrid|Multijet|MultiJet|FireFly|PureTech|VTi|THP|D-4D|JTD|CDTI|CDTi|BiTurbo|Turbo|D|d|i|e)?'
def fit_curve(g):
    valid = [a for a in sorted(g.age.unique()) if (g.age==a).sum() >= 10]
    if len(valid) < 3:
        valid = [a for a in sorted(g.age.unique()) if (g.age==a).sum() >= 8]
    if len(valid) < 2: return None
    g = g[g.age.isin(valid)].copy()
    med_km = g.groupby("age")["km"].median()
    g["km_dev"] = np.log1p(g.km) - g.age.map(np.log1p(med_km))
    linear = len(valid) <= 3
    X = (np.column_stack([np.ones(len(g)), g.age, g.km_dev]) if linear
         else np.column_stack([np.ones(len(g)), g.age, g.age**2, g.km_dev]))
    try: b, *_ = np.linalg.lstsq(X, np.log(g.price_tl.values), rcond=None)
    except Exception: return None
    a0, b1 = b[0], b[1]; b2 = 0.0 if linear else b[2]
    amin, amax = int(min(valid)), int(max(valid))
    smooth = {a: float(np.exp(a0+b1*a+b2*a*a)) for a in range(amin, amax+1)}
    marg = {a: round(max(100*(1-smooth[a+1]/smooth[a]),0.0),2) for a in range(amin,amax)}
    if not marg: return None
    sweet = next((a for a in sorted(marg) if marg[a] < 5.0), amax)
    flat = next((a for a in sorted(marg) if marg[a] < 3.0), None)
    mk = sorted(marg)
    return {"smooth_curve": smooth, "smooth_marginal": marg,
            "median_raw": {int(k): float(v) for k,v in g.groupby("age")["price_tl"].median().items()},
            "counts": {int(k): int(v) for k,v in g.groupby("age").size().items()},
            "sweet_age": int(sweet), "sweet_year": CUR_YEAR-int(sweet),
            "flat_age": int(flat) if flat is not None else None,
            "atipik": bool(marg[mk[-1]] > marg[mk[0]] + 0.5),
            "kisa_gecmis": linear, "sinirli": len(valid) == 2, "n": int(len(g))}

def stage_analiz():
    df = pd.read_csv("full_listings.csv").drop_duplicates().dropna(subset=["price_tl"])
    df["km"] = df["km"].fillna(0)
    df = df[(df.year >= 2015) & (df.price_tl >= 50_000)]
    df["age"] = CUR_YEAR - df.year
    def var_of(row):
        m = re.search(ENG, str(row.title))
        return (m.group(1) + ((" "+m.group(2)) if m.group(2) else "")).strip() if m else "diger"
    df["variant"] = df.apply(var_of, axis=1)
    def iqr(g):
        if len(g) < 8: return g
        q1, q3 = g.price_tl.quantile([.25,.75]); r = q3-q1
        return g[(g.price_tl >= q1-1.5*r) & (g.price_tl <= q3+1.5*r)]
    df = df.groupby(["slug","year"], group_keys=False).apply(iqr)
    models, variants = {}, {}
    for (slug, name), g in df.groupby(["slug","name"]):
        r = fit_curve(g)
        if r:
            r["display"] = brandize(slug); models[slug] = r
        for var, gv in g.groupby("variant"):
            if var == "diger" or len(gv) < 60: continue
            rv = fit_curve(gv)
            if rv:
                rv["display"] = brandize(slug)+" "+var; variants[f"{slug}|{var}"] = rv
    # yas-0 capasi
    if os.path.exists("sifir_guncel.csv"):
        sg = pd.read_csv("sifir_guncel.csv")
        mslugs = list(models)
        def owner(s):
            c = [m for m in mslugs if s == m or s.startswith(m+"-")]
            return max(c, key=len) if c else None
        sg["owner"] = sg.slug.map(owner)
        for slug, r in models.items():
            match = sg[sg.owner == slug]
            if not len(match): continue
            row = match.loc[match.price_min_tl.idxmin()]
            mid = (row.price_min_tl + row.price_max_tl) / 2
            r["new_now"] = {"min": int(row.price_min_tl), "max": int(row.price_max_tl),
                            "mid": round(mid), "genis": bool(row.price_max_tl > 1.8*row.price_min_tl)}
            sc = {int(k): v for k,v in r["smooth_curve"].items()}
            if 1 in sc and mid > 0:
                r["ilk_yil_sifirdan"] = round(100*(1 - sc[1]/mid), 1)
    # kohort (USD + TUFE)
    I = {CUR_YEAR: 100.0}
    for y in range(CUR_YEAR-1, 2018, -1):
        I[y] = I[y+1] / (1 + TUFE_YOY[y+1]/100)
    if os.path.exists("new_prices.csv"):
        npdf = pd.read_csv("new_prices.csv").drop_duplicates(subset=["slug","year"], keep="last")
        npdf["mid_tl"] = (npdf.price_min_tl + npdf.price_max_tl)/2
        npdf["snap_year"] = npdf.snapshot.astype(str).str[:4].astype(int)
        yr = npdf.dropna(subset=["usd_rate"]).groupby("snap_year")["usd_rate"].median()
        npdf["usd_rate"] = npdf.usd_rate.fillna(npdf.snap_year.map(yr))
        npdf["new_usd"] = npdf.mid_tl / npdf.usd_rate
        rows = []
        for _, r in npdf.iterrows():
            slug = r.slug
            if slug not in models: continue
            year = int(r.year)
            cohort = df[(df.slug==slug) & (df.year==year)]
            if len(cohort) < 10 or r.new_usd <= 0 or abs(r.snap_year-year) > 1: continue
            if not (8000 <= r.new_usd <= 120000): continue
            used_tl = cohort.price_tl.median(); used_usd = used_tl/CUR_RATE
            age = CUR_YEAR-year; aeff = max(age,1)
            infl = 100.0 / I.get(r.snap_year, I[2020])
            rows.append({"slug": slug, "display": models[slug]["display"], "year": year, "age": age,
                "new_tl": round(r.mid_tl), "new_usd": round(r.new_usd),
                "used_tl": round(used_tl), "used_usd": round(used_usd),
                "nominal_pct": round(100*(used_tl/r.mid_tl-1),1),
                "usd_loss_pct": round(100*(1-used_usd/r.new_usd),1),
                "usd_loss_yillik": round(100*(1-(used_usd/r.new_usd)**(1/aeff)),1),
                "tufe_reel_loss_pct": round(100*(1-(used_tl/r.mid_tl)/infl),1),
                "tufe_reel_yillik": round(100*(1-((used_tl/r.mid_tl)/infl)**(1/aeff)),1),
                "n": len(cohort), "snapshot": str(r.snapshot)[:8]})
        pd.DataFrame(rows).drop_duplicates(["slug","year"]).to_csv("kohort_analiz.csv", index=False)
        print(f"kohort: {len(rows)} satir")
    json.dump({"models": models, "variants": variants}, open("full_results.json","w"), ensure_ascii=False)
    print(f"\n{len(models)} model, {len(variants)} varyant")
    print("\n=== OPTIMAL ALIM YASLARI (hacme gore ilk 30) ===")
    for slug, r in sorted(models.items(), key=lambda kv: -kv[1]["n"])[:30]:
        et = " [ATIPIK]" if r["atipik"] else (" [KISA]" if r["kisa_gecmis"] else "")
        iy = f" | sifirdan ilk yil: %{r['ilk_yil_sifirdan']}" if "ilk_yil_sifirdan" in r else ""
        print(f"{r['display']:32s} sweet: {r['sweet_age']}y ({r['sweet_year']}){iy}{et}")

if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "analiz"
    {"katalog": stage_katalog, "rank": stage_rank, "scrape": stage_scrape,
     "sifir": stage_sifir, "wayback": stage_wayback, "analiz": stage_analiz}[stage]()
