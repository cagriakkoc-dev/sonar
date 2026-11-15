"""Kıymetli maden fonlarının Portföy Dağılım Raporu: varlık kalemlerine göre dağılım (grup toplamlarından).
Kullanım: python3 km_ayristir.py rapor.txt -> JSON
- Fon portföy değeri tablosundaki her alt grubun "GRUP TOPLAMI" satırı (en büyük sayı = TL değer) bir kalemdir; üst grup toplamları ve tekrarlanan satırlar atlanır.
- Grup başlığı (ör. "D.Maden Yabancı", "Borsa Y.Fonu Türk", "Kamu Kesimi Kira Sertifikaları") ve grup satırlarındaki işaretler (XAU, AU1, GÜMÜŞ, GLD, SLV…) kalemin türünü ve madenini belirler.
- Doğrulama: kalemler toplamı fon portföy değeriyle ±%1 tutmalı. Ağırlık = değer ÷ fon toplam değeri."""
import re, sys, json
sys.path.insert(0, __import__("os").path.dirname(__file__))
from pdr_ayristir import bicim, sayilar, ust

ALTIN = re.compile(r"XAU|\bAU\d*\b|ALTIN|GOLD|\bGLD|\bIAU\b|ZGOLD|GLDTR|\bKAU\b|ISGLK|AU995|AU999|\bALT\b|ALTINS?\d|ALTIN\.S", re.I)
GUMUS = re.compile(r"XAG|G[ÜU]M[ÜU][SŞ]|SILVER|\bSLV\b|GMSTR|ZSLVR|SVUSA|MAG9999|\bAG\d*\b", re.I)
PLATIN = re.compile(r"PLAT[İI]N|PLATINUM|XPT|PPLT|PALADYUM|PALLADIUM|XPD", re.I)
BASLIK_DISI = re.compile(r"MENKUL|KIYMET\s*$|D[ÖO]V[İI]Z\s+[İI]HRA|C[İI]NS[İI]|TAR[İI]H|FİYAT|ORANI|GÜN\s*$|TOPLAM|SAYISI|NOM[İI]NAL|PORTF[ÖO]Y DE|AYLIK|FONU?\s*$|A\.?Ş\.?$|YÖNET", re.I)

def tur_bul(b, satir):
    B = ust(b)
    if re.search(r"MADEN|K[İI]YMETL[İI]", B): return "maden"
    if re.search(r"BORSA\s*Y|BYF|\bETF", B): return "byf"
    if re.search(r"K[İI]RA\s*SERT", B): return "kira"
    if re.search(r"TAHV|BONO|D[İI]BS|BORÇLANMA|DEVLET|HAZ[İI]NE|KAMU", B): return "tahvil"
    if re.search(r"Y\.?\s*FON|YATIRIM\s*FON|FON\s*SEP|KATILIM\s*FON|\bFON", B): return "fon"
    if re.search(r"REPO|\bTPP\b|PARA\s*P[İI]YASA", B): return "repo"
    if re.search(r"MEVDUAT|KATILIM\s*HESAB", B): return "mevduat"
    if re.search(r"V[İI]OP|TEM[İI]NAT", B): return "viop"
    if re.search(r"D[ÖO]V[İI]Z", B): return "doviz"
    if re.search(r"H[İI]SSE|\bPAY\b", B): return "hisse"
    if re.search(r"G[İI]R[İI]Ş[İI]M", B): return "fon"
    return "diger"

AD = {"maden": "Fiziki {ml}", "byf": "{m} BYF", "fon": "{m} fonları", "kira": "{m}a dayalı kira sertifikası", "tahvil": "{m} tahvili", "doviz": "Fiziki {ml}"}
AD0 = {"maden": "Kıymetli maden", "byf": "Borsa yatırım fonları", "fon": "Fon payları", "kira": "Kira sertifikası", "tahvil": "Devlet tahvili / bono", "repo": "Repo / Takasbank para piyasası",
       "mevduat": "Mevduat / katılım hesabı", "viop": "VİOP teminatı", "doviz": "Döviz", "hisse": "Hisse senedi", "diger": "Diğer"}

def ayristir_km(metin):
    f = bicim(metin); L = metin.splitlines()
    fon_toplam = portfoy = None
    for s in L:
        u = ust(s); big = [v for h, v in sayilar(s, f) if "%" not in h and v > 1000]
        if not big: continue
        if re.search(r"FON TOPLAM DE[ĞG]ER", u) and fon_toplam is None: fon_toplam = max(big)
        elif fon_toplam is None and re.search(r"NET VARLIK DE[ĞG]ER|TOPLAM DE[ĞG]ER", u) and ":" in s: fon_toplam = big[-1]
        if re.search(r"FON PORTF[ÖO]Y DE[ĞG]ER", u) and portfoy is None: portfoy = max(big)
    bas = next((i for i, s in enumerate(L) if re.search(r"FON PORTF[ÖO]Y DE[ĞG]ER", ust(s))), 0)
    kalem, baslik, grup, onceki_top, son_deger = [], "", [], False, None
    for s in L[bas + 1:]:
        u = ust(s); t = s.strip()
        if not t: continue
        if re.search(r"FON TOPLAM DE[ĞG]ER[İI]? TABLOSU|^\s*[A-Z]-?\)?\s*FON PORTF[ÖO]Y DE[ĞG]ER", u) or re.match(r"^\s*FON PORTF[ÖO]Y DE[ĞG]ER", u): break
        if "GRUP TOPLAM" in u:
            n = [v for h, v in sayilar(s, f) if "%" not in h]
            v = max(n) if n else 0
            if not onceki_top and v > 0:
                metin_g = " ".join(grup)
                tr = tur_bul(baslik, metin_g)
                # satır bazında maden (grupta birden çok maden varsa değer satırlara bölünür)
                pay = {}
                for g in grup:
                    mg = "Altın" if ALTIN.search(g) else "Gümüş" if GUMUS.search(g) else "Platin" if PLATIN.search(g) else None
                    dv = [x for h, x in sayilar(g, f) if "%" not in h and re.search(r"[.,]\d{2}$", h) and x <= v * 1.001]
                    if dv: pay[mg] = pay.get(mg, 0) + max(dv)
                    elif mg and mg not in pay: pay[mg] = 0
                mlar = [k_ for k_ in pay if k_]
                if not mlar:
                    m = "Altın" if ALTIN.search(metin_g + " " + baslik) else "Gümüş" if GUMUS.search(metin_g + " " + baslik) else "Platin" if PLATIN.search(metin_g + " " + baslik) else None
                    parcalar = [(m, v)]
                elif len(mlar) == 1 or sum(pay.values()) <= 0: parcalar = [(mlar[0], v)]
                else:
                    tp = sum(pay.values()); parcalar = [(k_, v * x / tp) for k_, x in pay.items() if x > 0]
                for m, vv in parcalar:
                    t_ = tr
                    if m and t_ in ("hisse", "diger"): t_ = "byf" if re.search(r"ETF|\bSW\b|\bUS\b|\bCN\b|\bLN\b|TRUST", metin_g) else "maden"
                    if t_ == "doviz" and not m: ad = AD0["doviz"]
                    elif m and t_ in AD: ad = AD[t_].format(m=m, ml=m.lower()).replace("Gümüşa", "Gümüşe").replace("Platina", "Platine")
                    else: ad = AD0[t_]
                    kalem.append({"ad": ad, "tur": t_, "maden": m, "baslik": baslik, "deger": vv})
                son_deger = v
            elif onceki_top and son_deger and abs(v - son_deger) < 0.01: pass   # aynı toplamın tekrarı
            onceki_top = True; grup = []; continue
        n = sayilar(s, f)
        if not re.search(r"\d", t) and len(t) < 60 and not BASLIK_DISI.search(t) and not s.startswith(" " * 12) and not re.search(r"\S\s{3,}\S", t):
            baslik = t; onceki_top = False; grup = []; continue
        if n or re.search(r"[A-Z]{2,}", t):
            if n: onceki_top = False
            grup.append(t)
    # aynı adlı kalemleri birleştir
    birles = {}
    for x in kalem:
        y = birles.setdefault(x["ad"], {"ad": x["ad"], "tur": x["tur"], "maden": x["maden"], "deger": 0.0}); y["deger"] += x["deger"]
    K = sorted(birles.values(), key=lambda x: -x["deger"]); ks = sum(x["deger"] for x in K)
    fark = round(100 * (ks - portfoy) / portfoy, 4) if portfoy else None
    payda = fon_toplam or portfoy
    for x in K: x["agirlik"] = round(100 * x["deger"] / payda, 4) if payda else None; x["deger"] = round(x["deger"], 2)
    km = sum(x["deger"] for x in K if x["maden"])
    dag = {m: round(100 * sum(x["deger"] for x in K if x["maden"] == m) / payda, 2) for m in ("Altın", "Gümüş", "Platin")} if payda else {}
    return {"tur": "km", "fon_toplam_deger": fon_toplam, "fon_portfoy_degeri": portfoy, "kalemler": K, "km_agirligi": round(100 * km / payda, 4) if payda else None,
            "maden_dagilimi": dag, "hisse_sayisi": 0, "hisse_agirligi": None, "hisseler": [], "islemler": {"alis": [], "satis": []},
            "dogrulama": {"kalem_toplami": round(ks, 2), "portfoy_degeri": portfoy, "fark_yuzde": fark, "bicim": f, "tutuyor": bool(K and fark is not None and abs(fark) <= 1.0)}}

KM_AD = re.compile(r"\bALTIN\b(?!C)|ALTIN FON|ALTIN KATILIM|K[ÜU]LÇE ALTIN|G[ÜU]M[ÜU]Ş|K[İI]YMETL[İI] MADEN|PLAT[İI]N\b", re.I)
def kiymetli(ad): return bool(KM_AD.search(ad or "")) and not re.search(r"ALTINCI|ONALTINCI|YİRMİALTINCI|OTUZALTINCI|KIRKALTINCI", ad or "", re.I)

if __name__ == "__main__":
    print(json.dumps(ayristir_km(open(sys.argv[1], encoding="utf-8").read()), ensure_ascii=False, indent=1))
