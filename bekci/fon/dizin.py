"""Fon dizini: son PDR'lerden site verisi.
Çıktı: veri/fon/fonlar.json ve public/veri/fon/fonlar.json (sitenin okuduğu kopya)
  fonlar[]: kod, ad, kurucu, donem, toplam (TL), hisse_ag (%), n, getiri, h: [[hisse, ağırlık %, değer TL]], degisim, alis, satis, bildirim
  hisse{}: hisse kodu -> [[fon kodu, ağırlık %, dönem]] (şirket sayfasındaki "Bu hisseyi tutan fonlar")"""
import os, json, glob, datetime

KOK = os.path.join(os.path.dirname(__file__), "..", "..")
VERI = os.path.join(KOK, "veri", "fon")
GDIR = os.path.join(KOK, "public", "veri", "fon", "gecmis")

def main():
    liste = {f["kod"]: f for f in (json.load(open(os.path.join(VERI, "liste.json"))).get("fonlar", []) if os.path.exists(os.path.join(VERI, "liste.json")) else [])}
    F, H = [], {}
    GEC = {}
    for d in sorted(glob.glob(os.path.join(VERI, "pdr", "*"))):
        P = [json.load(open(p)) for p in sorted(glob.glob(os.path.join(d, "*.json")))]
        P = [a for a in P if a.get("dogrulama", {}).get("tutuyor")]   # yalnız doğrulaması tutan raporlar
        if P: GEC[os.path.basename(d)] = P
    KODLAR = {x["kod"] for P in GEC.values() for a in P for x in a["hisseler"] if x.get("kod")}
    for kod, P in GEC.items():
        son = P[-1]; onc = P[-2] if len(P) > 1 else None
        ag = lambda a: {x["kod"] or x["isin"]: x.get("agirlik") or 0 for x in a["hisseler"]}
        A = ag(son); deg = None
        if onc:
            B = ag(onc)
            fark = sorted(((k, round(A.get(k, 0) - B.get(k, 0), 2)) for k in set(A) | set(B)), key=lambda x: -abs(x[1]))
            deg = {"onceki": onc["donem"], "eklenen": sorted(set(A) - set(B)), "cikan": sorted(set(B) - set(A)),
                   "artan": [list(x) for x in fark if x[1] > 0 and x[0] in B][:5], "azalan": [list(x) for x in fark if x[1] < 0 and x[0] in A][:5]}
        # aylara göre dağılım: tüm geçerli aylar, tüm hisseler (fon sayfası ayrı dosyadan okur; yakınlaştırma istemcide)
        AG = [ag(a) for a in P]; tum = sorted({k_ for d in AG for k_ in d}, key=lambda k_: -max(d.get(k_, 0) for d in AG))
        G = {"kod": kod, "ay": [a["donem"] for a in P], "h": {k_: [round(d.get(k_, 0), 2) for d in AG] for k_ in tum if max(d.get(k_, 0) for d in AG) >= 0.05},
             "disi": [round(max(0, 100 - (a.get("hisse_agirligi") or 0)), 2) for a in P]}
        os.makedirs(GDIR, exist_ok=True); json.dump(G, open(os.path.join(GDIR, kod + ".json"), "w"), ensure_ascii=False, separators=(",", ":"))
        L = liste.get(kod, {})
        isl = son.get("islemler") or {}
        F.append({"kod": kod, "ad": L.get("ad") or kod, "kurucu": L.get("kurucu", ""), "donem": son["donem"], "toplam": son.get("fon_toplam_deger"),
                  "hisse_ag": son.get("hisse_agirligi"), "n": son.get("hisse_sayisi"), "getiri": L.get("getiri"), "bildirim": son.get("bildirim"),
                  "h": [[x["kod"] or x["isin"], x.get("agirlik"), x["deger"]] for x in son["hisseler"]], "degisim": deg,
                  "alis": [x[:2] for x in (isl.get("alis") or []) if x[0] in KODLAR][:10], "satis": [x[:2] for x in (isl.get("satis") or []) if x[0] in KODLAR][:10], "ay_sayisi": len(P)})
        for x in son["hisseler"]:
            if x.get("kod"): H.setdefault(x["kod"], []).append([kod, x.get("agirlik"), son["donem"]])
    for k in H: H[k].sort(key=lambda r: -(r[1] or 0))
    out = {"guncel": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z", "fonlar": sorted(F, key=lambda f: -(f["toplam"] or 0)), "hisse": H}
    for p in (os.path.join(VERI, "fonlar.json"), os.path.join(KOK, "public", "veri", "fon", "fonlar.json")):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(out, open(p, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"dizin: {len(F)} fon, {len(H)} hisse; veri yok: {sorted(set(os.path.basename(d) for d in glob.glob(os.path.join(VERI, 'pdr', '*'))) - set(GEC))}")

if __name__ == "__main__":
    main()
