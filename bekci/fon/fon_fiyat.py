"""TEFAS'tan sitedeki fonların son 1 yıllık günlük pay fiyatı (POST /api/funds/fonFiyatBilgiGetir, periyod=12).
Çıktı: public/veri/fon/fiyat/<KOD>.json  {"kod":..., "guncel":..., "f": [["YYYY-MM-DD", fiyat], ...]}
Süre sınırı (FIYAT_SURE dk, vars. 20): biterse kalan fonlar bir sonraki koşuya kalır (en eski güncellenenden başlanır)."""
import os, json, time, datetime, urllib.request, http.cookiejar, sys
KOK = os.path.join(os.path.dirname(__file__), "..", "..")
OUT = os.path.join(KOK, "public", "veri", "fon", "fiyat"); os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def log(*a): print(*a, flush=True)
def isin():
    try: OP.open(urllib.request.Request("https://www.tefas.gov.tr/tr/fon-getirileri", headers={"User-Agent": UA}), timeout=20).read(); log("oturum açıldı")
    except Exception as e: log("oturum açılamadı", repr(e)[:120])
def cek(kod):
    r = urllib.request.Request("https://www.tefas.gov.tr/api/funds/fonFiyatBilgiGetir", json.dumps({"fonKodu": kod, "dil": "TR", "periyod": 12}).encode(),
                               {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA, "Origin": "https://www.tefas.gov.tr", "Referer": f"https://www.tefas.gov.tr/tr/fon-detayli-analiz/{kod}"})
    b = OP.open(r, timeout=20).read().decode("utf-8")
    R = json.loads(b)
    return [[x["tarih"][:10], x["fiyat"]] for x in (R.get("resultList") or []) if x.get("fiyat") is not None]
def main():
    p = os.path.join(KOK, "veri", "fon", "fonlar.json")
    kodlar = [f["kod"] for f in json.load(open(p))["fonlar"]] if os.path.exists(p) else []
    guncel = lambda k: (json.load(open(os.path.join(OUT, k + ".json"))).get("guncel", "") if os.path.exists(os.path.join(OUT, k + ".json")) else "")
    kodlar.sort(key=guncel)
    bitis = time.time() + 60 * float(os.environ.get("FIYAT_SURE") or 20)
    isin(); tamam = hata = ard = 0; bugun = datetime.date.today().isoformat()
    for kod in kodlar:
        if time.time() > bitis: log("süre doldu"); break
        if guncel(kod) == bugun: continue
        try:
            L = cek(kod)
            if L:
                json.dump({"kod": kod, "guncel": bugun, "f": L}, open(os.path.join(OUT, kod + ".json"), "w"), separators=(",", ":")); tamam += 1; ard = 0
            else: hata += 1; log(kod, "boş")
        except Exception as e:
            hata += 1; ard += 1; log(kod, "hata", repr(e)[:150])
            if ard >= 8: log("art arda 8 hata, durduruldu"); break
            time.sleep(3)
        time.sleep(0.5)
    log(f"fiyat: {tamam} fon yazıldı, {hata} hata")
if __name__ == "__main__":
    main()
