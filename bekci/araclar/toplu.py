"""Tüm BIST'i Sonar'a ekleme · veri toplama (GitHub Actions: .github/workflows/toplu.yml) · 11 Kas 2026.
Liste: bekci/toplu/liste.json {T: {oid, ad, grp, kap}}. Her çalıştırmada süre bütçesi içinde sırayla:
  A) KAP FR listeleri: 25'erli oid grupları, yalnız FR sınıfı, 30 günlük pencereler (2023-01-01 → bugün) → bekci/toplu/fr/<T>.json
  B) dönem başına bildirim seçimi (konu "Finansal Rapor", en büyük bildirim no; dönem sonundan 7 aydan geç olan yalnız başka yoksa) → bekci/toplu/ids.json
  C) XBRL: seçilen bildirimlerin KAP sayfasından XBRL satırları → bekci/xbrl/<id>.json (xbrl_cek.rows)
  D) Fiyat: İş Yatırım HisseTekil (2022-12-01 → bugün, kapanış ve piyasa değeri) → bekci/toplu/fiyat/<T>.json
Durum: bekci/toplu/durum.json. Kaldığı yerden sürer; bitenler tekrar çekilmez."""
import os, sys, json, time, datetime, urllib.request, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__)); import xbrl_cek
B = os.path.join(os.path.dirname(__file__), "..", "toplu"); X = os.path.join(os.path.dirname(__file__), "..", "xbrl")
for d in ("fr", "fiyat", "kart", "logo"): os.makedirs(os.path.join(B, d), exist_ok=True)
BUTCE = float(os.environ.get("BUTCE_DK", "40")) * 60; T0 = time.time()
FAZ = os.environ.get("FAZ", "liste,veri").split(","); SH, NSH = int(os.environ.get("SHARD", "0")), int(os.environ.get("NSHARD", "1"))
kalan = lambda: BUTCE - (time.time() - T0)
UA = {"User-Agent": "Mozilla/5.0 Sonar-Bekci", "Accept": "application/json"}
L = json.load(open(os.path.join(B, "liste.json"), encoding="utf-8"))
EK = os.path.join(B, "eksik_oid.json")   # {T: {ad, grp, kap}}: oid'i kap_oid.json'da olmayan (bankalar vb.) → KAP şirket listesinden bulunur
if "liste" in FAZ and os.path.exists(EK):
    import re
    eks = json.load(open(EK, encoding="utf-8")); bul = {}
    for u in ("https://www.kap.org.tr/tr/bist-sirketler", "https://www.kap.org.tr/tr/sirketler/IGS"):
        try:
            h = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA["User-Agent"]}), timeout=60).read().decode("utf-8", "ignore").replace('\\"', '"')
            for t in eks:
                if t in bul: continue
                m = re.search(r'"(?:mkkMemberOid|memberOid|oid)"\s*:\s*"([0-9a-f]{32})"[^{}]{0,400}?"(?:stockCode|stockCodes)"\s*:\s*"[^"]*\b' + t + r'\b', h) or re.search(r'"(?:stockCode|stockCodes)"\s*:\s*"[^"]*\b' + t + r'\b[^{}]{0,400}?"(?:mkkMemberOid|memberOid|oid)"\s*:\s*"([0-9a-f]{32})"', h) or re.search(r'ozet/([0-9a-f]{32})[^<]{0,200}?>\s*' + t + r'\b', h)
                if m: bul[t] = m.group(1)
        except Exception as ex: print("oid sayfası", u, repr(ex)[:80])
    for t, o in bul.items(): L[t] = {"oid": o, **eks[t], "ek": 1}
    if bul: json.dump(L, open(os.path.join(B, "liste.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump({t: v for t, v in eks.items() if t not in bul}, open(EK, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("eksik oid bulunan", sorted(bul))
DP = os.path.join(B, "durum.json" if NSH == 1 or "liste" in os.environ.get("FAZ", "liste") else f"durum_{SH}.json"); D = json.load(open(DP)) if os.path.exists(DP) else {}
def kaydet(): D["zaman"] = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"; json.dump(D, open(DP, "w"), ensure_ascii=False, indent=1)
BUGUN = datetime.date.today()

# ---------- A) FR listeleri ----------
def kap(oids, a, b):
    body = {"fromDate": a, "toDate": b, "memberType": "IGS", "mkkMemberOidList": oids, "inactiveCompanies": "N", "bdkMemberOidList": [],
            "subjectList": [], "srcCategory": "", "index": "", "market": "", "isLate": "", "term": "", "ruleType": "", "period": "", "year": "", "disclosureClass": "FR"}
    req = urllib.request.Request("https://www.kap.org.tr/tr/api/disclosure/members/byCriteria", json.dumps(body).encode(), {**UA, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
TS = sorted(L)
if "liste" in FAZ:
    W = []; a = datetime.date(2023, 1, 1)
    while a <= BUGUN: e = min(a + datetime.timedelta(days=29), BUGUN); W.append((a.isoformat(), e.isoformat())); a = e + datetime.timedelta(days=1)
    T1 = sorted(t for t in L if not L[t].get("ek")); T2 = sorted(t for t in L if L[t].get("ek"))   # ilk 430 şirketin grup sırası değişmesin
    GR = [T1[i:i + 25] for i in range(0, len(T1), 25)] + [T2[i:i + 25] for i in range(0, len(T2), 25)]
    fr_bitti = D.setdefault("fr_bitti", {})   # "grup no" -> son pencere
    for gi, g in enumerate(GR):
        if kalan() < 120: break
        oid2t = {L[t]["oid"]: t for t in g}; son = fr_bitti.get(str(gi))
        ws = [w for w in W if son is None or w[0] > son]
        if not ws or (son and son >= W[-1][0] and son == W[-1][0]): continue
        acc = {t: (json.load(open(os.path.join(B, "fr", f"{t}.json"))) if os.path.exists(os.path.join(B, "fr", f"{t}.json")) else []) for t in g}
        for w in ws:
            if kalan() < 90: break
            for k in range(9):
                try: R = kap(list(oid2t), *w); break
                except Exception as ex:
                    print("FR", gi, w, repr(ex)[:100]); time.sleep(20 * (k + 1) if "429" in repr(ex) else 5); R = None
            if R is None: break
            for x in R:
                if x.get("disclosureClass") != "FR": continue
                for t in (x.get("stockCodes") or "").replace(" ", "").split(","):
                    if t in acc: acc[t].append({k_: x.get(k_) for k_ in ("disclosureIndex", "publishDate", "subject", "summary", "year", "period", "ruleType")})
            fr_bitti[str(gi)] = w[0]; time.sleep(2.0)
        for t, v in acc.items():
            v = list({x["disclosureIndex"]: x for x in v}.values())
            json.dump(v, open(os.path.join(B, "fr", f"{t}.json"), "w"), ensure_ascii=False)
        print("FR grup", gi, "→", fr_bitti.get(str(gi))); kaydet()
    # 2021–2022 dönemleri (14 Kas 2026): geçmiş pencereler ayrı izlenir, aynı fr/<T>.json'a eklenir
    W2 = []; a = datetime.date(2021, 1, 1)
    while a < datetime.date(2023, 1, 1): e = min(a + datetime.timedelta(days=29), datetime.date(2022, 12, 31)); W2.append((a.isoformat(), e.isoformat())); a = e + datetime.timedelta(days=1)
    fr_g = D.setdefault("fr_gecmis", {})
    for gi, g in enumerate(GR):
        if kalan() < 120: break
        son = fr_g.get(str(gi)); ws = [w for w in W2 if son is None or w[0] > son]
        if not ws: continue
        oid2t = {L[t]["oid"]: t for t in g}
        acc = {t: (json.load(open(os.path.join(B, "fr", f"{t}.json"))) if os.path.exists(os.path.join(B, "fr", f"{t}.json")) else []) for t in g}
        for w in ws:
            if kalan() < 90: break
            for k in range(9):
                try: R = kap(list(oid2t), *w); break
                except Exception as ex:
                    print("FR2", gi, w, repr(ex)[:100]); time.sleep(20 * (k + 1) if "429" in repr(ex) else 5); R = None
            if R is None: break
            for x in R:
                if x.get("disclosureClass") != "FR": continue
                for t in (x.get("stockCodes") or "").replace(" ", "").split(","):
                    if t in acc: acc[t].append({k_: x.get(k_) for k_ in ("disclosureIndex", "publishDate", "subject", "summary", "year", "period", "ruleType")})
            fr_g[str(gi)] = w[0]; time.sleep(2.0)
        for t, v in acc.items():
            v = list({x["disclosureIndex"]: x for x in v}.values())
            json.dump(v, open(os.path.join(B, "fr", f"{t}.json"), "w"), ensure_ascii=False)
        print("FR2 grup", gi, "→", fr_g.get(str(gi))); kaydet()
    D["fr_gecmis_tamam"] = all(fr_g.get(str(gi)) == W2[-1][0] for gi in range(len(GR)))
    fr_tamam = all(fr_bitti.get(str(gi)) == W[-1][0] for gi in range(len(GR)))
    D["fr_tamam"] = fr_tamam

    # ---------- B) dönem seçimi ----------
    PER = {"3 Aylık": "03", "6 Aylık": "06", "9 Aylık": "09", "Yıllık": "12"}
    def secim(v):
        c = {}
        for x in v:
            if not str(x.get("subject") or "").startswith("Finansal Rapor"): continue
            p = PER.get(x.get("ruleType")); y = x.get("year")
            if not p or not y: continue
            key = f"{y}-{p}"
            if key < "2021-03": continue
            try: pub = datetime.datetime.strptime(x["publishDate"], "%d.%m.%Y %H:%M:%S").date()
            except Exception: continue
            ps = datetime.date(int(y), int(p), 28); gec = (pub - ps).days > 215
            c.setdefault(key, []).append((gec, -x["disclosureIndex"], x["disclosureIndex"]))
        return {k: sorted(v)[0][2] for k, v in sorted(c.items())}
    IDS = {}
    for t in TS:
        f = os.path.join(B, "fr", f"{t}.json")
        if os.path.exists(f): IDS[t] = secim(json.load(open(f)))
    json.dump(IDS, open(os.path.join(B, "ids.json"), "w"), ensure_ascii=False, indent=0)


IDS = json.load(open(os.path.join(B, "ids.json"))) if os.path.exists(os.path.join(B, "ids.json")) else {}
if "veri" not in FAZ: kaydet(); sys.exit(0)
TSH = [t for i, t in enumerate(TS) if i % NSH == SH]
# ---------- D) fiyat ----------
def fiyat(t):
    u = f"https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/HisseTekil?hisse={t}&startdate=01-12-2022&enddate={BUGUN:%d-%m-%Y}"
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 Sonar"}), timeout=60).read())
        v = [[x["HGDG_TARIH"], x.get("HGDG_KAPANIS"), x.get("PD")] for x in d.get("value", []) if x.get("HGDG_KAPANIS")]
        if not v: return t, "boş"
        json.dump(v, open(os.path.join(B, "fiyat", f"{t}.json"), "w")); return t, None
    except Exception as ex: return t, repr(ex)[:80]
fy = [t for t in TSH if not os.path.exists(os.path.join(B, "fiyat", f"{t}.json"))]
with cf.ThreadPoolExecutor(4) as ex:
    for k in range(0, len(fy), 8):
        if kalan() < BUTCE * 0.6: break
        for t, h in ex.map(fiyat, fy[k:k + 8]):
            if h: print("fiyat", t, h)
# 2021–2022 fiyatları (14 Kas 2026): fiyat_eski/<T>.json (yeni halka arzlarda boş → .yok)
os.makedirs(os.path.join(B, "fiyat_eski"), exist_ok=True)
def fiyat_eski(t):
    u = f"https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/HisseTekil?hisse={t}&startdate=01-01-2021&enddate=30-11-2022"
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 Sonar"}), timeout=60).read())
        v = [[x["HGDG_TARIH"], x.get("HGDG_KAPANIS"), x.get("PD")] for x in d.get("value", []) if x.get("HGDG_KAPANIS")]
        if not v: open(os.path.join(B, "fiyat_eski", f"{t}.yok"), "w").close(); return t, "boş"
        json.dump(v, open(os.path.join(B, "fiyat_eski", f"{t}.json"), "w")); return t, None
    except Exception as ex: return t, repr(ex)[:80]
fy2 = [t for t in TSH if not any(os.path.exists(os.path.join(B, "fiyat_eski", f"{t}.{e}")) for e in ("json", "yok"))]
with cf.ThreadPoolExecutor(4) as ex:
    for k in range(0, len(fy2), 8):
        if kalan() < BUTCE * 0.6: break
        for t, h in ex.map(fiyat_eski, fy2[k:k + 8]):
            if h and h != "boş": print("fiyat_eski", t, h)
import re
def kart(t):
    try:
        h = urllib.request.urlopen(urllib.request.Request("https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sirket-karti.aspx?hisse=" + t, headers={"User-Agent": "Mozilla/5.0 Sonar"}), timeout=60).read().decode("utf-8", "ignore")
        tb = [x for x in re.findall(r"<table.*?</table>", h, re.S) if re.search(r"Dağıtma|Temettü Verimi|Brüt", x)]
        open(os.path.join(B, "kart", f"{t}.html"), "w", encoding="utf-8").write("\n".join(tb) or "<!-- tablo yok -->"); return t, None
    except Exception as ex: return t, repr(ex)[:80]
def logo(t):   # KAP üye logosu (BIST 100 eklemesinde kullanılan adres)
    try:
        b = urllib.request.urlopen(urllib.request.Request(f"https://www.kap.org.tr/tr/api/member/logo/{L[t]['oid']}", headers={"User-Agent": UA["User-Agent"]}), timeout=60).read()
        if len(b) < 200: open(os.path.join(B, "logo", f"{t}.yok"), "w").write(""); return t, "logo yok"
        ext = "svg" if b"<svg" in b[:400] else "png" if b[:4] == b"\x89PNG" else "jpg" if b[:2] == b"\xff\xd8" else "bin"
        if ext == "bin": open(os.path.join(B, "logo", f"{t}.yok"), "w").write(""); return t, "logo biçimi tanınmadı"
        open(os.path.join(B, "logo", f"{t}.{ext}"), "wb").write(b); return t, None
    except Exception as ex: return t, repr(ex)[:80]
for fn, d_, ext in ((kart, "kart", ("html",)), (logo, "logo", ("png", "svg", "jpg", "yok"))):
    yap = [t for t in TSH if not any(os.path.exists(os.path.join(B, d_, f"{t}.{e}")) for e in ext)]
    with cf.ThreadPoolExecutor(4) as ex:
        for k in range(0, len(yap), 8):
            if kalan() < BUTCE * 0.55: break   # XBRL'e süre kalsın
            for t, h in ex.map(fn, yap[k:k + 8]):
                if h: print(d_, t, h)
# ---------- C) XBRL ----------
hata = D.setdefault("xbrl_hata", {})
gerek = [i for t in TSH for i in (IDS.get(t) or {}).values() if not os.path.exists(os.path.join(X, f"{i}.json")) and hata.get(str(i), 0) < 3]
def cek(i, k=0):
    try:
        raw = urllib.request.urlopen(urllib.request.Request(f"https://www.kap.org.tr/tr/Bildirim/{i}", headers={"User-Agent": UA["User-Agent"]}), timeout=90).read().decode("utf-8", "ignore")
        r = xbrl_cek.rows(raw)
        if not r: return i, "satır yok"
        json.dump({"id": int(i), "rows": r}, open(os.path.join(X, f"{i}.json"), "w"), ensure_ascii=False); return i, None
    except Exception as ex:
        if k < 2 and any(c in repr(ex) for c in ("429", "503", "502", "timed out", "Timeout")): time.sleep(25 * (k + 1)); return cek(i, k + 1)
        return i, repr(ex)[:80]
n_ok = 0
with cf.ThreadPoolExecutor(3) as ex:
    for k in range(0, len(gerek), 9):
        if kalan() < 150: break
        for i, h in ex.map(cek, gerek[k:k + 9]):
            if h: hata[str(i)] = hata.get(str(i), 0) + 1; D.setdefault("son_hata", []).append(h); D["son_hata"] = D["son_hata"][-15:]; print("XBRL", i, h)
            else: n_ok += 1
        time.sleep(1.0)
print("XBRL indirilen", n_ok, "kalan", len(gerek) - n_ok); D["xbrl_kalan"] = len(gerek) - n_ok; kaydet()

# ---------- F) Faaliyet raporu sayfaları (14 Kas 2026; "nasıl izlenir" verileri) ----------
# Son 5 dönemin faaliyet raporu PDF'inden anahtar kelime geçen sayfaların metni → bekci/toplu/fa/<T>/<dönem>.json
import re, subprocess, tempfile
FAK = re.compile(r"kapasite|kurulu g[üu]ç|\bMW\b|GWh|mağaza|sipariş|backlog|\bton\b|tonaj|sermaye yeterlili|takipteki|satış hacmi|satış miktar|üretim miktar|hasta|yönetilen portföy|komisyon|doluluk|ihracat|abone|yolcu|ünite|adet", re.I)
PERF = {"3 Aylık": "03", "6 Aylık": "06", "9 Aylık": "09", "Yıllık": "12"}
fah = D.setdefault("fa_hata", {})
def fa_liste(t):
    f = os.path.join(B, "fr", f"{t}.json")
    if not os.path.exists(f): return []
    c = {}
    for x in json.load(open(f)):
        if "Faaliyet Raporu" not in str(x.get("subject") or ""): continue
        p = PERF.get(x.get("ruleType")); y = x.get("year")
        if not p or not y: continue
        k = f"{y}-{p}"
        if k >= "2025-09": c[k] = max(c.get(k, 0), x["disclosureIndex"])
    return [(t, k, i) for k, i in sorted(c.items())]
def fa_cek(a):
    t, p, i = a; o = os.path.join(B, "fa", t, f"{p}.json")
    try:
        h = urllib.request.urlopen(urllib.request.Request(f"https://www.kap.org.tr/tr/Bildirim/{i}", headers={"User-Agent": UA["User-Agent"]}), timeout=90).read()
        oids = list(dict.fromkeys(x.decode() for x in re.findall(rb"file/download/([0-9a-f]{32})", h)))[:2]
        out = {"id": i, "ekler": []}
        for oid in oids:
            b = urllib.request.urlopen(urllib.request.Request(f"https://www.kap.org.tr/tr/api/file/download/{oid}", headers={"User-Agent": UA["User-Agent"]}), timeout=180).read()
            k = b.find(b"%PDF", 0, 400)
            if k > 0: b = b[k:]
            if b[:4] != b"%PDF": continue
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tf:
                tf.write(b); tf.flush()
                txt = subprocess.run(["pdftotext", "-layout", tf.name, "-"], capture_output=True, text=True, timeout=120).stdout
            pg = txt.split("\f"); hit = {str(n + 1): x for n, x in enumerate(pg) if FAK.search(x)}
            out["ekler"].append({"oid": oid, "sayfa_sayisi": len(pg), "sayfalar": dict(list(hit.items())[:40])})
        os.makedirs(os.path.dirname(o), exist_ok=True); json.dump(out, open(o, "w"), ensure_ascii=False); return a, None
    except Exception as ex: return a, repr(ex)[:80]
fa_gerek = [a for t in TSH for a in fa_liste(t) if not os.path.exists(os.path.join(B, "fa", a[0], f"{a[1]}.json")) and fah.get(str(a[2]), 0) < 3]
n_fa = 0
with cf.ThreadPoolExecutor(2) as ex:
    for k in range(0, len(fa_gerek), 4):
        if kalan() < 200: break
        for a, h in ex.map(fa_cek, fa_gerek[k:k + 4]):
            if h: fah[str(a[2])] = fah.get(str(a[2]), 0) + 1; print("FA", a, h)
            else: n_fa += 1
        time.sleep(1.5)
D["fa_kalan"] = len(fa_gerek) - n_fa; print("FA indirilen", n_fa, "kalan", D["fa_kalan"])

D["fiyat_kalan"] = len([t for t in TS if not os.path.exists(os.path.join(B, "fiyat", f"{t}.json"))])
D["sirket"] = len(TS); D["ids_dolu"] = sum(1 for t in TS if IDS.get(t))
kaydet(); print(json.dumps({k: v for k, v in D.items() if k not in ("xbrl_hata", "fr_bitti")}, ensure_ascii=False))
