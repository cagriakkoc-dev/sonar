"""KAP'tan fonların aylık Portföy Dağılım Raporlarını (PDR) çeker ve ayrıştırır.
Ortam: FON_KOD (ör. MAC; virgülle birden çok), FON_LIMIT (son kaç rapor, varsayılan 2), FON_KAYNAK (PDF geçici klasörü)
Çıktı: veri/fon/pdr/<KOD>/<YYYY-MM>.json, veri/fon/son_kosu.json; ham pdftotext metni yalnız doğrulaması tutmayan raporlarda veri/fon/ham/<KOD>/
Fon bildirimleri: GET /tr/api/disclosure/filter/FILTERYFBF/<fonOid>/ALL/365 (fonOid: kap_fon_oid.json)"""
import os, re, json, time, subprocess, tempfile, urllib.request, datetime, sys, gzip
sys.path.insert(0, os.path.dirname(__file__))
from pdr_ayristir import ayristir

KOK = os.path.join(os.path.dirname(__file__), "..", "..")
VERI = os.path.join(KOK, "veri", "fon")
UA = {"User-Agent": "Mozilla/5.0 Sonar-Bekci", "Accept": "application/json, text/html, */*"}
OIDS = json.load(open(os.path.join(os.path.dirname(__file__), "kap_fon_oid.json")))
_LP = os.path.join(VERI, "liste.json")
LISTE = json.load(open(_LP)).get("fonlar", []) if os.path.exists(_LP) else []
OIDS.update({f["kod"]: f["oid"] for f in LISTE})
KAYNAK = os.environ.get("FON_KAYNAK") or tempfile.mkdtemp()
LIMIT = int(os.environ.get("FON_LIMIT") or 2)

def get(u, t=90):
    for k in range(4):
        try: return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read()
        except Exception as e:
            if k == 3: raise
            time.sleep(15 * (k + 1) if "429" in repr(e) else 4)

def pdr_listesi(oid):
    L = json.loads(get(f"https://www.kap.org.tr/tr/api/disclosure/filter/FILTERYFBF/{oid}/ALL/365"))
    out = []
    for x in L:
        b = x.get("disclosureBasic", x)
        if "Portföy Dağılım Raporu" not in (b.get("title") or ""): continue
        if b.get("year") and b.get("donem"): donem = f"{b['year']}-{int(b['donem']):02d}"
        else:
            g = datetime.datetime.strptime(b["publishDate"][:10], "%d.%m.%Y").replace(day=1) - datetime.timedelta(days=1)
            donem = g.strftime("%Y-%m")
        out.append({"id": b["disclosureIndex"], "donem": donem, "yayin": b["publishDate"], "ozet": b.get("summary")})
    # aynı dönemin düzeltmesi varsa en son yayımlananı al
    tek = {}
    for r in sorted(out, key=lambda r: r["id"]): tek[r["donem"]] = r
    return sorted(tek.values(), key=lambda r: r["donem"], reverse=True)

def pdf_metin(bid):
    html = get(f"https://www.kap.org.tr/tr/Bildirim/{bid}")
    oids = list(dict.fromkeys(x.decode() for x in re.findall(rb"file/download/([0-9a-f]{32})", html)))
    if not oids: raise RuntimeError("ek bulunamadı")
    metinler = []
    for oid in oids[:3]:
        b = get(f"https://www.kap.org.tr/tr/api/file/download/{oid}", 180)
        k = b.find(b"%PDF", 0, 400)  # KAP PDF'i Java byte[] içinde verebiliyor
        if k > 0: b = b[k:]
        if b[:4] != b"%PDF": continue
        p = os.path.join(KAYNAK, f"{bid}_{oid[:8]}.pdf")
        open(p, "wb").write(b)
        metinler.append(subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, text=True).stdout)
    if not metinler: raise RuntimeError("PDF eki yok")
    return "\n".join(metinler), oids

def main():
    kodlar = [k.strip().upper() for k in (os.environ.get("FON_KOD") or "MAC").split(",") if k.strip()]
    HSY = [f["kod"] for f in LISTE if f.get("hisse_yogun") and not f.get("serbest")]
    if kodlar == ["HSY"]: kodlar = HSY                      # tüm hisse yoğun (serbest olmayan) fonlar
    elif kodlar == ["PILOT"]: kodlar = (["MAC"] + [k for k in HSY if k != "MAC"])[:15]
    parca = os.environ.get("FON_PARCA")             # "i/n": paralel koşuda bu işin payı
    if parca:
        pi, pn = map(int, parca.split("/")); kodlar = kodlar[pi::pn]
    print("fon sayısı", len(kodlar), flush=True)
    sp = os.path.join(VERI, f"son_kosu_{pi}.json" if parca else "son_kosu.json")
    kosu = {"zaman": datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z", "basarili": [], "atlandi": [], "hata": []}
    for kod in kodlar:
        oid = OIDS.get(kod)
        if not oid: kosu["hata"].append({"kod": kod, "neden": "kap_fon_oid.json'da yok"}); continue
        try: L = pdr_listesi(oid)[:LIMIT]
        except Exception as e: kosu["hata"].append({"kod": kod, "neden": "liste: " + repr(e)[:200]}); continue
        print(kod, "PDR", [(r["donem"], r["id"]) for r in L])
        for r in L:
            hedef = os.path.join(VERI, "pdr", kod, f"{r['donem']}.json")
            if os.path.exists(hedef) and not os.environ.get("YENIDEN"):
                kosu["atlandi"].append({"kod": kod, "donem": r["donem"]}); continue
            try:
                metin, ekler = pdf_metin(r["id"])
                if len(metin.strip()) < 200: raise RuntimeError("metin yok (taranmış PDF)")
                a = ayristir(metin)
                if not a["dogrulama"]["tutuyor"] or os.environ.get("HAM"):  # ham metin yalnız tutmayan raporlarda saklanır (hata ayıklama)
                    os.makedirs(os.path.join(VERI, "ham", kod), exist_ok=True)
                    with gzip.open(os.path.join(VERI, "ham", kod, f"{r['donem']}.txt.gz"), "wt", encoding="utf-8") as g: g.write(metin)
                a.update({"kod": kod, "donem": r["donem"], "bildirim": r["id"], "yayin": r["yayin"], "ekler": ekler})
                os.makedirs(os.path.dirname(hedef), exist_ok=True)
                json.dump(a, open(hedef, "w"), ensure_ascii=False, indent=1)
                d = a["dogrulama"]
                ozet = {"kod": kod, "donem": r["donem"], "hisse": a["hisse_sayisi"], "tutuyor": d["tutuyor"], "fark_yuzde": d["fark_yuzde"]}
                (kosu["basarili"] if d["tutuyor"] else kosu["hata"]).append(ozet)
                print(ozet, flush=True)
            except Exception as e:
                kosu["hata"].append({"kod": kod, "donem": r["donem"], "neden": repr(e)[:200]}); print(kod, r["donem"], "hata", repr(e)[:200])
            time.sleep(1.5)
    os.makedirs(VERI, exist_ok=True)
    json.dump(kosu, open(sp, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
