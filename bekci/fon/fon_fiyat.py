"""TEFAS'tan sitedeki fonların günlük pay fiyatı (POST /api/funds/fonFiyatBilgiGetir; periyod ay sayısı: 1,3,6,12,36,60).
Dosyası olmayan ya da 5 yıllık geçmişi eksik fon için periyod=60 (5 yıl) çekilir; diğerlerine yalnız son 1 ay (periyod=1) çekilip eklenir.
Çıktı: public/veri/fon/fiyat/<KOD>.json  {"kod":..., "guncel":..., "tam":1, "f": [["YYYY-MM-DD", fiyat], ...]} (her nokta ayrı satırda: günlük değişiklik küçük kalır)
Süre sınırı FIYAT_SURE dk (vars. 20): biterse kalanlar sonraki koşuya kalır (en eski güncellenenden başlanır)."""
import os, json, time, datetime, urllib.request, http.cookiejar
KOK = os.path.join(os.path.dirname(__file__), "..", "..")
OUT = os.path.join(KOK, "public", "veri", "fon", "fiyat"); os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def log(*a): print(*a, flush=True)
def oturum():
    try: OP.open(urllib.request.Request("https://www.tefas.gov.tr/tr/fon-getirileri", headers={"User-Agent": UA}), timeout=20).read(); log("oturum açıldı")
    except Exception as e: log("oturum açılamadı", repr(e)[:120])
def cek(kod, periyod):
    r = urllib.request.Request("https://www.tefas.gov.tr/api/funds/fonFiyatBilgiGetir", json.dumps({"fonKodu": kod, "dil": "TR", "periyod": periyod}).encode(),
                               {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA, "Origin": "https://www.tefas.gov.tr", "Referer": f"https://www.tefas.gov.tr/tr/fon-detayli-analiz/{kod}"})
    R = json.loads(OP.open(r, timeout=30).read().decode("utf-8"))
    return [[x["tarih"][:10], x["fiyat"]] for x in (R.get("resultList") or []) if x.get("fiyat") is not None]
def oku(kod):
    p = os.path.join(OUT, kod + ".json")
    return json.load(open(p)) if os.path.exists(p) else {}
def yaz(kod, d):
    s = '{"kod":%s,"guncel":%s,"tam":%d,"f":[\n' % (json.dumps(kod), json.dumps(d["guncel"]), d.get("tam", 0)) + ",\n".join(json.dumps(x, separators=(",", ":")) for x in d["f"]) + "\n]}\n"
    open(os.path.join(OUT, kod + ".json"), "w").write(s)
def main():
    p = os.path.join(KOK, "veri", "fon", "fonlar.json")
    kodlar = [f["kod"] for f in json.load(open(p))["fonlar"]] if os.path.exists(p) else []
    kodlar.sort(key=lambda k: (oku(k).get("tam", 0), oku(k).get("guncel", "")))   # önce 5 yılı eksik olanlar
    bitis = time.time() + 60 * float(os.environ.get("FIYAT_SURE") or 20)
    oturum(); tamam = hata = ard = 0; simdi = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")
    for kod in kodlar:
        if time.time() > bitis: log("süre doldu"); break
        d = oku(kod); tam = d.get("tam") == 1
        try:
            L = cek(kod, 1 if tam else 60)
            if not L: hata += 1; log(kod, "boş"); continue
            S = {x[0]: x[1] for x in (d.get("f") or [])} if tam else {}
            S.update({x[0]: x[1] for x in L})
            sinir = (datetime.date.today() - datetime.timedelta(days=5 * 366 + 7)).isoformat()   # 5 yıldan eskisi atılır
            yaz(kod, {"guncel": simdi, "tam": 1, "f": [[k, S[k]] for k in sorted(S) if k >= sinir]}); tamam += 1; ard = 0
        except Exception as e:
            hata += 1; ard += 1; log(kod, "hata", repr(e)[:150])
            if ard >= 8: log("art arda 8 hata, durduruldu"); break
            time.sleep(3)
        time.sleep(0.5)
    log(f"fiyat: {tamam} fon yazıldı, {hata} hata")
if __name__ == "__main__":
    main()
