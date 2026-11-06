"""KAP Portföy Dağılım Raporu (SPK II-14.2) metninden hisse senetlerini çıkarır (biçimden bağımsız, v2).
Kullanım: python3 pdr_ayristir.py rapor.txt  ->  JSON (stdout)
- Hisse = BIST pay ISIN'i (TRA…/TRE…). Satır numaraları ISIN satırında yoksa (kaydırılmış satır) komşu satırdan alınır.
- Sayı biçimi (1.234,56 / 1,234.56) belge bazında saptanır.
- Değer sütunu: "TOPLAM" satırlarından, en büyük sayıdan sonra kaç yüzde sütunu geldiği bulunur (k); satırda değer = sondan (k+1). sayı.
- Doğrulama: hisse değerleri toplamı, belgedeki bir TOPLAM satırının en büyük sayısıyla ±%0,2 tutmalı.
- Ağırlık = değer ÷ fon toplam değeri (net varlık)."""
import re, sys, json
from collections import Counter

ISIN = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
TARIH = re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
TOK = re.compile(r"%?-?\d[\d.,]*%?")

def bicim(t):
    us = len(re.findall(r"\d{1,3}(?:,\d{3})+\.\d{2}\b", t)); tr = len(re.findall(r"\d{1,3}(?:\.\d{3})+,\d{2}\b", t))
    return "us" if us > tr else "tr"

def sayi(h, f):
    h = h.strip("%").strip(".,")
    if not h or not re.search(r"\d", h): return None
    if f == "us": h = h.replace(",", "")
    else: h = h.replace(".", "").replace(",", ".")
    try: return float(h)
    except ValueError: return None

def sayilar(s, f):
    s = ISIN.sub(" ", TARIH.sub(" ", s))
    out = []
    for m in TOK.finditer(s):
        v = sayi(m.group(), f)
        if v is not None: out.append((m.group(), v))
    return out

def ust(s): return s.replace("i", "İ").upper()

def islemler(metin):
    """VII- PORTFÖYDEN SATIŞLAR / IX- PORTFÖYE ALIŞLAR: satırları hisse koduna göre toplar (TL; satırdaki en büyük tutar).
    Kod süzgeci dizin.py'de (bilinen hisse kodları) yapılır."""
    f = bicim(metin); out, kisim = {"alis": {}, "satis": {}}, None
    for s in metin.splitlines():
        m = re.match(r"^\s*([IVX]+)\s*[-.)]+\s*(.+)", s)
        if m and len(s.strip()) < 90:
            b = ust(m.group(2))
            kisim = "satis" if "PORTF" in b and ("SATIŞ" in b or "SATIS" in b) else "alis" if "PORTF" in b and ("ALIŞ" in b or "ALIS" in b) else None
            continue
        if not kisim: continue
        mk = re.search(r"\b([A-ZÇĞİÖŞÜ0-9]{3,6})\.E\b", s) or re.match(r"^\s*(?:Pay\s+)?([A-Z0-9]{4,6})\s{2,}", s)
        if not mk: continue
        n = [v for h, v in sayilar(s[mk.end():], f) if "%" not in h]
        if not n: continue
        k = out[kisim].setdefault(mk.group(1), [0.0, 0]); k[0] += max(n); k[1] += 1
    return {t: sorted(([kod, round(v[0], 2), v[1]] for kod, v in d.items()), key=lambda x: -x[1]) for t, d in out.items()}

def hisse_isin(i): return i[:3] in ("TRA", "TRE")

def ayristir(metin):
    f = bicim(metin); L = metin.splitlines()
    N = [sayilar(s, f) for s in L]
    # toplam satırları ve yüzde sütunu sayısı
    top, ks = [], Counter()
    for s, n in zip(L, N):
        if re.match(r"^\s*(ANA\s+)?(GRUP\s+)?TOPLAM", ust(s)) and not ISIN.search(s) and n:
            vals = [v for h, v in n if "%" not in h]
            if not vals: continue
            i = max(range(len(vals)), key=lambda j: (abs(vals[j]), j))
            if abs(vals[i]) > 1000: top.append(abs(vals[i])); ks[len(vals) - 1 - i] += 1
        elif "TOPLAM" in ust(s) and not ISIN.search(s):
            vals = [v for h, v in n if "%" not in h and abs(v) > 1000]
            if vals: top.append(max(map(abs, vals)))
    k = ks.most_common(1)[0][0] if ks else 0
    NP = [[x for x in n if "%" not in x[0]] for n in N]   # yüzde işaretli sütunlar atılır
    # fon toplam değeri
    fon_toplam = portfoy = None
    for s, n in zip(L, N):
        u = ust(s); big = [v for h, v in n if "%" not in h and v > 1000]
        if not big: continue
        if re.search(r"FON TOPLAM DE[ĞG]ER", u): fon_toplam = max(big)
        elif fon_toplam is None and re.search(r"NET VARLIK DE[ĞG]ER|TOPLAM DE[ĞG]ER", u) and ":" in s: fon_toplam = big[-1]
        if re.match(r"^\s*(A[.\-)\s]+)?FON PORTF[ÖO]Y DE[ĞG]ER", u): portfoy = max(big)
    kalem = {}
    bas = [i for i, s in enumerate(L) if len(NP[i]) >= k + 2 and (re.match(r"^\s{0,3}\S", s) or ISIN.search(s)) and not re.match(r"^\s*(ANA\s+)?(GRUP\s+)?TOPLAM", ust(s))]
    for n_, i in enumerate(bas):
        son = bas[n_ + 1] if n_ + 1 < len(bas) else min(i + 12, len(L))
        isin = None
        for j in range(i, min(son, i + 12)):
            if j > i and re.match(r"^\s*(ANA\s+)?(GRUP\s+)?TOPLAM", ust(L[j])): break
            m = ISIN.search(L[j])
            if m: isin = m.group(1); break
        e = re.match(r"^\s{0,3}([A-ZÇĞİÖŞÜ0-9]{3,6})\.E\b", L[i])
        if not isin and e: isin = "KOD:" + e.group(1)       # MKK biçiminde ISIN'i boş bırakılmış pay satırı
        if not isin or not (hisse_isin(isin) or isin.startswith("KOD:")): continue
        v = NP[i][-(k + 1)][1]
        mk = re.match(r"^\s{0,3}([A-ZÇĞİÖŞÜ0-9]{3,6})(?:\.E)?\b", L[i])
        kod = mk.group(1) if mk and mk.group(1) not in ("TL", "USD", "EUR") else (re.sub(r"W$", "", isin[3:8]) if isin.startswith("TRA") else None)
        if isin.startswith("KOD:"):
            isin = next((x["isin"] for x in kalem.values() if x["kod"] == kod), None) or isin
        x = kalem.setdefault(isin, {"isin": None if isin.startswith("KOD:") else isin, "kod": kod, "deger": 0.0, "satir": 0})
        x["deger"] += v; x["satir"] += 1
    if not kalem:   # ISIN'siz biçim: hisse bölümündeki "KOD  AD  … değer" satırları
        bolum = False
        for i, s in enumerate(L):
            u = ust(s)
            if re.match(r"^\s*([A-ZÇ0-9]{1,3}[.)\-]+\s*)?(HİSSE|PAY)", u) and len(u.strip()) < 70 and not NP[i]: bolum = True; continue
            if bolum and re.match(r"^\s*(ANA\s+)?(GRUP\s+)?TOPLAM", u): break
            if not bolum: continue
            mk = re.match(r"^\s{0,8}([A-Z0-9]{4,6})(?:\.E)?\s{2,}", s)
            if mk and len(NP[i]) >= k + 2:
                x = kalem.setdefault(mk.group(1), {"isin": None, "kod": mk.group(1), "deger": 0.0, "satir": 0})
                x["deger"] += NP[i][-(k + 1)][1]; x["satir"] += 1
    H = sorted(kalem.values(), key=lambda x: -x["deger"])
    hs = sum(x["deger"] for x in H)
    eslesen = min(top, key=lambda t: abs(t - hs)) if top and hs else None
    fark = round(100 * (hs - eslesen) / eslesen, 4) if eslesen else None
    dog = {"hisse_satir_toplami": round(hs, 2), "hisse_grup_toplami": eslesen, "fark_yuzde": fark, "yuzde_sutun": k, "bicim": f,
           "tutuyor": bool(H and fark is not None and abs(fark) <= 0.2 and (not fon_toplam or hs <= fon_toplam * 1.05))}
    if fon_toplam:
        for x in H: x["agirlik"] = round(100 * x["deger"] / fon_toplam, 4)
    for x in H: x["deger"] = round(x["deger"], 2)
    return {"fon_toplam_deger": fon_toplam, "fon_portfoy_degeri": portfoy, "islemler": islemler(metin), "hisse_sayisi": len(H),
            "hisse_agirligi": round(100 * hs / fon_toplam, 4) if fon_toplam else None, "dogrulama": dog, "hisseler": H}

if __name__ == "__main__":
    print(json.dumps(ayristir(open(sys.argv[1], encoding="utf-8").read()), ensure_ascii=False, indent=1))
