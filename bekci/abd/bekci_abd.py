#!/usr/bin/env python3
"""Sonar ABD bekçisi · SEC EDGAR yeni başvuru takibi → Telegram (SonarBot).

Takip edilen: 10-Q, 10-K ve önemli 8-K'ler (2.02 kazanç duyurusu, 1.01 önemli sözleşme, 2.01 satın alma/satış,
5.02 yönetici değişikliği, 7.01/8.01 duyuru). Yeni 10-Q/10-K gelince o şirketin verisi edgar.py ile yenilenir.
Durum: bekci/abd/durum.json. Telegram sohbeti: bekci/state.json chat_id (KAP bekçisiyle aynı).
"""
import json, os, sys, time, urllib.request, datetime as dt

BURA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURA)
import edgar  # noqa: E402

KOK = edgar.KOK
DURUM = os.path.join(BURA, "durum.json")
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
MADDE = {"2.02": "Kazanç duyurusu", "1.01": "Önemli sözleşme", "2.01": "Satın alma / satış", "5.02": "Yönetici değişikliği",
         "7.01": "Kamuya duyuru (Reg FD)", "8.01": "Diğer önemli olay"}
FORM = {"10-Q": "Çeyrek raporu (10-Q)", "10-K": "Yıllık rapor (10-K)"}


def tg(metin):
    if not TOKEN:
        print("[telegram yok]", metin)
        return
    try:
        st = json.load(open(os.path.join(KOK, "bekci", "state.json")))
        cid = st.get("chat_id")
        if not cid:
            return
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                               json.dumps({"chat_id": cid, "text": metin, "disable_web_page_preview": True}).encode(),
                               {"Content-Type": "application/json"}), timeout=30)
    except Exception as e:
        print("telegram hatası", e)


def main():
    S = json.load(open(edgar.SIRKET_DOSYA, encoding="utf-8"))["sirketler"]
    du = json.load(open(DURUM)) if os.path.exists(DURUM) else {"gorulen": {}, "ilk": True}
    ilk = du.get("ilk", False)
    tam = "--tam" in sys.argv
    yenile = set(s["t"] for s in S) if tam else set()
    mesaj = []
    for s in S:
        cik = int(s["cik"])
        try:
            sub = edgar.al(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
        except Exception as e:
            print("submissions hatası", s["t"], e)
            continue
        rc = sub.get("filings", {}).get("recent", {})
        gor = set(du["gorulen"].get(s["t"], []))
        for i in range(min(len(rc.get("form", [])), 40)):
            f, accn = rc["form"][i], rc["accessionNumber"][i]
            if accn in gor:
                continue
            it = rc.get("items", [""] * 99)[i] or ""
            onemli = [MADDE[m] for m in MADDE if m in it] if f == "8-K" else []
            if f not in FORM and not onemli:
                gor.add(accn)
                continue
            gor.add(accn)
            if ilk:
                continue
            u = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{rc['primaryDocument'][i]}"
            tur = FORM.get(f) or ("8-K · " + ", ".join(onemli))
            mesaj.append(f"🇺🇸 {s['t']} · {tur}\n{s['ad']} · başvuru {rc['filingDate'][i]}" + (f" · dönem {rc['reportDate'][i]}" if rc.get('reportDate', [''])[i] else "") + f"\n{u}")
            if f in FORM or "2.02" in it:
                yenile.add(s["t"])
        du["gorulen"][s["t"]] = sorted(gor)[-200:]
    if yenile:
        sys.argv = [sys.argv[0], ",".join(sorted(yenile))]
        try:
            edgar.main()
        except SystemExit:
            pass
        if not tam and not ilk:
            mesaj.append("Sonar ABD verisi yenilendi: " + ", ".join(sorted(yenile)) + "\nhttps://sonar.smartcuzdan.io/abd/")
    if ilk:
        mesaj = [f"🇺🇸 Sonar ABD bekçisi başladı · {len(S)} şirket (Muhteşem 7): " + ", ".join(s['t'] for s in S) +
                 ".\nSEC EDGAR'da yeni 10-Q, 10-K ve önemli 8-K'ler (kazanç duyurusu, önemli sözleşme, yönetici değişikliği…) buraya gelecek."]
    for m in mesaj:
        tg(m)
        time.sleep(1)
    du["ilk"] = False
    du["son"] = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    json.dump(du, open(DURUM, "w"), ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
