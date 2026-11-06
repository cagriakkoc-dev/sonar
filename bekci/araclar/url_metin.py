"""bekci/istek/metin_url.txt içindeki PDF URL'lerinin tüm sayfa metinlerini çıkarır.
Çıktı: bekci/metin/u_<sha1(url)[:12]>.json -> {"url":..., "sayfa_sayisi":n, "sayfalar":{"1":"..."}}"""
import hashlib, json, os, subprocess, tempfile, time, urllib.parse, urllib.request
GEVSEK_SSL = {"www.fordotosan.com.tr"}  # sunucu ara sertifikayı göndermiyor (bekci/sunum.py ile aynı; yalnız açık belgeler)
B = os.path.join(os.path.dirname(__file__), '..')
OUT = os.path.join(B, 'metin'); os.makedirs(OUT, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36'}
for u in open(os.path.join(B, 'istek', 'metin_url.txt')):
    u = u.strip()
    if not u or u.startswith('#'):
        continue
    p = os.path.join(OUT, 'u_' + hashlib.sha1(u.encode()).hexdigest()[:12] + '.json')
    if os.path.exists(p):
        continue
    try:
        q = urllib.parse.quote(u, safe=':/?&=%#~+,;@!$\'()*')
        _c = __import__('ssl')._create_unverified_context() if urllib.parse.urlparse(u).hostname in GEVSEK_SSL else None
        b = urllib.request.urlopen(urllib.request.Request(q, headers=UA), timeout=60, context=_c).read()
        k = b.find(b'%PDF', 0, 400)
        if k > 0: b = b[k:]
        if b[:4] != b'%PDF':
            print('pdf değil', u[:120]); continue
        with tempfile.NamedTemporaryFile(suffix='.pdf') as f:
            f.write(b); f.flush()
            t = subprocess.run(['pdftotext', '-layout', f.name, '-'], capture_output=True, text=True).stdout
        pg = t.split('\f')
        json.dump({'url': u, 'sayfa_sayisi': len(pg), 'sayfalar': {str(i + 1): x for i, x in enumerate(pg) if x.strip()}},
                  open(p, 'w'), ensure_ascii=False)
        print('ok', len(pg), u[:120])
    except Exception as e:
        print('hata', repr(e)[:160], u[:120])
    time.sleep(1)
