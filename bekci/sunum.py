"""Şirket web sitelerinde yatırımcı sunumu takibi (deneme: TUPRS, ANHYT, AVPGY, FROTO, ISMEN, AKSA).

bekci.py her çalışmada tara() çağırır. Şirket başına sayfa en çok 6 saatte bir okunur; "aylik" şirketlerde
(sunumu her ayın başında yayımlayanlar) ayın 1–3'ünde 30 dakikada bir. Sayfadaki sunum bağlantıları önceki
listeyle karşılaştırılır; yeni bağlantı Telegram'a yazılır ve bekci/sunumlar.json'a eklenir (site şirket
sayfasında "Yatırımcı sunumu" kutusunda gösterir). İlk okumada mevcut liste sessizce alınır.
Yeni şirket: SITELER'e satır ekle (url, desen = bağlantı düzenli ifadesi). Elle deneme: python3 bekci/sunum.py --kuru
"""
import datetime, html as H, json, os, re, sys, urllib.parse, urllib.request

B = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(B, "sunumlar.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 Sonar-Bekci",
      "Accept-Language": "tr-TR,tr;q=0.9", "Accept": "text/html,application/json,*/*"}

SITELER = {
    "TUPRS": {"url": "https://www.tupras.com.tr/tr/yatirimci-iliskileri-sunumlar", "desen": r"/assets/uploads/yatirimci-iliskileri/sunum/[^\"'<>]+\.pdf",
              "aylik": True, "not": "Tüpraş yatırımcı sunumunu her ayın ilk günü şirket sitesinde yayımlar."},
    "ANHYT": {"url": "https://www.anadoluhayat.com.tr/yatirimci-iliskileri/yatirimci-sunumlari", "tip": "anhyt",
              "api": "https://www.anadoluhayat.com.tr/InvestorRelations/GetPresentationFiles"},
    "AVPGY": {"url": "https://www.avrupakentgyo.com/tr/yatirimci-iliskileri/raporlar-ve-sunumlar/yatirimci-sunumlari/", "desen": r"/PDF/[^\"'<>]+\.pdf"},
    "FROTO": {"url": "https://www.fordotosan.com.tr/tr/yatirimcilar/sunumlar/yatirimci-sunumlari", "desen": r"/doc/[A-Za-z0-9_\-]{20,}",
              "aylik": True, "not": "Ford Otosan yatırımcı sunumunu (pazar payı, satış adetleri) her ay günceller."},
    "ISMEN": {"url": "https://www.isyatirim.com.tr/tr-tr/bizi-taniyin/yatirimci-iliskileri/Sayfalar/yatirimci-sunumlari.aspx",
              "desen": r"/yatirimci-sunumlari/\d{4}/[^\"'<>]+\.pdf", "on": "Finansal sonuçlar sunumu"},
    "AKSA": {"url": "https://www.aksa.com/yatirimci-iliskileri/finansal-tablolar-ve-raporlar/yatirimci-sunumlari",
             "ek": ["https://www.aksa.com/yatirimci-iliskileri/finansal-tablolar-ve-raporlar/finansal-sonuclar-sunumu"],
             "desen": r"https://asset\.aksa\.com/media-data/docs/[^\"'<>]+\.pdf", "on": "Yatırımcı sunumu"},
}
GENEL = re.compile(r"^(pdf|indir|download|tıklayınız|görüntüle|)$", re.I)


GEVSEK_SSL = {"www.fordotosan.com.tr"}  # sunucu ara sertifikayı göndermiyor (tarayıcı tamamlıyor, Python tamamlayamıyor); yalnız açık sayfa okunur


def get(url, data=None, t=40):
    ctx = None
    if urllib.parse.urlparse(url).hostname in GEVSEK_SSL:
        import ssl; ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=t, context=ctx)
    b = r.read()
    if b[:2] == b"\x1f\x8b":
        import gzip; b = gzip.decompress(b)
    return b.decode("utf-8", "replace")


def temiz(s):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def dosya_adi(u):
    b = urllib.parse.unquote(u.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
    return re.sub(r"[-_]+", " ", re.sub(r"-[a-z0-9]{4,8}$", "", b)).strip()


def html_bul(url, desen):
    s = get(url)
    out = {}
    for m in re.finditer(r"""href\s*=\s*["']\s*([^"'<>]*?(?:""" + desen + r"""))\s*["']""", s, re.I):
        u = urllib.parse.quote(urllib.parse.urljoin(url, H.unescape(m.group(1)).strip()), safe=":/%?=&#+;,@")
        bas = s.rfind("<", 0, m.start())
        son = s.find("</a>", m.end())
        t = temiz(s[s.find(">", m.end()) + 1:son]) if son > 0 else ""
        cap = len(t) >= 4 and not GENEL.match(t)
        if not cap:  # bağlantı metni boş/"PDF": hemen önceki metin (tablo hücresi, kart başlığı)
            parca = [temiz(x) for x in re.split(r"<[^>]+>", s[max(0, bas - 1500):bas])]
            parca = [x for x in parca if len(x) >= 4 and not GENEL.match(x)]
            t = parca[-1] if parca else ""
        if u not in out or (cap and not out[u][1]): out[u] = (t[:140], cap)
    return [{"t": t, "u": u} for u, (t, _) in out.items()]


def anhyt(cfg):
    s = get(cfg["api"], data=b"")
    j = json.loads(s)
    if isinstance(j, str): j = json.loads(j)
    out = []
    for y in sorted(j.get("files") or [], key=lambda y: y.get("year") or "", reverse=True):
        for f in y.get("yearFiles") or []:
            if f.get("link"): out.append({"t": f.get("text") or "", "u": urllib.parse.urljoin(cfg["url"], urllib.parse.quote(f["link"], safe="/:%"))})
    return out


def oku(t, cfg):
    if cfg.get("tip") == "anhyt": L = anhyt(cfg)
    else:
        L = []
        for u in [cfg["url"]] + cfg.get("ek", []): L += html_bul(u, cfg["desen"])
    for x in L:
        if not re.search(r"20\d\d", x["t"]):
            y = re.findall(r"20\d\d", dosya_adi(x["u"])) or re.findall(r"/(20\d\d)/", x["u"])
            if y: x["t"] = (x["t"] + " " + y[-1]).strip()
        if not x["t"]: x["t"] = dosya_adi(x["u"])
        if cfg.get("on") and not re.search(r"sunum|sonuç|presentation", x["t"], re.I): x["t"] = cfg["on"] + " · " + x["t"]
    return L


def zaman():
    return datetime.datetime.now(datetime.timezone.utc)


def tara(kuru=False, zorla=False):
    D = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    now = zaman(); tr = now + datetime.timedelta(hours=3)
    msj = []
    for t, cfg in SITELER.items():
        e = D.setdefault(t, {})
        e["sayfa"] = cfg["url"]
        if cfg.get("not"): e["not"] = cfg["not"]
        else: e.pop("not", None)
        son = e.get("kontrol")
        ara = 1800 if cfg.get("aylik") and tr.day <= 3 else 3600 if e.get("hata") else 6 * 3600
        if not zorla and son and (now - datetime.datetime.fromisoformat(son.replace("Z", "+00:00"))).total_seconds() < ara: continue
        try:
            L = oku(t, cfg)
            if not L: raise ValueError("sayfada sunum bağlantısı bulunamadı")
        except Exception as ex:
            e["hata"] = repr(ex)[:160]; e["kontrol"] = now.strftime("%Y-%m-%dT%H:%MZ")
            print(t, "sunum hatası:", e["hata"]); continue
        e.pop("hata", None)
        bilinen = {x["u"] for x in e.get("tum", [])} | set(e.get("gorulen", []))
        ilk = not bilinen
        yeni = [x for x in L if x["u"] not in bilinen]
        g = now.strftime("%Y-%m-%dT%H:%MZ")
        for x in yeni:
            if not ilk: x["g"] = g
        e["gorulen"] = sorted(bilinen | {x["u"] for x in L})[-300:]
        e["liste"] = (yeni if not ilk else []) + [x for x in e.get("liste", []) if x["u"] not in {y["u"] for y in yeni}]
        if ilk: e["liste"] = L[:12]
        e["liste"] = e["liste"][:12]
        e["kontrol"] = g
        e.pop("tum", None)
        print(t, len(L), "bağlantı,", "ilk okuma" if ilk else f"{len(yeni)} yeni")
        if not ilk:
            for x in yeni:
                msj.append(f"{t} · Yeni yatırımcı sunumu (şirket sitesi)\n{x['t']}\n{x['u']}")
    if kuru:
        print(json.dumps(D, ensure_ascii=False, indent=1)[:6000]); return []
    json.dump(D, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return msj


if __name__ == "__main__":
    print("\n\n".join(tara(kuru="--kuru" in sys.argv, zorla=True)))
