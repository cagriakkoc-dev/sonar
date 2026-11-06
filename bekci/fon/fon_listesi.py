"""Fon listesi: KAP yatırım fonları sayfası (kod, fonOid, unvan, kurucu) + TEFAS getirileri (varsa).
Çıktı: veri/fon/liste.json  {"guncel":..., "tefas": "tamam"|"hata: ...", "fonlar": [{kod, oid, ad, kurucu, sinif, hisse_yogun, serbest, getiri}]}"""
import os, re, json, datetime, urllib.request

KOK = os.path.join(os.path.dirname(__file__), "..", "..")
VERI = os.path.join(KOK, "veri", "fon"); os.makedirs(VERI, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36 Sonar-Bekci"

def kap_fonlar():
    h = urllib.request.urlopen(urllib.request.Request("https://www.kap.org.tr/tr/YatirimFonlari/YF", headers={"User-Agent": UA}), timeout=120).read().decode("utf-8")
    h = h.replace('\\"', '"')
    m = {}
    for x in re.finditer(r'\{[^{}]*"fundOid":"[^{}]*\}', h):
        try: o = json.loads(x.group(0))
        except ValueError: continue
        if o.get("fundCode"): m.setdefault(o["fundCode"], {}).update(o)
    L = []
    for k, o in m.items():
        if not o.get("fundName") or o.get("fundState", "Y") != "Y": continue
        ad = o["fundName"].strip()
        L.append({"kod": k, "oid": o["fundOid"], "ad": ad, "kurucu": (o.get("fundMemberTitle") or "").strip(), "sinif": o.get("fundClass"),
                  "hisse_yogun": "HİSSE SENEDİ YOĞUN" in ad, "serbest": "SERBEST" in ad})
    return sorted(L, key=lambda x: x["kod"])

def tefas_getiri():
    body = {"dil": "TR", "fonTipi": "YAT", "kurucuKodu": None, "sfonTurKod": None, "fonTurAciklama": None, "islem": 1, "fonTurKod": None, "fonGrubu": None,
            "donemGetiri1a": "1", "donemGetiri3a": "1", "donemGetiri6a": "1", "donemGetiri1y": "1", "donemGetiriyb": "1", "donemGetiri3y": "1", "donemGetiri5y": "1",
            "basTarih": None, "bitTarih": None, "calismaTipi": 2, "getiriOrani": "1"}
    r = urllib.request.Request("https://www.tefas.gov.tr/api/funds/fonGetiriBazliBilgiGetir", json.dumps(body).encode(),
                               {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA, "Origin": "https://www.tefas.gov.tr", "Referer": "https://www.tefas.gov.tr/tr/fon-getirileri"})
    R = json.loads(urllib.request.urlopen(r, timeout=60).read().decode("utf-8"))
    return {x["fonKodu"]: {k: x.get(g) for k, g in (("1a", "getiri1a"), ("3a", "getiri3a"), ("6a", "getiri6a"), ("yb", "getiriyb"), ("1y", "getiri1y"), ("3y", "getiri3y"), ("5y", "getiri5y"))} | {"risk": x.get("riskDegeri"), "tefas": x.get("tefasDurum")}
            for x in R.get("resultList") or []}

def main():
    p = os.path.join(VERI, "liste.json")
    eski = json.load(open(p)) if os.path.exists(p) else {}
    try: L = kap_fonlar()
    except Exception as e:
        print("KAP fon listesi alınamadı:", repr(e)[:200]); L = eski.get("fonlar") or []
    durum = "tamam"
    try: G = tefas_getiri()
    except Exception as e:
        durum = "hata: " + repr(e)[:150]; G = {}
        print("TEFAS getirileri alınamadı:", durum)
    eskiG = {f["kod"]: f.get("getiri") for f in eski.get("fonlar") or []}
    for f in L: f["getiri"] = G.get(f["kod"]) or eskiG.get(f["kod"])
    json.dump({"guncel": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z", "tefas": durum, "fonlar": L}, open(p, "w"), ensure_ascii=False, indent=0)
    hs = [f for f in L if f["hisse_yogun"] and not f["serbest"]]
    print(f"{len(L)} fon; hisse yoğun (serbest değil) {len(hs)}; TEFAS {durum}, getirisi olan {sum(1 for f in L if f.get('getiri'))}")

if __name__ == "__main__":
    main()
