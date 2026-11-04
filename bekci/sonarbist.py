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
ACIK_TAVAN_SON = datetime.datetime(2026, 11, 3, 21, 0, tzinfo=datetime.timezone.utc)  # Cagri 3 Kas: test için tavan bugünlük kapalı (TR gece yarısına kadar)
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
Şu türler editörün kararıyla HER ZAMAN önemlidir ve en az 80 puan alır (şirket küçük veya tutar belirsiz olsa bile): kâr payı (temettü) dağıtım kararı, tutarı veya ödemesi; yeni iş ilişkisi, sözleşme, sipariş; finansal sonuç (bilanço) açıklaması; yatırımcı sunumu; pay geri alımı (şirketin kendi paylarını geri alması, alınan lot ve tutar); geleceğe ilişkin değerlendirme, beklenti, rehberlik (gelir/kâr hedefi, yatırım planı). Bu türlerde puanı 80-100 arasında ver; genel kurul toplantı usulü, hazirun cetveli gibi usulî bildirimler bu gruba girmez. Çıktı: {"puan": int, "fin": int, "yenilik": int, "kapsam": int, "kesinlik": int, "ilgi": int, "tur": "kısa tür", "gerekce": "tek cümle"}"""

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
Doğal anlatım: bildirimde neyin bulunmadığını söyleme ("Bildirimde rakam yok", "tutar belirtilmedi", "ayrıntı verilmedi" gibi cümleler yasak); yalnız var olan bilgiyi ve bağlamı yaz. Sunum veya genel özel durum bildirimlerinde ne açıklandığını ve şirket için neden önemli olduğunu anlat.
Pay geri alımı bildiriminde: alınan lot (adet) ve tutarı, kaynakta yazıyorsa ortalama fiyatı ve şirket sermayesine oranını (%) mutlaka ver; oran kaynakta yoksa kendin hesaplama, yazma.
Biçim: noktalı virgül (;) kullanma. Birden çok bilgi varsa onları ";" ile tek cümleye bağlama; boş satırla ayrılmış kısa paragraflar halinde ya da her biri "• " ile başlayan kısa maddeler halinde ver (madde işareti yalnız "•"). Tweet bir muhabir notu gibi okunmalı, ama tek uzun cümle olmamalı.
Yasaklar: "Neden önemli?" / "Önemi:" gibi başlık; emoji, hashtag, $ işareti; bağlantı ve alan adı (kap.org.tr dahil); tahmin ve tavsiye (al/sat, hedef fiyat, yükselir/düşer, fırsat); kaynakta olmayan her rakam; hisse kodu tweette mutlaka geçer ve öne alınır: önce kod, parantez içinde şirket adı, örneğin "PAHOL (Pasifik Holding) ..." biçiminde; kodu yalnız bir kez ve düz yazıyla yaz.
Yorum yalnız bağlam verir: geçmişle kıyas, büyüklük (verilen Sonar büyüklükleri ve metindeki rakamlarla), şirket için ne anlama geldiği. Rakam hesaplama; kaynakta yazan rakamları kullan. Son 20 tweetle açılış, cümle yapısı ve kapanış tekrar etmemeli; her tweet farklı kalıpla başlar.
En çok 270 karakter. Çıktı: {"tweet": "...", "kart": {"baslik": "en çok 6 kelimelik kart başlığı", "satirlar": [["etiket", "değer"], ...]}}. Kart tweetin görselidir: 3-5 satır, her satır kısa etiket + kaynakta yazan değer (lot, tutar, fiyat, oran, tarih, süre gibi). Etiket en çok 4 kelime, değer en çok 22 karakter ve kaynaktaki rakamlarla birebir (örn. "4.100.000 lot", "%0,09", "1,68-1,70 TL"). Başlıkta ve satırlarda hisse kodu, marka adı, kullanıcı adı, bağlantı, # veya @ olmasın; rakam hesaplama."""

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
    if re.search(r"(bildirimde|açıklamada)[^.\n]{0,40}(yok|yer almıyor|belirtilmemiş|bulunmuyor)|belirtilmedi|rakam yok|ayrıntı verilmedi", tweet, re.I): h.append("bilginin eksikliğini söyleme, yalnız var olanı yaz")
    if ";" in tweet: h.append("noktalı virgül var: paragraf veya • maddeleriyle ayır")
    kay = _sayilar(kaynak)
    for tok in re.findall(r"\d+(?:[.,]\d+)*", tweet):
        d = re.sub(r"\D", "", tok)
        if tok not in kaynak and not any(k == d or (k.startswith(d) and set(k[len(d):]) <= {"0"}) or (d.startswith(k) and k and set(d[len(k):]) <= {"0"}) for k in kay):
            h.append(f"rakam kaynakta yok: {tok}"); break
    def _acilis(t): return " ".join(re.sub(r"^\S+ \([^)]*\),?\s*", "", t.lower()).split()[:3])
    ac = _acilis(tweet)
    for g in gecmis[-8:]:
        if _acilis(g) == ac: h.append("açılış son tweetlerle aynı"); break
    for g in gecmis[-20:]:
        if difflib.SequenceMatcher(None, tweet.lower(), g.lower()).ratio() > 0.6: h.append("son tweetlere çok benziyor"); break
    return h

# ---- KAP ekran görüntüsü (bölüm 5, en iyi çaba) ----
def site_karti(hisse, kid, bekle=75):
    """Sonar'daki haber sayfasında (admin panelinde üretilen) ilk kartı 1080x1350 PNG olarak alır."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None, "playwright yok"
    import base64, time
    yol = os.path.join(BASE, "sonarbist_site_karti.png")
    url = f"https://sonar.smartcuzdan.io/haber/{hisse.lower()}-{kid}/"
    son = "kart bulunamadı"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 1400}, locale="tr-TR")
            bit = time.time() + bekle
            while time.time() < bit:
                try:
                    pg.goto(url + "?t=" + str(int(time.time())), wait_until="domcontentloaded", timeout=45000)
                    pg.wait_for_selector('canvas[data-hc="0"]', timeout=15000)
                    pg.wait_for_timeout(3500)
                    d = pg.evaluate("document.querySelector('canvas[data-hc=\"0\"]').toDataURL('image/png')")
                    if d and len(d) > 20000:
                        open(yol, "wb").write(base64.b64decode(d.split(",", 1)[1])); b.close(); return yol, None
                    son = "kart boş"
                except Exception as e:
                    son = repr(e)[:120]
                pg.wait_for_timeout(8000)
            b.close()
    except Exception as e:
        son = repr(e)[:150]
    return None, "site kartı: " + son

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
def _k(s):
    """Türkçe büyük/küçük harf: İ→i, I→ı, sonra küçült."""
    return s.replace("İ", "i").replace("I", "ı").strip().lower()

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

def _tr_say(s):
    return float(s.replace(".", "").replace(",", "."))

def _olcek(rows, hisse):
    """KAP rakamlarının birimi şirkete göre TL, bin TL veya milyon TL olabilir; Sonar'daki son 4 çeyrek hasılatına bakıp çarpanı bulur."""
    try:
        m = re.search(r"Hasılat · son 4 çeyrek: (-?[\d.,]+) (milyar|milyon) TL", buyukluk(hisse))
        if not m: return 1
        ltm = _tr_say(m.group(1)) * (1e9 if m.group(2) == "milyar" else 1e6)
        has = next((r for r in rows if _k(r[0]) == "hasılat" and isinstance(r[1], (int, float))), None)
        if not has or not has[1] or not ltm: return 1
        for f in (1, 1000, 1000000):
            if 0.1 <= abs(has[1]) * f / ltm <= 1.6: return f
    except Exception:
        pass
    return 1

def _olcekle(rows, f):
    return rows if f == 1 else [[r[0]] + [(v * f if isinstance(v, (int, float)) else v) for v in r[1:]] for r in rows]

def fr_olc(kid, hisse=""):
    """KAP bildirim sayfasındaki XBRL satırlarından ana kalemleri çıkarır. Bulamazsa None."""
    import sys as _s
    _s.path.insert(0, os.path.join(BASE, "araclar"))
    import xbrl_cek
    raw = http(f"https://www.kap.org.tr/tr/Bildirim/{kid}", headers=UA, timeout=90).decode("utf-8", "ignore")
    rows = [r for r in xbrl_cek.rows(raw) if len(r) >= 3 and isinstance(r[1], (int, float)) and isinstance(r[2], (int, float))]
    rows = _olcekle(rows, _olcek(rows, hisse)) if hisse else rows
    def bul(*adlar, onek=False):
        for ad in adlar:
            for r in rows:
                l = _k(r[0])
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
    return {"satirlar": sat, "kart": kart, "rows": rows}

def fr_kart(hisse, baslik, olc):
    """Finansal sonuç kartı (1080x1350, açık tema): her kalemde bu dönem, karşılaştırma ve yeşil artış / kırmızı azalış yüzdesi."""
    from playwright.sync_api import sync_playwright
    yol = os.path.join(BASE, "sonarbist_kart.png")
    ok = {"up": "▲", "down": "▼"}
    tarih = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%d.%m.%Y")
    rows = ""
    for a_, c, o, d, y in olc["kart"]:
        chip = '<span class="c %s">%s</span>' % (y or "n", html.escape((ok.get(y, "") + " " + d).strip())) if d else ""
        et = "önceki yıl sonu" if a_ == "Özkaynaklar" else "geçen yılın aynı dönemi"
        rows += '<div class="r"><div class="l">%s</div><div class="rr"><div class="v">%s</div>%s</div><div class="o">%s: %s</div></div>' % (
            html.escape(a_), html.escape(c), chip, et, html.escape(o))
    css = ("*{box-sizing:border-box}body{margin:0;background:#f6f8fb}"
           "#k{width:1080px;height:1350px;padding:72px;background:#f6f8fb;color:#0f172a;font-family:'Plus Jakarta Sans','Segoe UI',Arial,Helvetica,sans-serif;position:relative;overflow:hidden}"
           "#k:before{content:'';position:absolute;left:0;right:0;top:0;height:10px;background:#1d6fd8}"
           ".h{color:#1d6fd8;font-size:30px;font-weight:600;letter-spacing:.5px}"
           ".t{font-size:64px;font-weight:700;line-height:1.1;margin:26px 0 8px}.s{color:#64748b;font-size:28px;margin-bottom:40px}"
           ".r{background:#fff;box-shadow:0 1px 3px rgba(15,23,42,.12);border-left:8px solid #1d6fd8;border-radius:10px;padding:22px 36px;margin-bottom:20px}"
           ".l{color:#64748b;font-size:28px;font-weight:500}.rr{display:flex;justify-content:space-between;align-items:center;margin:4px 0}"
           ".v{font-size:52px;font-weight:700}.o{color:#64748b;font-size:26px}"
           ".c{font-size:30px;font-weight:700;padding:8px 20px;border-radius:999px;white-space:nowrap}"
           ".c.up{color:#047857;background:#d1fae5}.c.down{color:#b91c1c;background:#fee2e2}.c.n{color:#475569;background:#e2e8f0}"
           ".f{position:absolute;left:72px;bottom:48px;color:#64748b;font-size:26px}")
    doc = ('<html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700&display=swap" rel="stylesheet"><style>' + css + '</style></head><body><div id="k"><div class="h">'
           + html.escape(hisse) + " · KAP · " + tarih + '</div><div class="t">Finansal sonuçlar</div><div class="s">' + html.escape(baslik)[:70] + '</div>' + rows + '<div class="f">Kaynak: KAP finansal rapor</div></div></body></html>')
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1080, "height": 1350})
        try: pg.set_content(doc, wait_until="networkidle", timeout=20000)
        except Exception: pg.set_content(doc)
        try: pg.evaluate("document.fonts.ready")
        except Exception: pass
        pg.wait_for_timeout(500)
        pg.locator("#k").screenshot(path=yol); b.close()
    return yol

KART_KAYNAK = {"kap": "KAP", "ozet": "KAP", "spk-basin": "SPK", "bist": "Borsa İstanbul", "sunum": "Yatırımcı sunumu"}

def kart_dogrula(kart, kaynak):
    if not isinstance(kart, dict): return ["kart eksik"]
    sat = kart.get("satirlar")
    if not isinstance(sat, list) or not (2 <= len(sat) <= 5): return ["kart 2-5 satır olmalı"]
    if not str(kart.get("baslik", "")).strip(): return ["kart başlığı boş"]
    kay = _sayilar(kaynak)
    for x in sat:
        if not (isinstance(x, list) and len(x) == 2): return ["kart satırı [etiket, değer] olmalı"]
        def _ok(d): return any(k == d or (k.startswith(d) and set(k[len(d):]) <= {"0"}) or (d.startswith(k) and k and set(d[len(k):]) <= {"0"}) for k in kay)
        for tok in re.findall(r"\d+(?:[.,/:-]\d+)*", f"{x[0]} {x[1]}"):
            if not (_ok(re.sub(r"\D", "", tok)) or all(_ok(pp) for pp in re.split(r"[.,/:-]", tok))):
                return [f"kart rakamı kaynakta yok: {tok}"]
    dump = json.dumps(kart, ensure_ascii=False)
    if re.search(r"[#$@]|https?://|www\.", dump) or ALAN.search(dump): return ["kartta bağlantı, @, # veya $ var"]
    return []

def ozet_karti(hisse, kaynak, kart):
    """Özet kartı (1080x1350, koyu, SmartCüzdan tarzı); marka veya kullanıcı adı yok."""
    from playwright.sync_api import sync_playwright
    yol = os.path.join(BASE, "sonarbist_ozet_karti.png")
    tarih = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%d.%m.%Y")
    et = KART_KAYNAK.get(kaynak, "KAP")
    bas = html.escape(str(kart["baslik"])[:70])
    sat = "".join('<div class="r"><div class="l">%s</div><div class="v" style="font-size:%dpx">%s</div></div>' % (
        html.escape(str(a)), 54 if len(str(d)) <= 22 else 42, html.escape(str(d))) for a, d in kart["satirlar"][:5])
    css = ("*{box-sizing:border-box}body{margin:0;background:#f6f8fb}"
           "#k{width:1080px;height:1350px;padding:72px;background:#f6f8fb;color:#0f172a;font-family:'Plus Jakarta Sans','Segoe UI',Arial,Helvetica,sans-serif;position:relative;overflow:hidden}"
           "#k:before{content:'';position:absolute;left:0;right:0;top:0;height:10px;background:#1d6fd8}"
           ".h{color:#1d6fd8;font-size:30px;font-weight:600;letter-spacing:.5px}"
           ".t{font-size:%dpx;font-weight:700;line-height:1.14;margin:30px 0 52px}"
           ".r{background:#ffffff;box-shadow:0 1px 3px rgba(15,23,42,.12);border-left:8px solid #1d6fd8;border-radius:10px;padding:28px 40px;margin-bottom:24px}"
           ".l{color:#64748b;font-size:30px;margin-bottom:8px;font-weight:500}.v{font-weight:700;line-height:1.15}"
           ".f{position:absolute;left:72px;bottom:56px;color:#64748b;font-size:28px}") % (66 if len(bas) <= 32 else 52)
    doc = ('<html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700&display=swap" rel="stylesheet"><style>' + css + '</style></head><body><div id="k"><div class="h">'
           + html.escape(hisse) + " · " + et + " · " + tarih + '</div><div class="t">' + bas + '</div>' + sat + '<div class="f">Kaynak: ' + et + '</div></div></body></html>')
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1080, "height": 1350})
        try: pg.set_content(doc, wait_until="networkidle", timeout=20000)
        except Exception: pg.set_content(doc)
        try: pg.evaluate("document.fonts.ready")
        except Exception: pass
        pg.wait_for_timeout(500)
        pg.locator("#k").screenshot(path=yol); b.close()
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

def x_paylas(metin, gorsel=None, yanit=None):
    """Tweet atar; (tweet_id, gorsel_hatasi) döner."""
    url = "https://api.x.com/2/tweets"; payload = {"text": metin}; ghata = None
    if yanit: payload["reply"] = {"in_reply_to_tweet_id": str(yanit)}
    if gorsel:
        try: payload["media"] = {"media_ids": [str(x_gorsel(gorsel))]}
        except Exception as e: ghata = repr(e)[:200]
    r = http(url, json.dumps(payload).encode(), {"Content-Type": "application/json", "Authorization": oauth_baslik("POST", url, {}, XK["ck"], XK["cs"], XK["tk"], XK["ts"])})
    return json.loads(r)["data"]["id"], ghata



# ---- bilanço sonrası: güçlü yönler / dikkat edilecekler (3 Kas: THYAO ile test) ----
def _yz(x): return f"%{abs(x):.1f}".replace(".", ",")

def fr_analiz_olc(rows):
    """XBRL satırlarından gösterge listesi üretir; yön (güçlü/dikkat/nötr) kodla belirlenir. Dönüş: [{ad, deger, kars, tur}]"""
    rows = [r for r in rows if len(r) >= 3 and isinstance(r[1], (int, float))]
    def bul(*adlar, onek=False):
        for ad in adlar:
            for r in rows:
                l = _k(r[0])
                if (l.startswith(ad) if onek else l == ad) and isinstance(r[2], (int, float)): return r
        return None
    O = []
    def ekle(ad, deger, kars, tur): O.append({"ad": ad, "deger": deger, "kars": kars, "tur": tur})
    has = bul("hasılat"); brut = bul("brüt kar (zarar)", "brüt kâr (zarar)", "brüt kar", onek=True)
    esas = bul("esas faaliyet karı (zararı)", "esas faaliyet kârı (zararı)", "esas faaliyet karı", onek=True)
    net = bul("net dönem karı veya zararı", "dönem karı (zararı)")
    if not has or not net: return []
    c, o = has[1], has[2]
    if o:
        y = (c - o) / abs(o) * 100
        ekle("Hasılat", _tl(c), f"geçen yılın aynı dönemi {_tl(o)}, {'artış' if y >= 0 else 'azalış'} {_yz(y)}", "guclu" if y >= 5 else "dikkat" if y <= -5 else "notr")
    def marj(r): return r[1] / has[1] * 100, (r[2] / has[2] * 100 if has[2] else None)
    for ad, r in (("Brüt kâr marjı", brut), ("Esas faaliyet kâr marjı", esas)):
        if not r or not has[1]: continue
        m1, m0 = marj(r)
        if m0 is None: continue
        d = m1 - m0
        ekle(ad, _yz(m1), f"geçen yılın aynı dönemi {_yz(m0)}", "guclu" if d >= 1 else "dikkat" if d <= -1 else "notr")
    if esas and esas[1] < 0: ekle("Esas faaliyet sonucu", "zarar " + _tl(abs(esas[1])), f"geçen yılın aynı dönemi {_tl(esas[2])}", "dikkat")
    d_, yon = _deg(net[1], net[2])
    if d_ and yon: ekle("Net dönem kârı", _tl(net[1]), f"geçen yılın aynı dönemi {_tl(net[2])}, {d_}", "guclu" if yon == "up" else "dikkat")
    par = bul("net parasal pozisyon kazançları (kayıpları)", "net parasal pozisyon", onek=True)
    if par and par[1] > 0 and net[1] > 0 and par[1] >= net[1]:
        ekle("Net parasal kazanç", _tl(par[1]), f"net dönem kârı {_tl(net[1])}, kâr parasal kazançtan geliyor", "dikkat")
    fg = bul("finansman giderleri")
    if fg and fg[2]:
        y = (abs(fg[1]) - abs(fg[2])) / abs(fg[2]) * 100
        if abs(y) >= 10: ekle("Finansman gideri", _tl(abs(fg[1])), f"geçen yılın aynı dönemi {_tl(abs(fg[2]))}, {'azalış' if y < 0 else 'artış'} {_yz(y)}", "guclu" if y < 0 else "dikkat")
    kv = bul("kısa vadeli borçlanmalar"); ukv = bul("uzun vadeli borçlanmaların kısa vadeli kısımları"); uv = bul("uzun vadeli borçlanmalar")
    nk = bul("nakit ve nakit benzerleri"); fy = bul("finansal yatırımlar")
    if nk and (kv or uv):
        def top(i): return sum((r[i] or 0) for r in (kv, ukv, uv) if r) - (nk[i] or 0) - ((fy[i] or 0) if fy else 0)
        n1, n0 = top(1), top(2)
        if n1 <= 0: ekle("Net nakit", _tl(abs(n1)), "borçtan fazla nakit ve finansal yatırım var", "guclu")
        elif n0 > 0:
            y = (n1 - n0) / n0 * 100
            ekle("Net borç", _tl(n1), f"önceki yıl sonu {_tl(n0)}, {'azalış' if y < 0 else 'artış'} {_yz(y)}", "guclu" if y <= -5 else "dikkat" if y >= 5 else "notr")
    ok = bul("işletme faaliyetlerinden nakit akışları", "işletme faaliyetlerinden sağlanan nakit akışları")
    if ok:
        if ok[1] < 0: ekle("İşletme nakit akışı", "eksi " + _tl(abs(ok[1])), f"geçen yılın aynı dönemi {_tl(ok[2])}", "dikkat")
        elif ok[2] and ok[1] >= ok[2]: ekle("İşletme nakit akışı", _tl(ok[1]), f"geçen yılın aynı dönemi {_tl(ok[2])}", "guclu")
    ozk = bul("ana ortaklığa ait özkaynaklar", "özkaynaklar")
    if ozk and ozk[2]:
        y = (ozk[1] - ozk[2]) / abs(ozk[2]) * 100
        if abs(y) >= 3: ekle("Özkaynaklar", _tl(ozk[1]), f"önceki yıl sonu {_tl(ozk[2])}, {'artış' if y > 0 else 'azalış'} {_yz(y)}", "guclu" if y > 0 else "dikkat")
    da = bul("dönen varlıklar", "toplam dönen varlıklar"); kyl = bul("kısa vadeli yükümlülükler", "toplam kısa vadeli yükümlülükler")
    if da and kyl and kyl[1]:
        cr = da[1] / kyl[1]
        if cr >= 1.5 or cr < 1: ekle("Cari oran", f"{cr:.2f}".replace(".", ","), "dönen varlıklar / kısa vadeli yükümlülükler", "guclu" if cr >= 1.5 else "dikkat")
    return O

AN_SYS = """Sen SonarBIST'in editörüsün. Bir şirketin bilançosundan çıkan göstergeleri okuyup "güçlü yönler" ve "dikkat edilecekler" olarak iki kısa liste yazarsın. Yalnız JSON döndür.
Girdi satırları [guclu], [dikkat] veya [notr] etiketlidir; etiketi kod belirledi. Güçlü yönlere yalnız [guclu], dikkat edilecekler listesine yalnız [dikkat] satırlarından seç; [notr] kullanma. En önemli en çok 3 güçlü ve en çok 3 dikkat maddesini seç (daha az varsa daha az; bir taraf boşsa o tarafı boş bırak).
Rakamlar satırlarda yazdığı gibi aynen kullanılır (örn. "122,3 milyar TL", "%26,7"); kendin rakam hesaplama, yuvarlama veya yeni rakam ekleme. Tahmin, tavsiye, al/sat, hedef fiyat, "fırsat", "yükselir/düşer" yasak; yalnız bilançodaki durumu söyle. Dikkat maddeleri risk dili değil olgu dili kullanır ("Net borç arttı", "kâr parasal kazançtan geliyor").
Tweet: ilk sözcük hisse kodu, parantez içinde şirket adı: "THYAO (Türk Hava Yolları) bilançosunda öne çıkanlar." Sonra boş satır, "Güçlü yönler" başlığı ve her biri "• " ile başlayan kısa maddeler (rakamlı), boş satır, "Dikkat edilecekler" başlığı ve "• " maddeleri. Boş olan tarafın başlığını yazma. Noktalı virgül, emoji, hashtag, bağlantı, $ yok. En çok 270 karakter; kısa maddeler yaz.
Kart: her madde için {"ad": "en çok 4 kelime", "deger": "en çok 22 karakter, satırdaki değer", "not": "en çok 40 karakter kısa açıklama, rakam yazılırsa satırdaki gibi"}.
Çıktı: {"tweet": "...", "guclu": [{"ad":"","deger":"","not":""}], "dikkat": [{"ad":"","deger":"","not":""}]}"""

def analiz_dogrula(p, kaynak, hisse):
    h = dogrula(p.get("tweet", ""), kaynak, [], hisse)
    g, d = p.get("guclu") or [], p.get("dikkat") or []
    if not isinstance(g, list) or not isinstance(d, list) or not (g or d) or len(g) > 3 or len(d) > 3: return h + ["kart maddeleri 0-3 + 0-3 olmalı, en az bir madde"]
    for x in g + d:
        if not (isinstance(x, dict) and all(isinstance(x.get(a), str) and x.get(a).strip() for a in ("ad", "deger", "not"))): return h + ["kart maddesi ad/deger/not içermeli"]
        if len(x["deger"]) > 24 or len(x["not"]) > 44 or len(x["ad"]) > 40: return h + [f"kart maddesi çok uzun: {x['ad']}"]
        h += kart_dogrula({"baslik": "x", "satirlar": [[x["ad"], x["deger"] + " " + x["not"]]] * 2}, kaynak)
    return h

def analiz_karti(hisse, p):
    """Güçlü yönler (yeşil) / dikkat edilecekler (kırmızı) kartı, 1080x1350, açık zemin."""
    from playwright.sync_api import sync_playwright
    yol = os.path.join(BASE, "sonarbist_analiz_karti.png")
    tarih = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%d.%m.%Y")
    n = len(p.get("guclu") or []) + len(p.get("dikkat") or [])
    kucuk = n > 4
    def bolum(liste, sinif, baslik, isaret):
        if not liste: return ""
        s = '<div class="b %s"><span class="ik">%s</span>%s</div>' % (sinif, isaret, baslik)
        for x in liste:
            s += '<div class="r %s"><div class="rl"><div class="a">%s</div><div class="n">%s</div></div><div class="v">%s</div></div>' % (sinif, html.escape(x["ad"]), html.escape(x["not"]), html.escape(x["deger"]))
        return s
    govde = bolum(p.get("guclu"), "g", "GÜÇLÜ YÖNLER", "✓") + bolum(p.get("dikkat"), "d", "DİKKAT EDİLECEKLER", "!")
    css = ("*{box-sizing:border-box}body{margin:0;background:#f6f8fb}"
           "#k{width:1080px;height:1350px;padding:64px 72px;background:#f6f8fb;color:#0f172a;font-family:'Plus Jakarta Sans','Segoe UI',Arial,Helvetica,sans-serif;position:relative;overflow:hidden}"
           "#k:before{content:'';position:absolute;left:0;right:0;top:0;height:12px;background:linear-gradient(90deg,#16a34a 0 50%,#dc2626 50% 100%)}"
           ".h{color:#1d6fd8;font-size:30px;font-weight:600;letter-spacing:.5px}"
           ".t{font-size:58px;font-weight:800;line-height:1.1;margin:22px 0 30px}"
           ".b{display:flex;align-items:center;font-size:30px;font-weight:800;letter-spacing:1px;margin:18px 0 14px}"
           ".b.g{color:#15803d}.b.d{color:#b91c1c}"
           ".ik{display:inline-flex;align-items:center;justify-content:center;width:46px;height:46px;border-radius:50%;color:#fff;font-size:28px;margin-right:16px}"
           ".b.g .ik{background:#16a34a}.b.d .ik{background:#dc2626}"
           ".r{display:flex;justify-content:space-between;align-items:center;gap:24px;border-radius:14px;padding:" + ("16px 30px" if kucuk else "26px 34px") + ";margin-bottom:" + ("12px" if kucuk else "18px") + "}"
           ".r.g{background:#ecfdf5;border-left:10px solid #16a34a}.r.d{background:#fef2f2;border-left:10px solid #dc2626}"
           ".a{font-size:" + ("30px" if kucuk else "34px") + ";font-weight:700}.n{color:#475569;font-size:" + ("24px" if kucuk else "27px") + ";margin-top:4px}"
           ".v{font-size:" + ("40px" if kucuk else "46px") + ";font-weight:800;white-space:nowrap;text-align:right}"
           ".r.g .v{color:#15803d}.r.d .v{color:#b91c1c}"
           ".f{position:absolute;left:72px;bottom:44px;color:#64748b;font-size:26px}")
    doc = ('<html><head><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet"><style>' + css + '</style></head><body><div id="k"><div class="h">'
           + html.escape(hisse) + " · KAP · " + tarih + '</div><div class="t">Bilanço: öne çıkanlar</div>' + govde + '<div class="f">Kaynak: KAP finansal rapor</div></div></body></html>')
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1080, "height": 1350})
        try: pg.set_content(doc, wait_until="networkidle", timeout=20000)
        except Exception: pg.set_content(doc)
        try: pg.evaluate("document.fonts.ready")
        except Exception: pass
        pg.wait_for_timeout(500)
        pg.locator("#k").screenshot(path=yol); b.close()
    return yol

def analiz_isle(token, chat, hisse, kid, baslik="Finansal rapor", yanit=None, rows=None):
    """Bilanço sonrası ikinci tweet. yanit: ilk (bilanço) tweetinin id'si; verilirse yanıt olarak atılır."""
    if os.path.exists(DURDUR) or not KEY: return None
    kayit = _js(KAYIT); anahtar = f"analiz-{kid}"
    if any(k.get("id") == anahtar for k in kayit): return None
    k = {"id": anahtar, "hisse": hisse, "baslik": baslik[:150], "t": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "mod": "golge", "tur": "bilanço analizi"}
    try:
        if rows is None:
            import sys as _s
            _s.path.insert(0, os.path.join(BASE, "araclar"))
            import xbrl_cek
            rows = xbrl_cek.rows(http(f"https://www.kap.org.tr/tr/Bildirim/{kid}", headers=UA, timeout=90).decode("utf-8", "ignore"))
            rows = _olcekle(rows, _olcek(rows, hisse))
        olc = fr_analiz_olc(rows)
        if not any(x["tur"] == "guclu" for x in olc) and not any(x["tur"] == "dikkat" for x in olc):
            k.update(durum="analiz_atlandi", sebep="güçlü/dikkat göstergesi çıkmadı"); kayit.append(k); _kaydet(kayit); return k
        satir = "\n".join(f"[{x['tur']}] {x['ad']}: {x['deger']} ({x['kars']})" for x in olc)
        buy = buyukluk(hisse)
        kaynak_m = satir + " " + buy
        u = f"Şirket: {hisse}\nBüyüklükler (Sonar): {buy}\nBaşlık: {baslik}\n\nGöstergeler:\n{satir}"
        hata = None; p = {}; h = []
        for deneme in range(2):
            raw = claude(SONNET, AN_SYS, u + (f"\n\nÖnceki taslak reddedildi, düzelt: {hata}" if hata else ""), 900); p = jparse(raw)
            h = analiz_dogrula(p, kaynak_m, hisse) if p.get("tweet") else ["yanıt çözülemedi"]
            if not h: break
            hata = "; ".join(h)
        if h:
            k.update(durum="analiz_hata", sebep=hata, tweet_red=p.get("tweet")); kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST · bilanço analizi doğrulamadan geçmedi · {hisse}\nNeden: {hata}\nTaslak: {p.get('tweet')}"); return k
        try: foto, ghata = analiz_karti(hisse, p), None
        except Exception as e: foto, ghata = None, "kart: " + repr(e)[:120]
        k.update(tweet=p["tweet"], kart=p, goruntu=bool(foto), goruntu_hata=ghata)
        if MOD == "canli" and x_hazir():
            k["mod"] = "canli"; tid, xg = x_paylas(p["tweet"], foto, yanit)
            k.update(durum="analiz_paylasildi", tweet_id=tid, x_gorsel_hata=xg); kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST PAYLAŞILDI (bilanço analizi) · {hisse}\nhttps://x.com/{HESAP}/status/{tid}\n\n{p['tweet']}" + (f"\n(görsel yok: {ghata})" if ghata else "") + (f"\n(X görsel yüklemesi başarısız: {xg})" if xg else ""), foto)
        else:
            k["durum"] = "analiz_taslak"; kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST bilanço analizi taslağı (gölge) · {hisse}\n\n{p['tweet']}", foto)
        if foto:
            try: os.remove(foto)
            except Exception: pass
        return k
    except Exception as e:
        k.update(durum="analiz_hata", sebep=repr(e)[:600])
        try:
            kayit.append(k); _kaydet(kayit); tg(token, chat, f"SonarBIST bilanço analizi hata · {hisse}\n{repr(e)[:300]}")
        except Exception: pass
        return k

def analiz_kanca(token, chat):
    """bekci/sonarbist_analiz.json: [[hisse, kapId(, başlık)], ...] listesindeki bilançoların analiz tweetini tek başına atar (test)."""
    yol = os.path.join(BASE, "sonarbist_analiz.json")
    if not os.path.exists(yol): return
    try: liste = json.load(open(yol, encoding="utf-8"))
    except Exception: return
    try: os.remove(yol)
    except Exception: pass
    for e in liste:
        hisse, kid = e[0], e[1]; baslik = e[2] if len(e) > 2 else "Finansal rapor"
        kayit = [x for x in _js(KAYIT) if x.get("id") != f"analiz-{kid}"]; _kaydet(kayit)
        analiz_isle(token, chat, hisse, kid, baslik)

# ---- Sonar'da yayına alınan özetler (public/haber/<hisse>-<kapid>) ----
def ozetleri_tara(token, chat):
    """Cagri bir haber özetini yayına alınca public/haber/<hisse>-<id>/ oluşur; SonarBIST o özetin girişini (meta açıklama)
    ve KAP metnini kaynak alıp tweet atar. İlk çalışmada mevcut sayfalar sessizce 'görüldü' sayılır."""
    if os.path.exists(DURDUR) or not KEY: return
    try: analiz_kanca(token, chat)
    except Exception: pass
    kok = os.path.join(BASE, "..", "public", "haber")
    if not os.path.isdir(kok): return
    gp = os.path.join(BASE, "sonarbist_ozet_gorulen.json")
    mevcut = sorted(d for d in os.listdir(kok) if os.path.isfile(os.path.join(kok, d, "index.html")))
    if not os.path.exists(gp):
        json.dump(mevcut, open(gp, "w", encoding="utf-8")); return
    gor = _js(gp)
    # tek seferlik: PAHOL özeti belirteç sınırı yüzünden yazılamadı, yeniden dene
    ky = _js(KAYIT)
    esk = [k for k in ky if k.get("id") == "ozet-1691690" and str(k.get("tweet_id")) == "2117626345618375133"]
    if esk:  # Cagri bu tweeti sildi (3 Kas): olumsuz örnek olarak sakla, aynı özeti yeni biçimle yeniden at
        esk[0].update(id="ozet-1691690-silindi", silindi=True); _kaydet(ky); gor = [x for x in gor if x != "pahol-1691690"]
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
            olc = fr_olc(kid, hisse)
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
        saat = [x for x in kayit if x.get("durum") in ("taslak", "paylasildi") and x["t"] > (simdi - datetime.timedelta(hours=1)).isoformat()]
        gun = [x for x in kayit if x.get("durum") in ("taslak", "paylasildi") and x["t"][:10] == simdi.date().isoformat()]
        if simdi < ACIK_TAVAN_SON: pass
        elif len(saat) >= SAAT_TAVAN or len(gun) >= GUN_TAVAN:
            k.update(durum="tavan", sebep="saat/gün tavanı"); kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST · tavan nedeniyle sıraya alınmadı (puan {puan}) · {hisse}\n{baslik[:200]}\n{link}"); return k
        gecmis = [x["tweet"] for x in kayit if x.get("tweet")]
        kaynak_m = metin + " " + buy; hata = None; taslak = {}; kh = []
        for deneme in range(2):
            taslak = yaz(hisse, baslik, metin, buy, gecmis, hata, kayit)
            h = dogrula(taslak.get("tweet", ""), kaynak_m, gecmis, hisse)
            kh = [] if fr else kart_dogrula(taslak.get("kart"), kaynak_m)
            if not h and not kh: break
            hata = "; ".join(h + kh)
        if h:
            k.update(durum="dogrulama_hatasi", sebep=hata, tweet_red=taslak.get("tweet")); kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST · taslak doğrulamadan geçmedi (puan {puan}) · {hisse}\n{baslik[:160]}\nNeden: {hata}\nTaslak: {taslak.get('tweet')}\n{link}"); return k
        if fr:
            try: foto, ghata = fr_kart(hisse, baslik, olc), None
            except Exception as e: foto, ghata = None, "kart: " + repr(e)[:120]
        else:
            foto, ghata = (None, None)
            if kaynak == "ozet":
                foto, ghata = site_karti(hisse, kid)  # panelde üretilen kart
            if not foto:
                if kh: ghata = "kart doğrulanamadı: " + "; ".join(kh)[:150]
                else:
                    try: foto, ghata = ozet_karti(hisse, kaynak, taslak["kart"]), None
                    except Exception as e: ghata = "kart: " + repr(e)[:150]
        k.update(durum="taslak", tweet=taslak["tweet"], kart=taslak.get("kart"), goruntu=bool(foto), goruntu_hata=ghata)
        if MOD == "canli" and x_hazir():
            k["mod"] = "canli"; tid, xg = x_paylas(taslak["tweet"], foto)
            k.update(durum="paylasildi", tweet_id=tid, x_gorsel_hata=xg); kayit.append(k); _kaydet(kayit)
            tg(token, chat, f"SonarBIST PAYLAŞILDI · puan {puan} · {hisse}\nhttps://x.com/{HESAP}/status/{tid}\n\n{taslak['tweet']}\n\nGerekçe: {p.get('gerekce','')}\n{link}" +
               (f"\n(görsel yok: {ghata})" if ghata else "") + (f"\n(X görsel yüklemesi başarısız, metinle atıldı: {xg})" if xg else "") + "\nGereksizse X'ten sil ve bana 'sildim' de.", foto)
            if foto:
                try: os.remove(foto)
                except Exception: pass
            if fr and olc:
                try: analiz_isle(token, chat, hisse, kid, baslik, tid, olc.get("rows"))
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
