"""KAP Portföy Dağılım Raporu (SPK II-14.2) metninden varlıkları çıkarır.
Kullanım: python3 pdr_ayristir.py rapor.txt  ->  JSON (stdout)
Satırlar ISIN'e göre bulunur; ağırlık = değer / fon toplam değeri."""
import re, sys, json

ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
SAYI = re.compile(r"%?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?%?|%?-?\d+(?:,\d+)?%?")
BOLUM = re.compile(r"^\s*([A-ZÇĞİÖŞÜ])\s*[\.\)-]\s*([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ ]{2,})")

def sayi(t):
    t = t.strip("%")
    try: return float(t.replace(".", "").replace(",", "."))
    except ValueError: return None

def sayilar(s):
    return [(m.group(), sayi(m.group())) for m in SAYI.finditer(s) if sayi(m.group()) is not None]

def deger_bul(nums):
    """Satır sonundaki sayılardan toplam değeri seçer: sondan geriye, yüzde olmayan ilk büyük sayı."""
    son = nums[-5:]
    for ham, v in reversed(son):
        if "%" in ham: continue
        if abs(v) > 100 or ("." in ham and "," in ham): return v
    return None

def bolum_turu(baslik):
    b = baslik.upper()
    if "PAY" in b or "HİSSE" in b or "HISSE" in b: return "hisse"
    if "BORÇ" in b or "BORC" in b: return "borclanma"
    if "TÜREV" in b or "TUREV" in b: return "turev"
    if "YABANCI" in b: return "yabanci"
    if "DİĞER" in b or "DIGER" in b: return "diger"
    if "FON" in b: return "fon"
    return b.strip()[:20].lower()

def ayristir(metin):
    bolum, kalemler, fon_toplam, hisse_grup = None, {}, None, None
    onceki = ""
    satirlar = metin.splitlines()
    for i, s in enumerate(satirlar):
        u = s.upper()
        m = BOLUM.match(s)
        if m and not ISIN.search(s) and len(s.strip()) < 90:
            bolum = bolum_turu(m.group(2))
        if ("FON PORTF" in u and ("DEĞER" in u or "DEGER" in u)) or "FON TOPLAM DEĞER" in u:
            n = [v for h, v in sayilar(s) if "%" not in h and v > 1000]
            if n and ("TOPLAM" in u or "DEĞERİ" in u or "DEGERI" in u or "DEĞERİ" in u):
                if fon_toplam is None or "TOPLAM" in u: fon_toplam = max(n)
        if bolum == "hisse" and hisse_grup is None and "TOPLAM" in u and not ISIN.search(s):
            n = [v for h, v in sayilar(s) if "%" not in h and v > 1000]
            if n: hisse_grup = max(n)
        mi = ISIN.search(s)
        if not mi:
            onceki = s; continue
        isin = mi.group(1)
        sag = s[mi.end():]
        nums = sayilar(sag)
        v = deger_bul(nums)
        if v is None and i + 1 < len(satirlar):  # sayılar alt satıra kaymış olabilir
            v = deger_bul(sayilar(satirlar[i + 1]))
        sol = s[:mi.start()].strip()
        kod = None
        mk = re.match(r"([A-ZÇĞİÖŞÜ0-9]{3,6})(?:\.E)?\b", sol)
        if mk: kod = mk.group(1)
        elif re.match(r"^[A-ZÇĞİÖŞÜ0-9]{3,6}(\.E)?$", onceki.strip()): kod = onceki.strip().replace(".E", "")
        ad = re.sub(r"^[A-ZÇĞİÖŞÜ0-9]{3,6}(?:\.E)?\s+", "", sol)[:80]
        tur = bolum or ("hisse" if (isin[:3] in ("TRA", "TRE") or (kod and ".E" in sol)) else "diger")
        
        k = kalemler.setdefault(isin, {"isin": isin, "kod": kod, "ad": ad, "tur": tur, "deger": 0.0, "satir": 0})
        if v is not None: k["deger"] += v
        k["satir"] += 1
        if not k["kod"] and kod: k["kod"] = kod
        onceki = s
    L = sorted(kalemler.values(), key=lambda x: -x["deger"])
    hisseler = [x for x in L if x["tur"] == "hisse"]
    hs = sum(x["deger"] for x in hisseler)
    if fon_toplam:
        for x in L: x["agirlik"] = round(100 * x["deger"] / fon_toplam, 4)
    for x in L: x["deger"] = round(x["deger"], 2)
    dog = {"hisse_satir_toplami": round(hs, 2), "hisse_grup_toplami": hisse_grup,
           "fark_yuzde": round(100 * (hs - hisse_grup) / hisse_grup, 4) if hisse_grup else None}
    dog["tutuyor"] = bool(hisse_grup and abs(dog["fark_yuzde"]) <= 0.2)
    return {"fon_toplam_deger": fon_toplam, "hisse_sayisi": len(hisseler),
            "hisse_agirligi": round(100 * hs / fon_toplam, 4) if fon_toplam else None,
            "dogrulama": dog, "hisseler": hisseler, "diger_kalemler": [x for x in L if x["tur"] != "hisse"]}

if __name__ == "__main__":
    print(json.dumps(ayristir(open(sys.argv[1], encoding="utf-8").read()), ensure_ascii=False, indent=1))
