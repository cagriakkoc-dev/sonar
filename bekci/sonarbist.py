"""SonarBIST: yeni KAP / SPK / Borsa İstanbul bildirimlerini puanlar, tweet taslağı yazar.
Mod: SONARBIST_MOD=golge (varsayılan: tweet atılmaz, Telegram'a gider) veya canli (X'e paylaşır, Telegram'a bilgi verir).
Acil durdurma: bekci/x_durdur dosyası varsa hiçbir şey yapılmaz. Tasarım: proje dokümanı claude/sonarbist.md"""
import json, os, re, time, html, difflib, datetime, urllib.request, urllib.error, uuid, hmac, hashlib, base64, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
KAYIT = os.path.join(BASE, "sonarbist_kayit.json")
DURDUR = os.path.join(BASE, "x_durdur")
PUBLIC = os.path.join(BASE, "..", "public", "sirket")
ESIK = int(os.environ.get("SONARBIST_ESIK", "80"))
DUSUK = int(os.environ.get("SONARBIST_DUSUK", "60"))  # gölge modda "paylaşılmazdı" olarak gösterilen alt sınır
SAAT_TAVAN, GUN_TAVAN, DUSUK_TAVAN = 3, 12, 10
HAIKU = os.environ.get("SONARBIST_HAIKU", "claude-sonnet-5-5")  # puanlama modeli; Haiku yanıtları kesildi, şimdilik Sonnet (geri almak için SONARBIST_HAIKU=claude-haiku-5-5)
SONNET = os.environ.get("SONARBIST_SONNET", "claude-sonnet-5-5")
KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MOD = os.environ.get("SONARBIST_MOD", "golge").strip().lower()
XK = {k: os.environ.get(v, "").strip() for k, v in (("ck", "X_API_KEY"), ("cs", "X_API_SECRET"), ("tk", "X_ACCESS_TOKEN"), ("ts", "X_ACCESS_SECRET"))}
HESAP = "SonarBIST"
UA = {"User-Agent": "Mozilla/5.0 SonarBIST"}
SON = None

# ---- kural tabanlı ön eleme (bölüm 3) ----
ARACI = {"ISMEN", "A1CAP", "GEDIK", "GLBMD", "INFO", "OSMEN", "OYYAT", "TERA"}
ARACI_RUTIN = re.compile(r"varant|sertifika|piyasa yapıcılı|ihraç belgesi|borçlanma aracı|faiz oranı|kupon|fon ", re.I)
RUTIN = re.compile(r"sorumluluk beyan|pay alım satım|hazirun|genel kurul tescil|esas sözleşme tescil|yatırımcı ilişkileri.{0,40}(iletişim|bölüm)|bağımsız denetim kuruluşu|faaliyet raporu.{0,20}yayım", re.I)

def on_eleme(hisse, baslik, ozet):
    m = f"{baslik} {ozet}"
    if RUTIN.search(m): return "rutin bildirim"
    if hisse in ARACI and ARACI_RUTIN.search(m): return "aracı kurum rutin işlemi"
    return None

# ---- yardımcılar ----
def _js(yol, vars_=None):
    try: return json.load(open(yol, encoding="utf-8"))
    except Exception: return vars_ if vars_ is not None else []

def _kaydet(k):
    json.dump(k[-600:], open(KAYIT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def http(url, data=None, headers=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")

def claude(model, system, user, maxtok=700):
    global SON
    maxtok = max(maxtok * 4, 3000)  # Sonnet 5.5 düşünme belirteçleri çıktıyı kesiyordu
    b = {"model": model, "max_tokens": maxtok, "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
         "messages": [{"role": "user", "content": user}]}
    try:
        r = http("https://api.anthropic.com/v1/messages", json.dumps(b).encode(),
                 {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Claude API {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
    j = json.loads(r); SON = j.get("stop_reason")
    return "".join(c.get("text", "") for c in j["content"] if c.get("type") == "text")

def jparse(s):
    m = re.search(r"\{.*\}", s, re.S)
    return json.loads(m.group(0)) if m else {}

def duz_metin(raw):
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    t = re.sub(r"(?i)</(p|div|tr|li|h\d)>|<br\s*/?>", "\n", t); t = re.sub(r"(?i)</t[dh]>", " | ", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t\xa0]+", " ", t)).strip()

def kap_metin(i):
    """Bildirimin düz metni (bekçi indirdiyse gelen/<id>/, değilse KAP'tan)."""
    yol = os.path.join(BASE, "gelen", str(i), "bildirim.html")
    raw = open(yol, encoding="utf-8", errors="ignore").read() if os.path.exists(yol) else \
        http(f"https://www.kap.org.tr/tr/Bildirim/{i}", headers=UA, timeout=60).decode("utf-8", "ignore")
    t = duz_metin(raw); k = t.find("Açıklamalar")
    return (t[max(0, k - 800):k + 7000] if k > 0 else t[:7000])

def buyukluk(hisse):
    """Sonar şirket sayfasından büyüklükler (public/sirket/<kod>/index.html)."""
    try:
        s = open(os.path.join(PUBLIC, hisse.lower(), "index.html"), encoding="utf-8").read()
        t = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", "", s))))
        out = []
        for ad in ("Hasılat · son 4 çeyrek", "Net kâr · son 4 çeyrek", "Piyasa değeri", "PD/DD", "F/K"):
            m = re.search(re.escape(ad) + r" (-?[\d.,]+x?(?: (?:milyar|milyon) TL)?)", t)
            if m: out.append(f"{ad}: {m.group(1)}")
        return "; ".join(out) or "veri yok"
    except Exception:
        return "veri yok"

# ---- puanlama (Haiku) ----
PUAN_SYS = """Sen Borsa İstanbul bildirimlerini önem puanına çeviren bir analistsin. Yalnız JSON döndür.
Puan 0-100 = finansal etki (0-40: tutarın şirket büyüklüğüne oranı; büyüklük verisi verilir) + yenilik/sürpriz (0-20) + kapsam (0-20: şirketin tamamını etkiliyor mu: yönetim, temettü, sermaye, birleşme) + kesinlik (0-10: imzalı/kesinleşmiş mi, niyet/görüşme mi) + ilgi (0-10: BIST 30/100 üyeliği, bilinen büyük şirket).
Rutin işlemler, küçük tutarlar, usulî bildirimler düşük puan alır.
Şu türler editörün kararıyla HER ZAMAN önemlidir ve en az 80 puan alır (şirket küçük veya tutar belirsiz olsa bile): kâr payı (temettü) dağıtım kararı, tutarı veya ödemesi; yeni iş ilişkisi, sözleşme, sipariş; finansal sonuç (bilanço) açıklaması; yatırımcı sunumu; geleceğe ilişkin değerlendirme, beklenti, rehberlik (gelir/kâr hedefi, yatırım planı). Bu türlerde puanı 80-100 arasında ver; genel kurul toplantı usulü, hazirun cetveli gibi usulî bildirimler bu gruba girmez. Çıktı: {"puan": int, "fin": int, "yenilik": int, "kapsam": int, "kesinlik": int, "ilgi": int, "tur": "kısa tür", "gerekce": "tek cümle"}"""

def olumsuz(kayit):
    """Kullanıcının X'ten silip bildirdiği tweetler: gereksiz paylaşım örnekleri (kayıtta "silindi": true)."""
    return [x for x in kayit if x.get("silindi")][-15:]

def puanla(hisse, baslik, metin, buy, kayit=()):
    u = f"Şirket: {hisse}\nBüyüklükler (Sonar): {buy}\nBaşlık: {baslik}\n\nBildirim metni:\n{metin[:6000]}"
    neg = olumsuz(kayit)
    if neg: u += "\n\nEditör şu bildirimler için atılan tweetleri GEREKSİZ bulup sildi; benzerlerini belirgin düşük puanla (örnekler):\n" + "\n".join(f"- {x.get('hisse')} | {x.get('tur')} | {x.get('baslik','')[:100]} (önceki puan {x.get('puan')})" for x in neg)
    raw = claude(HAIKU, PUAN_SYS, u, 500); p = jparse(raw)
    if p.get("puan") is None:
        m = re.search(r'"puan"\s*:\s*(\d+)', raw)
        if not m: raise RuntimeError(f"puanlama yanıtı çözülemedi (stop={SON}, uzunluk={len(raw)}): " + raw[:150] + " … " + raw[-100:])
        p = {"puan": int(m.group(1)), "tur": (re.search(r'"tur"\s*:\s*"([^"]*)"', raw) or [None, None])[1], "gerekce": (re.search(r'"gerekce"\s*:\s*"([^"]*)', raw) or [None, ""])[1]}
    return p

# ---- yazım (Sonnet) ----
YAZ_SYS = """Sen SonarBIST'in editörüsün: Borsa İstanbul haber notlarını X'te kısa bir muhabir notu gibi yazarsın. Yalnız JSON döndür.
Dil: akıcı, sade, formal ama robot gibi değil Türkçe. Yapı: önce bilgi (ne açıklandı, rakamlarla), sonra neden önemli olduğu 1-2 cümleyle, doğal akışın devamı olarak.
Yasaklar: "Neden önemli?" / "Önemi:" gibi başlık; emoji, hashtag, $ işareti; bağlantı ve alan adı (kap.org.tr dahil); tahmin ve tavsiye (al/sat, hedef fiyat, yükselir/düşer, fırsat); kaynakta olmayan her rakam; hisse kodu tweette mutlaka geçer ve öne alınır: önce kod, parantez içinde şirket adı, örneğin "PAHOL (Pasifik Holding) ..." biçiminde; kodu yalnız bir kez ve düz yazıyla yaz.
Yorum yalnız bağlam verir: geçmişle kıyas, büyüklük (verilen Sonar büyüklükleri ve metindeki rakamlarla), şirket için ne anlama geldiği. Rakam hesaplama; kaynakta yazan rakamları kullan. Son 20 tweetle açılış, cümle yapısı ve kapanış tekrar etmemeli; her tweet farklı kalıpla başlar.
En çok 270 karakter. Çıktı: {"tweet": "...", "kap_ogesi": "ekran görüntüsüne alınacak bölümü KAP metninden birebir 6-12 kelimelik bir parçayla tanımla; parça tweetteki asıl bilginin geçtiği cümleden olsun (yasal uyarı, imza, ön yazı değil) ve yalnız KAP metninden alınsın, Sonar özet girişinden değil"}"""

def yaz(hisse, baslik, metin, buy, gecmis, hata=None, kayit=()):
    u = (f"Şirket: {hisse}\nBüyüklükler (Sonar): {buy}\nBaşlık: {baslik}\n\nSon 20 SonarBIST tweeti (tekrar etme):\n" +
         "\n".join(f"- {t}" for t in gecmis[-20:]) + f"\n\nBildirim metni:\n{metin[:7000]}")
    neg = olumsuz(kayit)
    if neg: u += "\n\nEditör şu tweetleri gereksiz bulup sildi, bu tarz yazma:\n" + "\n".join(f"- {x.get('tweet','')}" for x in neg if x.get("tweet"))
    if hata: u += f"\n\nÖnceki taslak şu nedenle reddedildi, düzelt: {hata}"
    raw = claude(SONNET, YAZ_SYS, u, 800); p = jparse(raw)
    if not p.get("tweet"): raise RuntimeError(f"yazım yanıtı çözülemedi (stop={SON}, uzunluk={len(raw)}): " + raw[:150] + " … " + raw[-100:])
    return p

# ---- doğrulama (kod) ----
YASAK = re.compile(r"\b(hedef fiyat|tavsiye|yükselecek|düşecek|yükselir|düşer|fırsat|kaçırma|al\b|sat\b|tut\b)", re.I)
BASLIK = re.compile(r"(neden önemli|önemi\s*:|özet\s*:|son dakika|önemli\s*:)", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
ALAN = re.compile(r"\b[\w-]+\.(com|io|org|net|tr|gov|info|co)\b", re.I)

def _sayilar(s):
    out = set()
    for tok in re.findall(r"\d+(?:[.,/:-]\d+)*", s):
        out.add(re.sub(r"\D", "", tok))
        for p in re.split(r"[.,/:-]", tok): out.add(p)
    return out

def dogrula(tweet, kaynak, gecmis, hisse=""):
    h = []
    if hisse and not re.search(r"\b" + re.escape(hisse) + r"\b", tweet): h.append(f"hisse kodu ({hisse}) tweette düz yazı olarak geçmiyor")
    if not tweet or len(tweet) > 280: h.append("uzunluk 280'i aşıyor veya boş")
    if re.search(r"https?://|www\.", tweet) or ALAN.search(tweet): h.append("bağlantı/alan adı var")
    if re.search(r"[#$]", tweet) or EMOJI.search(tweet): h.append("emoji, hashtag veya $ var")
    if YASAK.search(tweet): h.append("tavsiye/tahmin kalıbı")
    if BASLIK.search(tweet): h.append("başlık kalıbı")
    kay = _sayilar(kaynak)
    for tok in re.findall(r"\d+(?:[.,]\d+)*", tweet):
        d = re.sub(r"\D", "", tok)
        if not any(k == d or (k.startswith(d) and set(k[len(d):]) <= {"0"}) or (d.startswith(k) and k and set(d[len(k):]) <= {"0"}) for k in kay):
            h.append(f"rakam kaynakta yok: {tok}"); break
    ac = " ".join(tweet.lower().split()[:3])
    for g in gecmis[-8:]:
        if " ".join(g.lower().split()[:3]) == ac: h.append("açılış son tweetlerle aynı"); break
    for g in gecmis[-20:]:
        if difflib.SequenceMatcher(None, tweet.lower(), g.lower()).ratio() > 0.6: h.append("son tweetlere çok benziyor"); break
    return h

# ---- KAP ekran görüntüsü (bölüm 5, en iyi çaba) ----
def goruntu(i, parca):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None, "playwright yok"
    yol = os.path.join(BASE, "sonarbist_gecici.png")
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1100, "height": 1400}, device_scale_factor=2, locale="tr-TR")
            pg.goto(f"https://www.kap.org.tr/tr/Bildirim/{i}", wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_selector(".notification_detail-disclosure-detail, .disclosureScrollableArea", timeout=45000)
            pg.wait_for_timeout(1500)
            js = r"""(t)=>{const r=document.querySelector('.notification_detail-disclosure-detail'); if(!r) return false;
              document.querySelectorAll('[data-sb]').forEach(e=>e.removeAttribute('data-sb'));
              const n=(t||'').toLowerCase().replace(/\s+/g,' ').slice(0,40); let best=null;
              if(n){for(const e of r.querySelectorAll('td,p,div,span,tr,li')){const x=(e.innerText||'').toLowerCase().replace(/\s+/g,' ');
                if(x.includes(n) && (!best || x.length<best.len)) best={e,len:x.length};}}
              let e=best?best.e:r;
              if(best){ while(e.parentElement && e!==r && e.getBoundingClientRect().height<220) e=e.parentElement;
                if(e.getBoundingClientRect().height>1100) e=best.e; }
              e.setAttribute('data-sb','1'); return !!best;}"""
            bulundu = pg.evaluate(js, parca or "")
            hed = pg.locator('[data-sb="1"]').first
            hed.scroll_into_view_if_needed()
            if bulundu:
                hed.screenshot(path=yol)
            else:  # bölüm bulunamazsa bildirimin üst kısmı
                bx = hed.bounding_box()
                pg.screenshot(path=yol, clip={"x": bx["x"], "y": max(bx["y"], 0), "width": bx["width"], "height": min(max(bx["height"], 300), 700)})
            b.close()
        return yol, None
    except Exception as e:
        return None, repr(e)[:150]


# ---- finansal rapor (bilanço) ölçüleri ve kartı ----
def _tl(v):
    a = abs(v)
    if a >= 1e9: return f"{v/1e9:.1f}".replace(".", ",") + " milyar TL"
    if a >= 1e6: return f"{v/1e6:.1f}".replace(".", ",") + " milyon TL"
    return f"{v/1e3:.0f}".replace(".", ",") + " bin TL"

def _deg(c, o):
    if o is None or c is None: return "", ""
    if o == 0: return "kıyaslanamaz", ""
    if o < 0 < c: return "zarardan kâra", "up"
    if c < 0 < o: return "kârdan zarara", "down"
    y = (c - o) / abs(o) * 100
    s = f"%{abs(y):.1f}".replace(".", ",") + (" artış" if y >= 0 else " azalış")
    return s, ("up" if y >= 0 else "down")

def fr_olc(kid):
    """KAP bildirim sayfasındaki XBRL satırlarından ana kalemleri çıkarır. Bulamazsa None."""
    import sys as _s
    _s.path.insert(0, os.path.join(BASE, "araclar"))
    import xbrl_cek
    raw = http(f"https://www.kap.org.tr/tr/Bildirim/{kid}", headers=UA, timeout=90).decode("utf-8", "ignore")
    rows = [r for r in xbrl_cek.rows(raw) if len(r) >= 3 and isinstance(r[1], (int, float)) and isinstance(r[2], (int, float))]
    def bul(*adlar, onek=False):
        for ad in adlar:
            for r in rows:
                l = r[0].strip().lower()
                if (l.startswith(ad) if onek else l == ad): return r
        return None
    sec = [("Hasılat", bul("hasılat"), "geçen yıl aynı dönem"),
           ("Brüt kâr", bul("brüt kar (zarar)", "brüt kâr (zarar)", "brüt kar", onek=True), "geçen yıl aynı dönem"),
           ("Esas faaliyet kârı", bul("esas faaliyet karı (zararı)", "esas faaliyet kârı (zararı)", "esas faaliyet karı", onek=True), "geçen yıl aynı dönem"),
           ("Net dönem kârı", bul("net dönem karı veya zararı", "dönem karı (zararı)"), "geçen yıl aynı dönem"),
           ("Özkaynaklar", bul("ana ortaklığa ait özkaynaklar", "özkaynaklar"), "önceki yıl sonu")]
    sec = [(a, r, k) for a, r, k in sec if r]
    if not any(a in ("Hasılat", "Net dönem kârı") for a, _, _ in sec): return None
    sat = []; kart = []
    for ad, r, kar in sec:
        c, o = r[1], r[2]; yaz_, yon = _deg(c, o)
        sat.append(f"{ad}: {_tl(c)} ({kar}: {_tl(o)}; {yaz_})")
        kart.append((ad, _tl(c), _tl(o), yaz_, yon))
    return {"satirlar": sat, "kart": kart}

def fr_kart(hisse, baslik, olc):
    from playwright.sync_api import sync_playwright
    yol = os.path.join(BASE, "sonarbist_kart.png")
    trs = "".join(f'<tr><td class="a">{html.escape(a)}</td><td>{html.escape(c)}</td><td class="o">{html.escape(o)}</td><td class="{"u" if y == "up" else "d" if y == "down" else "n"}">{html.escape(d)}</td></tr>' for a, c, o, d, y in olc["kart"])
    h = f"""<html><body style="margin:0;background:#fff"><div id="k" style="width:900px;box-sizing:border-box;padding:36px 40px;font-family:Arial,Helvetica,sans-serif;color:#0f172a;background:#fff">
<div style="font-size:15px;color:#64748b;letter-spacing:.5px">FİNANSAL SONUÇLAR</div>
<div style="font-size:34px;font-weight:700;margin:4px 0 2px">{html.escape(hisse)}</div>
<div style="font-size:16px;color:#475569;margin-bottom:22px">{html.escape(baslik)[:90]}</div>
<table style="width:100%;border-collapse:collapse;font-size:20px"><tr style="color:#64748b;font-size:14px;text-align:left"><th style="padding:8px 0">Kalem</th><th>Bu dönem</th><th>Karşılaştırma dönemi</th><th>Değişim</th></tr>{trs}</table>
<div style="margin-top:20px;font-size:13px;color:#94a3b8">Kaynak: KAP finansal rapor · Sonar</div></div>
<style>td{{padding:11px 0;border-top:1px solid #e2e8f0}}td.a{{font-weight:600}}td.o{{color:#64748b}}td.u{{color:#047857;font-weight:600}}td.d{{color:#b91c1c;font-weight:600}}td.n{{color:#475569}}</style></body></html>"""
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 900, "height": 700}, device_scale_factor=2)
        pg.set_content(h); pg.locator("#k").screenshot(path=yol); b.close()
    return yol

# ---- Telegram (gölge mod) ----
def tg(token, chat, metin, foto=None):
    if foto and os.path.exists(foto):
        sn = uuid.uuid4().hex; v = open(foto, "rb").read()
        parts = [("chat_id", chat), ("caption", metin[:1000])]
        body = b"".join(f'--{sn}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{val}\r\n'.encode() for k, val in parts)
        body += f'--{sn}\r\nContent-Disposition: form-data; name="photo"; filename="kap.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + v + f"\r\n--{sn}--\r\n".encode()
        http(f"https://api.telegram.org/bot{token}/sendPhoto", body, {"Content-Type": f"multipart/form-data; boundary={sn}"})
    else:
        http(f"https://api.telegram.org/bot{token}/sendMessage", json.dumps({"chat_id": chat, "text": metin, "disable_web_page_preview": True}).encode(),
             {"Content-Type": "application/json"})


# ---- X (canlı mod): OAuth 1.0a ----
def _pe(x): return urllib.parse.quote(str(x), safe="~")

def oauth_baslik(method, url, params, ck, cs, tk, ts, nonce=None, stamp=None):
    o = {"oauth_consumer_key": ck, "oauth_nonce": nonce or uuid.uuid4().hex, "oauth_signature_method": "HMAC-SHA1",
         "oauth_timestamp": stamp or str(int(time.time())), "oauth_token": tk, "oauth_version": "1.0"}
    allp = sorted((_pe(k), _pe(v)) for k, v in {**params, **o}.items())
    taban = "&".join([method.upper(), _pe(url), _pe("&".join(f"{k}={v}" for k, v in allp))])
    o["oauth_signature"] = base64.b64encode(hmac.new(f"{_pe(cs)}&{_pe(ts)}".encode(), taban.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_pe(k)}="{_pe(v)}"' for k, v in sorted(o.items()))

def x_hazir(): return all(XK.values())

def x_gorsel(yol):
    """Görseli yükler, media_id döner (v2 medya yükleme). Başarısızsa istisna."""
    url = "https://api.x.com/2/media/upload"; sn = uuid.uuid4().hex
    body = (f'--{sn}\r\nContent-Disposition: form-data; name="media_category"\r\n\r\ntweet_image\r\n'.encode() +
            f'--{sn}\r\nContent-Disposition: form-data; name="media"; filename="kap.png"\r\nContent-Type: image/png\r\n\r\n'.encode() +
            open(yol, "rb").read() + f"\r\n--{sn}--\r\n".encode())
    r = http(url, body, {"Content-Type": f"multipart/form-data; boundary={sn}", "Authorization": oauth_baslik("POST", url, {}, XK["ck"], XK["cs"], XK["tk"], XK["ts"])})
    j = json.loads(r); return (j.get("data") or j).get("id") or j.get("media_id_string")

def x_paylas(metin, gorsel=None):
    """Tweet atar; (tweet_id, gorsel_hatasi) döner."""
    url = "https://api.x.com/2/tweets"; payload = {"text": metin}; ghata = None
    if gorsel:
        try: payload["media"] = {"media_ids": [str(x_gorsel(gorsel))]}
        except Exception as e: ghata = repr(e)[:200]
    r = http(url, json.dumps(payload).encode(), {"Content-Type": "application/json", "Authorization": oauth_baslik("POST", url, {}, XK["ck"], XK["cs"], XK["tk"], XK["ts"])})
    return json.loads(r)["data"]["id"], ghata


# ---- Sonar'da yayına alınan özetler (public/haber/<hisse>-<kapid>) ----
def ozetleri_tara(token, chat):
    """Cagri bir haber özetini yayına alınca public/haber/<hisse>-<id>/ oluşur; SonarBIST o özetin girişini (meta açıklama)
    ve KAP metnini kaynak alıp tweet atar. İlk çalışmada mevcut sayfalar sessizce 'görüldü' sayılır."""
    if os.path.exists(DURDUR) or not KEY: return
    kok = os.path.join(BASE, "..", "public", "haber")
    if not os.path.isdir(kok): return
    gp = os.path.join(BASE, "sonarbist_ozet_gorulen.json")
    mevcut = sorted(d for d in os.listdir(kok) if os.path.isfile(os.path.join(kok, d, "index.html")))
    if not os.path.exists(gp):
        json.dump(mevcut, open(gp, "w", encoding="utf-8")); return
    gor = _js(gp)
    # tek seferlik: PAHOL özeti belirteç sınırı yüzünden yazılamadı, yeniden dene
    ky = _js(KAYIT)
    if any(k.get("id") == "ozet-1691690" and k.get("durum") == "hata" for k in ky):
        _kaydet([k for k in ky if k.get("id") != "ozet-1691690"]); gor = [x for x in gor if x != "pahol-1691690"]
    for d in mevcut:
        if d in gor: continue
        gor.append(d); json.dump(gor, open(gp, "w", encoding="utf-8"), ensure_ascii=False)
        m = re.match(r"^([a-z0-9]+)-(\d{7})$", d)
        if not m: continue  # sunum özetleri vb. (kimlik KAP numarası değil)
        hisse, kid = m.group(1).upper(), m.group(2)
        if any(k.get("id") == f"kap-{kid}" and k.get("durum") == "paylasildi" for k in _js(KAYIT)): continue  # anlık tweet zaten atılmış
        t = open(os.path.join(kok, d, "index.html"), encoding="utf-8", errors="ignore").read()
        bm = re.search(r"<title>(.*?) · Sonar</title>", t); dm = re.search(r'<meta name="description" content="(.*?)"', t)
        baslik = html.unescape(bm.group(1)).split(": ", 1)[-1] if bm else d
        giris = html.unescape(dm.group(1)) if dm else ""
        def mf(g=giris, i=kid):
            try: kapm = kap_metin(i)
            except Exception: kapm = ""
            return "[SONAR ÖZETİ, yayına alındı] Özet girişi: " + g + "\n\nKAP metni:\n" + kapm
        isle(token, chat, "ozet", kid, hisse, baslik, giris, link=f"https://www.kap.org.tr/tr/Bildirim/{kid}", metin_fn=mf, zorla=True)

# ---- ana akış ----
def isle(token, chat, kaynak, kid, hisse, baslik, ozet, fr=False, link="", metin_fn=None, zorla=False):
    """Bir bildirimi işler. kaynak: kap|spk|bist. Dönüş: kayıt sözlüğü veya None."""
    if os.path.exists(DURDUR) or not KEY: return None
    kayit = _js(KAYIT); anahtar = f"{kaynak}-{kid}"
    if any(k.get("id") == anahtar for k in kayit): return None
    simdi = datetime.datetime.now(datetime.timezone.utc); k = {"id": anahtar, "hisse": hisse, "baslik": baslik[:150], "t": simdi.isoformat(timespec="seconds"), "mod": "golge"}
    try:
        sebep = on_eleme(hisse, baslik, ozet or "")
        if sebep:
            k.update(durum="elendi", sebep=sebep); kayit.append(k); _kaydet(kayit); return k
        olc = None
        if fr:  # finansal rapor: XBRL ölçüleri + bilanço kartı
            olc = fr_olc(kid)
            if not olc:
                k.update(durum="fr_atlandi", sebep="finansal rapor: XBRL kalemleri çıkarılamadı (banka/sigorta vb. olabilir)"); kayit.append(k); _kaydet(kayit)
                tg(token, chat, f"SonarBIST · {hisse} finansal rapor, kalemler çıkarılamadı, atlandı\n{link}"); return k
        if fr:
            metin = ("[FİNANSAL SONUÇ] Dönem: " + baslik + ". Tweet: önce hasılat ve net kârı, geçen yılın aynı dönemiyle kıyaslayarak yaz; yalnız aşağıdaki rakam ve yüzdeleri kullan, kendin hesaplama. Kalemler:\n" + "\n".join(olc["satirlar"]))
        else:
            metin = metin_fn() if metin_fn else kap_metin(kid)
        buy = buyukluk(hisse) if hisse else "veri yok"
        p = {"puan": 100, "tur": "yayınlanan özet", "gerekce": "Sonar'da yayına alınan özet"} if zorla else puanla(hisse, baslik, metin, buy, kayit)
        k.update(puan=p.get("puan"), alt={x: p.get(x) for x in ("fin", "yenilik", "kapsam", "kesinlik", "ilgi")}, tur=p.get("tur"), gerekce=p.get("gerekce"))
        puan = int(p.get("puan") or 0)
        if puan < ESIK:
            k["durum"] = "dusuk"
            bugun = [x for x in kayit if x.get("durum") == "dusuk_bildirildi" and x["t"][:10] == simdi.date().isoformat()]
            if puan >= DUSUK and len(bugun) < DUSUK_TAVAN:
                tg(token, chat, f"SonarBIST · paylaşılmazdı (puan {puan}) · {hisse}\n{baslik[:200]}\n{p.get('gerekce','')}\n{link}"); k["durum"] = "dusuk_bildirildi"
            kayit.append(k); _kaydet(kayit); return k
        saat = [x for x in kayit if x.get("durum") == "taslak" and x["t"] > (simdi - datetime.timedelta(hours=1)).isoformat()]
        gun = [x for x in kayit if x.get("durum") == "taslak" and x["t"][:10] == simdi.date().isoformat()]
        if len(saat) >= SAAT_TAVAN or len(gun) >= GUN_TAVAN:
            k.update(durum="tavan", sebep="saat/gün tavanı"); kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST · tavan nedeniyle sıraya alınmadı (puan {puan}) · {hisse}\n{baslik[:200]}\n{link}"); return k
        gecmis = [x["tweet"] for x in kayit if x.get("tweet")]
        kaynak_m = metin + " " + buy; hata = None; taslak = {}
        for deneme in range(2):
            taslak = yaz(hisse, baslik, metin, buy, gecmis, hata, kayit)
            h = dogrula(taslak.get("tweet", ""), kaynak_m, gecmis, hisse)
            if not h: break
            hata = "; ".join(h)
        if h:
            k.update(durum="dogrulama_hatasi", sebep=hata, tweet_red=taslak.get("tweet")); kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST · taslak doğrulamadan geçmedi (puan {puan}) · {hisse}\n{baslik[:160]}\nNeden: {hata}\nTaslak: {taslak.get('tweet')}\n{link}"); return k
        if fr:
            try: foto, ghata = fr_kart(hisse, baslik, olc), None
            except Exception as e: foto, ghata = None, "kart: " + repr(e)[:120]
        else:
            foto, ghata = goruntu(kid, taslak.get("kap_ogesi")) if kaynak in ("kap", "ozet") else (None, None)
        k.update(durum="taslak", tweet=taslak["tweet"], kap_ogesi=taslak.get("kap_ogesi"), goruntu=bool(foto), goruntu_hata=ghata)
        if MOD == "canli" and x_hazir():
            k["mod"] = "canli"; tid, xg = x_paylas(taslak["tweet"], foto)
            k.update(durum="paylasildi", tweet_id=tid, x_gorsel_hata=xg); kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST PAYLAŞILDI · puan {puan} · {hisse}\nhttps://x.com/{HESAP}/status/{tid}\n\n{taslak['tweet']}\n\nGerekçe: {p.get('gerekce','')}\n{link}" +
               (f"\n(KAP görseli yok: {ghata})" if ghata else "") + (f"\n(X görsel yüklemesi başarısız, metinle atıldı: {xg})" if xg else "") + "\nGereksizse X'ten sil ve bana 'sildim' de.", foto)
            if foto:
                try: os.remove(foto)
                except Exception: pass
            return k
        kayit.append(k); _kaydet(kayit)
        tg(token, chat, f"SonarBIST taslağı (gölge) · puan {puan} · {hisse}\n\n{taslak['tweet']}\n\nGerekçe: {p.get('gerekce','')}\n{link}" + (f"\n(görsel alınamadı: {ghata})" if ghata else ""), foto)
        if foto:
            try: os.remove(foto)
            except Exception: pass
        return k
    except Exception as e:
        k.update(durum="hata", sebep=repr(e)[:700])
        try:
            kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST hata · {hisse} · {baslik[:100]}\n{repr(e)[:300]}")
        except Exception: pass
        return k
