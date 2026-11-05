"""Dış URL'leri indirir. DIS="ad1|url1;;ad2|url2" -> bekci/dis/<ad>. Var olan dosya atlanır (her push tüm listeyi yeniden indirip 10 dk sınırına takılıyordu, 5 Kas)."""
import os, urllib.request
OUT = os.path.join(os.path.dirname(__file__), "..", "dis"); os.makedirs(OUT, exist_ok=True)
for parca in filter(None, os.environ.get("DIS", "").split(";;")):
    ad, url = parca.split("|", 1)
    if os.path.exists(os.path.join(OUT, ad.strip())): continue   # zaten indirilmiş (yenilemek için dosyayı sil ya da yeni ad ver)
    try:
        b = urllib.request.urlopen(urllib.request.Request(url.strip(), headers={"User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/124 Safari/537.36"}), timeout=60).read()
        open(os.path.join(OUT, ad.strip()), "wb").write(b); print(ad, len(b))
    except Exception as e:
        print(ad, "hata", repr(e)[:150])
