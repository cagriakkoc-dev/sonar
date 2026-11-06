"""veri/fon/ham/<KOD>/<dönem>.txt metinlerini (indirmeden) güncel ayrıştırıcıyla yeniden işler; pdr JSON'unu günceller.
Doğrulaması tutan raporların ham metni silinir (depo hafif kalsın)."""
import os, json, glob, sys
sys.path.insert(0, os.path.dirname(__file__))
from pdr_ayristir import ayristir
VERI = os.path.join(os.path.dirname(__file__), "..", "..", "veri", "fon")
iyi = kotu = 0
for t in sorted(glob.glob(os.path.join(VERI, "ham", "*", "*.txt"))):
    kod, donem = t.split(os.sep)[-2], os.path.basename(t)[:-4]
    hp = os.path.join(VERI, "pdr", kod, donem + ".json")
    eski = json.load(open(hp)) if os.path.exists(hp) else {}
    metin = open(t, encoding="utf-8").read()
    if len(metin.strip()) < 200: kotu += 1; continue
    a = ayristir(metin)
    a.update({k: eski[k] for k in ("bildirim", "yayin", "ekler") if k in eski}); a.update(kod=kod, donem=donem)
    os.makedirs(os.path.dirname(hp), exist_ok=True); json.dump(a, open(hp, "w"), ensure_ascii=False, indent=1)
    if a["dogrulama"]["tutuyor"]: iyi += 1; os.remove(t)
    else: kotu += 1
print(f"yeniden ayrıştırma: {iyi} rapor düzeldi, {kotu} rapor hâlâ tutmuyor / metinsiz")
