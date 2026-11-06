"""TEFAS'tan sitedeki fonların son 1 yıllık günlük pay fiyatı (POST /api/funds/fonFiyatBilgiGetir, periyod=12).
Çıktı: public/veri/fon/fiyat/<KOD>.json  {"kod":..., "guncel":..., "f": [["YYYY-MM-DD", fiyat], ...]}"""
import os, json, time, datetime, urllib.request
KOK = os.path.join(os.path.dirname(__file__), "..", "..")
OUT = os.path.join(KOK, "public", "veri", "fon", "fiyat"); os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 Sonar-Bekci"
def cek(kod):
    r = urllib.request.Request("https://www.tefas.gov.tr/api/funds/fonFiyatBilgiGetir", json.dumps({"fonKodu": kod, "dil": "TR", "periyod": 12}).encode(),
                               {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA, "Origin": "https://www.tefas.gov.tr", "Referer": f"https://www.tefas.gov.tr/tr/fon-detayli-analiz/{kod}"})
    R = json.loads(urllib.request.urlopen(r, timeout=60).read().decode("utf-8"))
    return [[x["tarih"][:10], x["fiyat"]] for x in (R.get("resultList") or []) if x.get("fiyat") is not None]
def main():
    p = os.path.join(KOK, "veri", "fon", "fonlar.json")
    kodlar = [f["kod"] for f in json.load(open(p))["fonlar"]] if os.path.exists(p) else []
    tamam = hata = 0
    for kod in kodlar:
        for k in range(3):
            try:
                L = cek(kod)
                if L:
                    json.dump({"kod": kod, "guncel": datetime.date.today().isoformat(), "f": L}, open(os.path.join(OUT, kod + ".json"), "w"), separators=(",", ":"))
                    tamam += 1
                else: hata += 1
                break
            except Exception as e:
                if k == 2: hata += 1; print(kod, "hata", repr(e)[:120])
                time.sleep(5 * (k + 1))
        time.sleep(0.6)
    print(f"fiyat: {tamam} fon yazıldı, {hata} hata")
if __name__ == "__main__":
    main()
