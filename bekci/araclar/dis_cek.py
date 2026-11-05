"""Dış URL'leri indirir. DIS="ad1|url1;;ad2|url2" -> bekci/dis/<ad>. Var olan dosya atlanır (her push tüm listeyi yeniden indirip 10 dk sınırına takılıyordu, 5 Kas)."""
import os, re, time, urllib.request
T0 = time.time()
OUT = os.path.join(os.path.dirname(__file__), "..", "dis"); os.makedirs(OUT, exist_ok=True)
_D = os.environ.get("DIS_DOSYA")   # dosyadan okuma (ortam değişkeni 128 KB sınırını aşıyordu, 5 Kas)
_P = [l.strip() for l in open(_D, encoding="utf-8") if "|" in l and not l.startswith("#")] if _D else os.environ.get("DIS", "").split(";;")
for parca in filter(None, _P):
    ad, url = parca.split("|", 1)
    if os.path.exists(os.path.join(OUT, ad.strip())): continue
    if time.time() - T0 > 360: print("süre doldu; kalanlar sonraki çalıştırmada"); break   # zaten indirilmiş (yenilemek için dosyayı sil ya da yeni ad ver)
    try:
        b = urllib.request.urlopen(urllib.request.Request(url.strip(), headers={"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/124 Safari/537.36"}), timeout=60).read()
        if ad.strip().startswith("kapb_"):   # KAP bildirim sayfası ~5 MB: yalnız başlık ve ek dosya kimlikleri saklanır
            t = b.decode("utf-8", "ignore"); m = re.search(r"<title>(.*?)</title>", t, re.S)
            ids = list(dict.fromkeys(re.findall(r"file/download/([0-9a-f]{32})", t)))
            b = ("<title>" + (m.group(1).strip() if m else "") + "</title>\n" + "\n".join("file/download/" + i for i in ids) + "\n").encode()
        open(os.path.join(OUT, ad.strip()), "wb").write(b); print(ad, len(b))
    except Exception as e:
        print(ad, "hata", repr(e)[:150])
