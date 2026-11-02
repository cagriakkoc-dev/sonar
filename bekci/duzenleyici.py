"""SPK bültenleri, SPK basın duyuruları ve Borsa İstanbul duyuruları (Sonar · Haberler › SPK ve Borsa İstanbul).

bekci.py her çalışmada tara() çağırır:
- Kaynak sayfaları okunur, yeni kayıtlar bekci/duyurular.json'a eklenir (en yeni üstte, en çok 400 kayıt).
- Sonar'daki şirketler kayıt metninde (bülten PDF'i / duyuru sayfası) aranır → "kod" etiketi; bültende her
  şirket için geçtiği bölüm başlığı ("bol") da yazılır.
- Yeni kayıtlar Telegram mesajı olarak döner (bekci.py gönderir). İlk çalışmada mevcut liste sessizce alınır.
Site (index.html) duyurular.json'u raw.githubusercontent.com'dan okur; yayın gerekmez.
Elle deneme: python3 bekci/duzenleyici.py --kuru  (Telegram/kayıt yok, sonucu yazdırır)
"""
import datetime, html as H, io, json, os, re, sys, urllib.request

B = os.path.dirname(os.path.abspath(__file__))
DUY = os.path.join(B, "duyurular.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 Sonar-Bekci",
      "Accept-Language": "tr-TR,tr;q=0.9"}
AYLAR = [a.capitalize() for a in "ocak şubat mart nisan mayıs haziran temmuz ağustos eylül ekim kasım aralık".split()]
GENEL = re.compile(r"^(Basın (Duyurusu|Açıklaması)|Duyuru|Kamuoyuna Duyuru)$", re.I)
AY = {a: i + 1 for i, a in enumerate("ocak şubat mart nisan mayıs haziran temmuz ağustos eylül ekim kasım aralık".split())}
AY.update({a[:3]: i for a, i in list(AY.items())})
KAYNAK = {"spk-bulten": "SPK bülteni", "spk-basin": "SPK duyurusu", "bist": "Borsa İstanbul"}


def get(url, t=40):
    b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t).read()
    if b[:2] == b"\x1f\x8b":
        import gzip; b = gzip.decompress(b)
    return b


def metin(b):
    s = b.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def tarih(s):
    m = re.search(r"(\d{1,2})[ .](\w+)[ .](\d{4})", s or "")
    if not m: return None
    ay = AY.get(m.group(2).lower().replace("i̇", "i")) or AY.get(m.group(2).lower()[:3])
    return f"{m.group(3)}-{ay:02d}-{int(m.group(1)):02d}" if ay else None


# ---------- kaynaklar ----------
def spk_bulten(y):
    s = get(f"https://spk.gov.tr/spk-bultenleri/{y}-yili-spk-bultenleri").decode("utf-8", "replace")
    out = []
    for a in re.finditer(r'<a href="([^"]+\.pdf)"[^>]*>(.*?)</a>', s, re.S):
        t = metin(a.group(2).encode())
        m = re.search(r"Bülten No\s*:\s*(\d{4})/(\d+).*?Yayımlanma\s*:\s*(.+)$", t)
        if not m: continue
        out.append({"k": "spk-bulten", "id": f"spk-bulten-{m.group(1)}-{int(m.group(2)):03d}", "t": f"SPK Bülteni {m.group(1)}/{int(m.group(2))}",
                    "d": tarih(m.group(3)), "u": H.unescape(a.group(1))})
    return out


def spk_basin(y):
    s = get(f"https://spk.gov.tr/duyurular/basin-duyurulari/{y}").decode("utf-8", "replace")
    out = []
    for a in re.finditer(r'<a href="(/duyurular/basin-duyurulari/%d/[^"]+)"[^>]*>(.*?)</a>' % y, s, re.S):
        t = metin(a.group(2).encode())
        m = re.match(r"(\d{1,2} \w+ \d{4})\s*(?:Yeni\s+)?(.*)$", t)
        if not m: continue
        baslik = m.group(2).strip()
        bas = baslik if GENEL.match(baslik) else re.sub(r"^(Yeni )?Basın (Duyurusu|Açıklaması)\s+(?=\S)", "", baslik).strip()
        out.append({"k": "spk-basin", "id": "spk-basin-" + a.group(1).rsplit("/", 1)[1].lower(), "t": bas or baslik or "Basın duyurusu",
                    "d": tarih(m.group(1)), "u": "https://spk.gov.tr" + a.group(1)})
    return out


TR_HARF = re.compile(r"[çğıöşüÇĞÖŞÜ]")
EN = re.compile(r"\b(the|for|of|and|rang|bell|index|indices|announcement|opening)\b", re.I)


def bist():
    s = get("https://www.borsaistanbul.com/duyurular").decode("utf-8", "replace")
    out, gor = [], set()
    for a in re.finditer(r'<a [^>]*href="(?:https?://www\.borsaistanbul\.com)?(/duyuru/(\d+)/[^"]*)"[^>]*>(.*?)</a>', s, re.S):
        if a.group(2) in gor: continue
        t = metin(a.group(3).encode())
        m = re.match(r"(\d{1,2} \w+ \d{4})\s*(.+)$", t)
        if not m: continue
        baslik = m.group(2).strip()
        if not TR_HARF.search(baslik.replace("İstanbul", "")) and EN.search(baslik): continue  # İngilizce eşi
        gor.add(a.group(2))
        out.append({"k": "bist", "id": "bist-" + a.group(2), "t": baslik, "d": tarih(m.group(1)), "u": "https://www.borsaistanbul.com" + a.group(1)})
    return out


# ---------- şirket etiketleri ----------
EK = {"ISMEN": ["İş Yatırım Menkul"], "ISGYO": ["İş Gayrimenkul Yatırım"], "INFO": ["İnfo Yatırım Menkul"], "TERA": ["Tera Yatırım Menkul"],
      "GEDIK": ["Gedik Yatırım Menkul"], "OSMEN": ["Osmanlı Yatırım Menkul"], "OYYAT": ["OYAK Yatırım Menkul"], "GLBMD": ["Global Menkul Değerler"],
      "HALKB": ["Halk Bankası", "Halkbank"], "VAKBN": ["Vakıflar Bankası", "VakıfBank"], "ISCTR": ["Türkiye İş Bankası"], "YKBNK": ["Yapı ve Kredi Bankası", "Yapı Kredi Bankası"],
      "GARAN": ["Garanti Bankası", "Garanti BBVA"], "TSKB": ["Türkiye Sınai Kalkınma Bankası"], "ALBRK": ["Albaraka Türk"], "BIMAS": ["BİM Birleşik Mağazalar"],
      "SISE": ["Şişecam", "Türkiye Şişe ve Cam"], "EREGL": ["Ereğli Demir", "Erdemir"], "ISDMR": ["İskenderun Demir"], "TUPRS": ["Türkiye Petrol Rafinerileri", "Tüpraş"],
      "SAHOL": ["Hacı Ömer Sabancı"], "FROTO": ["Ford Otomotiv"], "TOASO": ["Tofaş Türk Otomobil"], "MGROS": ["Migros Ticaret"], "PGSUS": ["Pegasus Hava"],
      "TCELL": ["Turkcell İletişim"], "TTKOM": ["Türk Telekomünikasyon"], "THYAO": ["Türk Hava Yolları"], "ENKAI": ["Enka İnşaat"], "SOKM": ["Şok Marketler"],
      "ULKER": ["Ülker Bisküvi"], "AEFES": ["Anadolu Efes"], "CCOLA": ["Coca-Cola İçecek"], "TAVHL": ["TAV Havalimanları"], "ASELS": ["Aselsan"],
      "EKGYO": ["Emlak Konut Gayrimenkul"], "KCHOL": ["Koç Holding"], "AGESA": ["AgeSA Hayat"], "ANHYT": ["Anadolu Hayat Emeklilik"], "ANSGR": ["Anadolu Anonim Türk Sigorta", "Anadolu Sigorta"],
      "TURSG": ["Türkiye Sigorta"], "BINHO": ["1000 Yatırımlar Holding"], "A1CAP": ["A1 Capital Yatırım"]}
YALNIZ_EK = {"ISMEN", "ISGYO", "INFO", "TERA", "GEDIK", "OSMEN", "OYYAT", "GLBMD", "TSKB", "HALKB", "BIMAS", "A1CAP", "SAHOL"}


def up(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


def sirketler():
    p = os.path.join(B, "..", "public", "index.html")
    try:
        s = open(p, encoding="utf-8").read()
        D = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', s, re.S).group(1))
        L = [(c["t"], c.get("name") or "") for c in D["companies"]]
    except Exception as e:
        print("şirket listesi okunamadı:", repr(e)[:150]); L = []
    P = {}
    for t, ad in L:
        adlar = list(EK.get(t, [])) + ([] if t in YALNIZ_EK or len(ad) < 4 else [ad])
        rx = []
        for a in adlar:
            a = re.escape(up(a)).replace(r"\ ", r"\s+").replace("GYO", "(?:GYO|GAYRİMENKUL\\s+YATIRIM\\s+ORTAKLIĞI)")
            rx.append(a)
        rx.append(r"\(" + t + r"(?:\.E)?\)|\b" + t + r"\.E\b")  # (AKBNK) veya AKBNK.E
        P[t] = re.compile(r"(?<![A-ZÇĞİÖŞÜ0-9])(?:" + "|".join(rx) + r")(?![A-ZÇĞİÖŞÜ0-9])")
    return P


BASLIK = re.compile(r"^(?:[A-ZÇĞİÖŞÜ]|[IVX]+|\d{1,2}|[a-zçğıöşü])[.)]\s+\S.{2,90}$")


def etiketle(txt, P, bolum=False):
    """txt içinde geçen Sonar şirketleri → {kod: bölüm başlığı veya ''}"""
    if not txt: return {}
    U = up(txt)
    out = {}
    if not bolum:
        for t, rx in P.items():
            if rx.search(U): out[t] = ""
        return out
    satirlar = [x.strip() for x in txt.splitlines()]
    son = ["", ""]
    for x in satirlar:
        if not x: continue
        if BASLIK.match(x) and not re.search(r"\d{2}\.\d{2}\.\d{4}|TL|%", x):
            seviye = 0 if re.match(r"^([A-ZÇĞİÖŞÜ]|[IVX]+)[.)]", x) else 1
            h = re.sub(r"^\S+\s+", "", x).strip().rstrip(":")
            if re.search(r"Kurul Karar Organı.*Uyarınca", h): h = "Kurul kararıyla yapılan duyuru"
            if h == up(h): h = h.replace("I", "ı").replace("İ", "i").lower(); h = h[:1].upper() + h[1:]
            son[seviye] = h
            if seviye == 0: son[1] = ""
            continue
        ux = up(x)
        for t, rx in P.items():
            if t not in out and rx.search(ux):
                out[t] = (son[1] or son[0])[:90]
    return out


def pdf_metin(b):
    try:
        from pypdf import PdfReader
    except Exception:
        try:
            import subprocess, site, importlib
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--user", "pypdf"], timeout=120, check=False)
            importlib.invalidate_caches(); sys.path.append(site.getusersitepackages())
            from pypdf import PdfReader
        except Exception as e:
            print("pypdf yok:", repr(e)[:100]); return ""
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(b)).pages[:60])
    except Exception as e:
        print("pdf okunamadı:", repr(e)[:120]); return ""


def ayrinti(x, P):
    """Kaydın içeriğini indirip şirket etiketlerini çıkarır (hata olursa boş)."""
    try:
        if x["k"] == "spk-bulten":
            b = get(x["u"], 90)
            txt = pdf_metin(b)
            x["oku"] = bool(txt)
            e = etiketle(txt, P, bolum=True)
        else:
            s = metin(get(x["u"]))
            if x["k"] == "spk-basin" and x.get("d"):
                y_, m_, g_ = x["d"].split("-"); uz = f"{g_} {AYLAR[int(m_) - 1]} {y_}"
                i = s.rfind(uz); govde = s[i + len(uz):] if i >= 0 else ""
                if govde and GENEL.match(x["t"]):
                    c = re.split(r"(?<=[.!?])\s", govde.strip(), 1)[0]
                    x["t"] = x["t"] + ": " + (c[:140].rsplit(" ", 1)[0] + "…" if len(c) > 140 else c)
            else:
                i = s.rfind(x["t"][:40]); govde = s[i:] if i >= 0 else s
            e = etiketle(govde[:20000], P)
        if e:
            x["kod"] = sorted(e)
            bol = {t: v for t, v in e.items() if v}
            if bol: x["bol"] = bol
    except Exception as ex:
        print("ayrıntı alınamadı", x["id"], repr(ex)[:150])
    return x


def tara(kuru=False, sessiz=None):
    """Yeni kayıtları duyurular.json'a ekler; Telegram mesajlarını döndürür."""
    y = datetime.date.today().year
    eski = json.load(open(DUY, encoding="utf-8")) if os.path.exists(DUY) else []
    ids = {x["id"] for x in eski}
    ilk = not eski if sessiz is None else sessiz
    bulunan, hatalar = [], []
    for ad, f, args in (("SPK bülten", spk_bulten, (y,)), ("SPK basın", spk_basin, (y,)), ("BIST", bist, ())):
        try:
            r = f(*args)
            if not r and ad != "BIST" and datetime.date.today().month == 1: r = f(y - 1)
            print(ad, len(r), "kayıt")
            bulunan += r
        except Exception as e:
            hatalar.append(ad); print(ad, "hatası:", repr(e)[:200])
    yeni = [x for x in bulunan if x["id"] not in ids]
    if not yeni:
        return [], hatalar
    P = sirketler()
    if ilk:  # ilk kurulum: son 12 bülten ve son 15 duyurunun ayrıntısı, diğerleri yalnız başlık
        say = {}
        for x in yeni:
            say[x["k"]] = say.get(x["k"], 0) + 1
            if say[x["k"]] <= (12 if x["k"] == "spk-bulten" else 15): ayrinti(x, P)
    else:
        for x in yeni: ayrinti(x, P)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    for x in yeni: x["g"] = now
    tum = yeni + eski
    tum.sort(key=lambda x: (x.get("d") or "", x["id"]), reverse=True)
    if kuru:
        print(json.dumps(yeni[:40], ensure_ascii=False, indent=1)); return [], hatalar
    json.dump(tum[:400], open(DUY, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if ilk:
        return [f"SPK ve Borsa İstanbul duyuru takibi başladı: {len(yeni)} kayıt Sonar'a alındı. Yeni bülten ve duyurular buraya gelecek."], hatalar
    msj = []
    for x in sorted(yeni, key=lambda x: (x.get("d") or "", x["id"])):
        kod = x.get("kod") or []
        bol = x.get("bol") or {}
        ek = ""
        if kod:
            ek = "\nSonar şirketleri: " + ", ".join(t + (f" ({bol[t]})" if bol.get(t) else "") for t in kod[:12]) + (f" +{len(kod) - 12}" if len(kod) > 12 else "")
        msj.append(f"{KAYNAK[x['k']]} · {x['t']}\n{x.get('d') or ''}{ek}\n{x['u']}")
    return msj, hatalar


if __name__ == "__main__":
    m, h = tara(kuru="--kuru" in sys.argv, sessiz=("--sessiz" in sys.argv) or None)
    print("\n\n".join(m)); print("hata:", h)
