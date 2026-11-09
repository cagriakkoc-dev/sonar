"""Veri tazeliği denetimi (yol haritası bölüm 13, adım 2) · 9 Kas 2026.
Açık sitenin verisini (public/index.html) ve bekçi kuyruğunu okur; her şirket ve veri akışı için
"son güncelleme / beklenen" karşılaştırması yapar → bekci/tazelik.json.
Yeni çıkan bayat kalemler Telegram'a tek mesaj olarak gider; pazartesi haftalık rapor.
Kullanım: python3 bekci/tazelik.py [--kuru]   (--kuru: Telegram yok, yalnız ekrana)
Beklenen dönem kuralı (SPK süreleri + 2 gün pay): 3 ve 9 aylık rapor dönem sonundan 42 gün, 6 aylık 52 gün, yıllık 72 gün sonra beklenir.
"""
import json, os, re, sys, datetime, urllib.request

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(KOK, "bekci")
CIKTI = os.path.join(B, "tazelik.json")
KURU = "--kuru" in sys.argv
BUGUN = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=3)  # Türkiye saati
GECIKME = {3: 42, 6: 52, 9: 42, 12: 72}


def ceyrek_sonu(p):
    y, m = map(int, p.split("-")); return datetime.date(y, m, 30 if m in (6, 9) else 31)


def onceki(p, n=1):
    y, m = map(int, p.split("-"))
    for _ in range(n):
        m -= 3
        if m <= 0: m += 12; y -= 1
    return f"{y}-{m:02d}"


def beklenen(bugun):
    """Bugün itibarıyla sitede olması gereken en son finansal dönem."""
    m = (bugun.month - 1) // 3 * 3
    p = f"{bugun.year}-{m:02d}" if m else f"{bugun.year - 1}-12"
    for _ in range(5):
        if ceyrek_sonu(p) + datetime.timedelta(days=GECIKME[int(p[5:])]) <= bugun: return p
        p = onceki(p)
    return p


def veri():
    h = open(os.path.join(KOK, "public", "index.html"), encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="data">(.*?)</script>', h, re.S)
    return json.loads(m.group(1))


def tarih(s):
    try: return datetime.datetime.strptime(s, "%d.%m.%Y %H:%M:%S")
    except Exception: return None


def denetle():
    D = veri(); bugun = BUGUN.date(); P0 = beklenen(bugun)
    sorun = []  # {k: anahtar, tur, t, metin}
    ekle = lambda k, tur, t, metin: sorun.append({"k": k, "tur": tur, "t": t, "metin": metin})
    kuyruk = json.load(open(os.path.join(B, "kuyruk.json"), encoding="utf-8"))
    bekleyen = [x for x in kuyruk if x.get("durum") == "bekliyor"]
    elle = [x for x in kuyruk if x.get("durum") == "elle"]
    fr_bek = {}
    for x in bekleyen:
        if x.get("tur") == "Finansal rapor": fr_bek.setdefault(x.get("hisse"), []).append(x)
    sirket = []
    for c in D["companies"]:
        t = c["t"]; P = (c.get("periods") or ["?"])[-1]
        r = {"t": t, "grp": c.get("grp") or c.get("sector"), "son": P}
        if P < P0:
            ek = f" (bekçi kuyruğunda {len(fr_bek[t])} finansal rapor bekliyor)" if t in fr_bek else ""
            ekle(f"fin:{t}:{P0}", "rakam", t, f"{t}: son dönem {P}, beklenen {P0}{ek}")
        rat = c.get("rat"); rp = (rat[-1]["p"] if isinstance(rat, list) and rat else (rat or {}).get("p"))
        r["oran"] = rp
        if rp and rp < P: ekle(f"rat:{t}:{P}", "oran", t, f"{t}: oranlar {rp}, finansallar {P}")
        S = [s["p"] for s in c.get("summaries") or [] if s.get("p")]
        r["ozet"] = max(S) if S else None
        if S and max(S) < P: ekle(f"ozet:{t}:{P}", "özet", t, f"{t}: dönem özeti {max(S)}, finansallar {P}")
        dt = c.get("divT") or {}
        if dt.get("son") and dt["son"] < P: ekle(f"tem:{t}:{P}", "temettü", t, f"{t}: temettü tahmini {dt['son']} verisiyle, finansallar {P}")
        son_m = {}
        for k in c.get("kpi") or []:
            if k.get("k") != "q" or not k.get("p"): continue
            if k["p"] > son_m.get(k["m"], ""): son_m[k["m"]] = k["p"]
        geride = sorted(m for m, p in son_m.items() if p == onceki(P))
        r["gosterge"] = {"sayi": len(son_m), "geride": geride}
        if geride: ekle(f"kpi:{t}:{P}", "gösterge", t, f"{t}: {len(geride)} sektöre özgü gösterge {onceki(P)}'de kaldı ({', '.join(geride[:3])}{'…' if len(geride) > 3 else ''})")
        sirket.append(r)
    # otomasyon sağlığı
    eski = [x for x in bekleyen if (d := tarih(x.get("tarih") or "")) and (BUGUN - d).total_seconds() > 6 * 3600]
    dur = {}
    try: dur = json.load(open(os.path.join(B, "otomatik_durum.json"), encoding="utf-8"))
    except Exception: pass
    if eski:
        son = dur.get("zaman", "hiç çalışmadı")
        ekle(f"oto:{bugun}", "otomasyon", "-", f"Kuyrukta 6 saatten eski {len(eski)} kayıt var (en eskisi {min(x['tarih'] for x in eski)}); otomatik özetin son çalışması: {son}")
    if dur.get("rc"):
        ekle(f"otorc:{dur.get('zaman')}", "otomasyon", "-", f"Otomatik özet hata koduyla bitti (rc={dur['rc']}, {dur.get('zaman')})")
    if elle: ekle(f"elle:{len(elle)}", "elle", "-", f"Kuyrukta elle bakılacak {len(elle)} kayıt: " + ", ".join(f"{x.get('hisse')} {x['id']}" for x in elle[:6]))
    return {"zaman": BUGUN.strftime("%Y-%m-%d %H:%M"), "beklenen_donem": P0,
            "ozet": {"sirket": len(sirket), "guncel": sum(r["son"] >= P0 for r in sirket), "bekleyen_kuyruk": len(bekleyen), "elle": len(elle),
                     "sorun": {tur: sum(s["tur"] == tur for s in sorun) for tur in sorted({s["tur"] for s in sorun})}},
            "sorunlar": sorun, "sirketler": sirket}


def telegram(metin):
    tok = os.environ.get("TELEGRAM_TOKEN", "").strip()
    try: chat = json.load(open(os.path.join(B, "state.json"))).get("chat_id")
    except Exception: chat = None
    if KURU or not tok or not chat:
        print("--- Telegram (gönderilmedi) ---\n" + metin); return
    for i in range(0, len(metin), 3800):
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage",
                                     json.dumps({"chat_id": chat, "text": metin[i:i + 3800], "disable_web_page_preview": True}).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30)


def main():
    yeni = denetle()
    try: once = json.load(open(CIKTI, encoding="utf-8"))
    except Exception: once = {"sorunlar": []}
    eski_k = {s["k"] for s in once.get("sorunlar", [])}
    taze = [s for s in yeni["sorunlar"] if s["k"] not in eski_k]
    yeni["yeni"] = [s["k"] for s in taze]
    json.dump(yeni, open(CIKTI, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    o = yeni["ozet"]
    bas = f"Sonar tazelik · {yeni['zaman']} · beklenen dönem {yeni['beklenen_donem']} · güncel {o['guncel']}/{o['sirket']} şirket · kuyrukta {o['bekleyen_kuyruk']} bekleyen"
    print(bas); print(json.dumps(o["sorun"], ensure_ascii=False))
    if BUGUN.weekday() == 0 and BUGUN.hour < 12 and not once.get("hafta") == BUGUN.strftime("%G-%V"):
        satir = [bas, "Haftalık rapor · sorun türleri: " + ", ".join(f"{k} {v}" for k, v in o["sorun"].items())]
        satir += ["• " + s["metin"] for s in yeni["sorunlar"] if s["tur"] in ("otomasyon", "elle", "rakam")][:40]
        telegram("\n".join(satir)); yeni["hafta"] = BUGUN.strftime("%G-%V")
        json.dump(yeni, open(CIKTI, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    elif taze:
        oncelik = {"otomasyon": 0, "elle": 1, "rakam": 2, "özet": 3, "oran": 4, "temettü": 5, "gösterge": 6}
        taze.sort(key=lambda s: (oncelik.get(s["tur"], 9), s["t"]))
        satir = [bas, f"Yeni {len(taze)} bayat kalem:"] + ["• " + s["metin"] for s in taze[:30]]
        if len(taze) > 30: satir.append(f"… ve {len(taze) - 30} kalem daha (bekci/tazelik.json)")
        telegram("\n".join(satir))
    if "hafta" not in yeni and once.get("hafta"):
        yeni["hafta"] = once["hafta"]; json.dump(yeni, open(CIKTI, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
