#!/usr/bin/env python3
"""Sonar ABD · SEC EDGAR XBRL'den şirket verisi.

Kaynak: data.sec.gov companyfacts (10-Q, 10-K; US GAAP) ve submissions.
Fiyat: Stooq günlük kapanış (ücretsiz), olmazsa Yahoo grafik verisi.
Çıktı: public/veri/abd/abd.json (liste + özet) ve public/veri/abd/<T>.json (şirket sayfası).

Kullanım: python3 bekci/abd/edgar.py [AAPL,MSFT,...]
SEC kuralı: tanımlayıcı User-Agent, saniyede en çok 10 istek.
"""
import json, os, sys, time, datetime as dt, urllib.request, csv, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CIKTI = os.path.join(KOK, "public", "veri", "abd")
SIRKET_DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sirketler.json")
UA = {"User-Agent": os.environ.get("SEC_UA", "Sonar sonar@smartcuzdan.io"), "Accept-Encoding": "identity", "Host": None}
BASLANGIC = dt.date(2020, 10, 1)


def al(url, tekrar=4, json_mu=True):
    for n in range(tekrar):
        try:
            h = {k: v for k, v in UA.items() if v}
            if "sec.gov" not in url:
                h["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
            b = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60).read()
            time.sleep(0.15)
            return json.loads(b) if json_mu else b.decode("utf-8", "replace")
        except Exception as e:
            if n == tekrar - 1:
                raise
            time.sleep(2 * (n + 1))


def al_bayt(url, tekrar=4):
    for n in range(tekrar):
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers={k: v for k, v in UA.items() if v}), timeout=90).read()
            time.sleep(0.15)
            return b
        except Exception:
            if n == tekrar - 1:
                raise
            time.sleep(2 * (n + 1))


def gun(s):
    return dt.date.fromisoformat(s)


# ---------------------------------------------------------------- kalemler
# (anahtar, tür, etiket listesi) · tür: d = dönemsel (akış), i = anlık (bilanço)
KALEM = [
    ("rev", "d", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]),
    ("cogs", "d", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"]),
    ("gp", "d", ["GrossProfit"]),
    ("rnd", "d", ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost", "TechnologyAndContentExpense"]),
    ("sga", "d", ["SellingGeneralAndAdministrativeExpense"]),
    ("op", "d", ["OperatingIncomeLoss"]),
    ("pbt", "d", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                   "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
                   "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"]),
    ("tax", "d", ["IncomeTaxExpenseBenefit"]),
    ("ni", "d", ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"]),
    ("eps", "d", ["EarningsPerShareDiluted"]),
    ("shd", "d", ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
    ("da", "d", ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization", "Depreciation"]),
    ("sbc", "d", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]),
    ("ocf", "d", ["NetCashProvidedByUsedInOperatingActivities"]),
    ("capex", "d", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]),
    ("buyb", "d", ["PaymentsForRepurchaseOfCommonStock"]),
    ("divp", "d", ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"]),
    ("dps", "d", ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"]),
    ("assets", "i", ["Assets"]),
    ("liab", "i", ["Liabilities"]),
    ("eq", "i", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    ("cash", "i", ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    ("sti", "i", ["MarketableSecuritiesCurrent", "ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "DebtSecuritiesCurrent"]),
    ("ltd", "i", ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt"]),
    ("std", "i", ["LongTermDebtCurrent", "DebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"]),
    ("cp", "i", ["CommercialPaper", "ShortTermBorrowings"]),
    ("inv", "i", ["InventoryNet"]),
    ("ar", "i", ["AccountsReceivableNetCurrent"]),
    ("ca", "i", ["AssetsCurrent"]),
    ("cl", "i", ["LiabilitiesCurrent"]),
    ("ppe", "i", ["PropertyPlantAndEquipmentNet"]),
]
KAYNAK_FORM = ("10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "40-F")


def olgular(cf, etiketler, tur):
    """Etiket listesinden (başlangıç, bitiş) → (değer, dosyalama, accn, form) sözlüğü.
    Önce listedeki ilk etiket; sonraki etiketler yalnız boş kalan dönemleri doldurur."""
    out = {}
    for tag in etiketler:
        for tax in ("us-gaap", "dei"):
            f = cf.get("facts", {}).get(tax, {}).get(tag)
            if not f:
                continue
            for birim, L in f.get("units", {}).items():
                if birim not in ("USD", "USD/shares", "shares"):
                    continue
                for x in L:
                    if x.get("form") not in KAYNAK_FORM:
                        continue
                    son = x["end"]
                    bas = x.get("start") if tur == "d" else None
                    if tur == "d" and not bas:
                        continue
                    if gun(son) < BASLANGIC:
                        continue
                    k = (bas, son)
                    yeni = (x["val"], x.get("filed", ""), x.get("accn", ""), x.get("form", ""), tag)
                    eski = out.get(k)
                    if eski is None or (eski[4] == tag and yeni[1] > eski[1]):
                        out[k] = yeni
    return out


def fy_ceyrek(son, fye_ay):
    d = gun(son) - dt.timedelta(days=10)  # 52/53 haftalık yıl sonları ay başına taşabilir
    fy = d.year + (1 if d.month > fye_ay else 0)
    q = ((d.month - fye_ay - 1) % 12) // 3 + 1
    return fy, q


def ceyrek_seri(O, uclar):
    """Dönemsel olgulardan çeyreklik değer: doğrudan ~3 aylık olgu, yoksa birikimli farkı."""
    res = {}
    for E in uclar:
        dogrudan = [(k, v) for k, v in O.items() if k[1] == E and 80 <= (gun(k[1]) - gun(k[0])).days <= 100]
        if dogrudan:
            k, v = max(dogrudan, key=lambda kv: kv[1][1])
            res[E] = (v[0], "q", v[2])
            continue
        # birikimli: aynı başlangıçlı uzun dönem − bir önceki çeyrek sonuna kadarki birikimli
        uzun = sorted([(k, v) for k, v in O.items() if k[1] == E and (gun(k[1]) - gun(k[0])).days > 100], key=lambda kv: kv[0][0])
        for k, v in uzun:
            S = k[0]
            onceki = [e for e in uclar if gun(S) < gun(e) < gun(E)]
            if not onceki:
                continue
            Ep = max(onceki, key=gun)
            if (S, Ep) in O:
                res[E] = (v[0] - O[(S, Ep)][0], "fark", v[2])
                break
            # önceki birikimli yoksa ve önceki çeyrek Q1 ise doğrudan 3 aylık
            q1 = [(kk, vv) for kk, vv in O.items() if kk[0] == S and kk[1] == Ep and (gun(Ep) - gun(S)).days <= 100]
            if q1:
                res[E] = (v[0] - q1[0][1][0], "fark", v[2])
                break
    return res


FIYAT_TANI = {}


def fiyatlar(t):
    """Günlük kapanış: [(tarih, kapanış)], kaynak. Sıra: Nasdaq, Stooq, Yahoo (hepsi ücretsiz, gecikmeli)."""
    tani = []
    try:
        bas = (dt.date.today() - dt.timedelta(days=6 * 366)).isoformat()
        req = urllib.request.Request(f"https://api.nasdaq.com/api/quote/{t}/historical?assetclass=stocks&fromdate={bas}&todate={dt.date.today().isoformat()}&limit=9999",
                                     headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                                              "Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
        j = json.loads(urllib.request.urlopen(req, timeout=40).read())
        rows = ((j.get("data") or {}).get("tradesTable") or {}).get("rows") or []
        R = []
        for r in rows:
            m, d, y = r["date"].split("/")
            R.append((f"{y}-{m}-{d}", float(r["close"].replace("$", "").replace(",", ""))))
        R.sort()
        if len(R) > 200:
            FIYAT_TANI[t] = "Nasdaq"
            return R, "Nasdaq"
        tani.append(f"nasdaq {len(R)} satır")
    except Exception as e:
        tani.append("nasdaq " + repr(e)[:120])
    try:
        s = al(f"https://stooq.com/q/d/l/?s={t.lower()}.us&i=d", json_mu=False)
        R = [(r["Date"], float(r["Close"])) for r in csv.DictReader(io.StringIO(s)) if r.get("Close") not in (None, "", "N/D")]
        if len(R) > 200:
            FIYAT_TANI[t] = "Stooq"
            return R, "Stooq"
        tani.append("stooq " + s[:80].replace("\n", " "))
    except Exception as e:
        tani.append("stooq " + repr(e)[:120])
    try:
        j = al(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=10y&interval=1d")
        r = j["chart"]["result"][0]
        ts, cl = r["timestamp"], r["indicators"]["quote"][0]["close"]
        R = [(dt.datetime.utcfromtimestamp(a).date().isoformat(), c) for a, c in zip(ts, cl) if c]
        FIYAT_TANI[t] = "Yahoo"
        return R, "Yahoo Finance"
    except Exception as e:
        tani.append("yahoo " + repr(e)[:120])
    FIYAT_TANI[t] = tani
    print("fiyat yok", t, tani)
    return [], None


def kapanis(F, tarih):
    tt = None
    for d, c in F:
        if d <= tarih:
            tt = (d, c)
        else:
            break
    return tt


def isle(S):
    t, cik = S["t"], int(S["cik"])
    cf = al(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
    sub = al(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    fye = sub.get("fiscalYearEnd") or "1231"
    fye_ay = int(fye[:2])

    O = {k: olgular(cf, tags, tur) for k, tur, tags in KALEM}
    # çeyrek sonları: 10-Q/10-K'de 3 aylık hasılat ya da net kâr olan bitişler + yıllık bitişler
    uclar = set()
    for key in ("rev", "ni", "op"):
        for (b, e) in O[key]:
            gl = (gun(e) - gun(b)).days
            if 80 <= gl <= 100 or 350 <= gl <= 380:
                uclar.add(e)
    # aynı çeyreğe düşen yakın bitişleri (aynı dönem, farklı gün yazımı) birleştir
    uclar = sorted(uclar, key=gun)
    tekil = []
    for e in uclar:
        if tekil and (gun(e) - gun(tekil[-1])).days < 20:
            tekil[-1] = e
        else:
            tekil.append(e)
    uclar = tekil

    Q = {k: ceyrek_seri(O[k], uclar) for k, tur, _ in KALEM if tur == "d"}
    I = {}
    for k, tur, _ in KALEM:
        if tur != "i":
            continue
        d = {}
        for (b, e), v in O[k].items():
            for u in uclar:
                if abs((gun(u) - gun(e)).days) < 20:
                    if u not in d or v[1] > d[u][1]:
                        d[u] = (v[0], v[1], v[2])
        I[k] = d
    # ödenmemiş pay sayısı (dei, kapak sayfası; sınıfların toplamı) — dönem sonuna en yakın kapak tarihi
    pay = {}
    dei = cf.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    kapak = {}
    for x in dei:
        kapak.setdefault((x["accn"], x["end"]), 0)
        kapak[(x["accn"], x["end"])] += x["val"]
    kapak_l = sorted(((e, v) for (a, e), v in kapak.items()), key=lambda z: z[0])

    F, fkaynak = fiyatlar(t)
    periods = []
    for e in uclar:
        if gun(e) < dt.date(2021, 1, 1):
            continue
        fy, q = fy_ceyrek(e, fye_ay)
        p = {"p": f"{fy}Q{q}", "fy": fy, "q": q, "son": e}
        for k, tur, _ in KALEM:
            if tur == "d":
                v = Q[k].get(e)
                if v is not None:
                    p[k] = round(v[0] / 1e6, 2) if k not in ("eps", "dps") and k != "shd" else (round(v[0] / 1e6, 2) if k == "shd" else round(v[0], 2))
                    if v[1] == "fark":
                        p.setdefault("fark", []).append(k)
            else:
                v = I[k].get(e)
                if v is not None:
                    p[k] = round(v[0] / 1e6, 2)
        fy_shd = [v for (b_, e_), v in O["shd"].items() if e_ == e and (gun(e_) - gun(b_)).days > 300]
        if "shd" in (p.get("fark") or []):
            # ağırlıklı ortalama pay farkla türetilmez: 4. çeyrekte yıllık ağırlıklı ortalama kullanılır
            if fy_shd:
                p["shd"] = round(fy_shd[0][0] / 1e6, 2)
            else:
                p.pop("shd", None)
            p["fark"] = [k for k in p["fark"] if k != "shd"]
        if "eps" in (p.get("fark") or []) and p.get("ni") is not None and fy_shd:
            p["eps"] = round(p["ni"] / (fy_shd[0][0] / 1e6), 2)
        if "gp" not in p and "rev" in p and "cogs" in p:
            p["gp"] = round(p["rev"] - p["cogs"], 2)
        # kaynak dosyalama (10-Q/10-K) — hasılatın geldiği başvuru
        r = Q["rev"].get(e) or Q["ni"].get(e)
        if r:
            p["accn"] = r[2]
        # dönem sonuna en yakın sonraki kapak sayfasındaki pay sayısı (milyon)
        sonra = [v for d_, v in kapak_l if gun(d_) >= gun(e) and (gun(d_) - gun(e)).days < 120]
        yakin = sorted(kapak_l, key=lambda z: abs((gun(z[0]) - gun(e)).days))
        if sonra:
            p["pay"] = round(sonra[0] / 1e6, 2)
        elif yakin and abs((gun(yakin[0][0]) - gun(e)).days) < 200:
            p["pay"] = round(yakin[0][1] / 1e6, 2)
        elif p.get("shd"):
            p["pay"] = p["shd"]
        kp = kapanis(F, e) if F else None
        if kp:
            p["fiyat"] = round(kp[1], 2)
            p["fiyat_t"] = kp[0]
        periods.append(p)

    # son 4 çeyrek (TTM) oranları
    def ttm(i, k):
        L = periods[max(0, i - 3): i + 1]
        if len(L) < 4 or any(x.get(k) is None for x in L):
            return None
        return sum(x[k] for x in L)

    for i, p in enumerate(periods):
        r = {}
        for k in ("rev", "gp", "op", "ni", "ocf", "capex", "buyb", "divp", "da", "sbc", "rnd"):
            v = ttm(i, k)
            if v is not None:
                r[k + "4"] = round(v, 2)
        if r.get("rev4"):
            for k in ("gp", "op", "ni"):
                if r.get(k + "4") is not None:
                    r[k + "m"] = round(100 * r[k + "4"] / r["rev4"], 2)
            if r.get("rnd4") is not None:
                r["rndm"] = round(100 * r["rnd4"] / r["rev4"], 2)
        if r.get("rev4"):
            if r.get("capex4") is not None:
                r["capex_s"] = round(100 * r["capex4"] / r["rev4"], 2)
            if r.get("sbc4") is not None:
                r["sbc_s"] = round(100 * r["sbc4"] / r["rev4"], 2)
        c4 = ttm(i, "cogs")
        if c4 and p.get("inv") is not None:
            r["inv_gun"] = round(p["inv"] / (c4 / 365), 1)
        if r.get("ocf4") is not None and r.get("capex4") is not None:
            r["fcf4"] = round(r["ocf4"] - r["capex4"], 2)
        if r.get("op4") is not None and r.get("da4") is not None:
            r["ebitda4"] = round(r["op4"] + r["da4"], 2)
        borc = sum(p.get(k) or 0 for k in ("ltd", "std", "cp"))
        nakit = (p.get("cash") or 0) + (p.get("sti") or 0)
        if p.get("cash") is not None:
            r["netborc"] = round(borc - nakit, 2)
        if p.get("fiyat") and p.get("pay"):
            pd_ = p["fiyat"] * p["pay"]
            r["pd"] = round(pd_, 1)
            if r.get("ni4") and r["ni4"] > 0:
                r["fk"] = round(pd_ / r["ni4"], 2)
            if p.get("eq") and p["eq"] > 0:
                r["pddd"] = round(pd_ / p["eq"], 2)
            if r.get("rev4"):
                r["pdsat"] = round(pd_ / r["rev4"], 2)
            if r.get("fcf4") is not None:
                r["fcfv"] = round(100 * r["fcf4"] / pd_, 2)
            if r.get("buyb4") is not None:
                r["gav"] = round(100 * r["buyb4"] / pd_, 2)
            if r.get("divp4") is not None:
                r["tv"] = round(100 * r["divp4"] / pd_, 2)
            if r.get("ebitda4") and "netborc" in r:
                r["fd_favok"] = round((pd_ + r["netborc"]) / r["ebitda4"], 2)
        if i >= 4 and r.get("ni4") is not None:
            e0 = sum(periods[j].get("eq") or 0 for j in (i, i - 4)) / 2
            if e0 > 0:
                r["roe"] = round(100 * r["ni4"] / e0, 2)
        if r.get("ebitda4") and "netborc" in r and r["ebitda4"] > 0:
            r["nb_favok"] = round(r["netborc"] / r["ebitda4"], 2)
        # yıllık büyüme (aynı mali çeyrek)
        if i >= 4:
            for k in ("rev", "op", "ni", "eps"):
                a, b = p.get(k), periods[i - 4].get(k)
                if a is not None and b not in (None, 0) and periods[i - 4]["q"] == p["q"]:
                    r["g_" + k] = round(100 * (a - b) / abs(b), 2)
        p["r"] = r

    # kırılımlar ve sektöre özgü göstergeler (XBRL boyutlu veri + 10-Q/10-K metni)
    mix, kpi = {}, {}
    try:
        import segment
        olgu, metin = segment.topla(al, al_bayt, t, cik, sub)
        mix, kpi = segment.kur(t, olgu, metin, periods, ceyrek_seri)
        kpi = segment.tureve(t, mix, kpi, periods)
    except Exception as e:
        import traceback; traceback.print_exc()
        print("kırılım hatası", t, repr(e))
    son_f = F[-1] if F else None
    out = {
        "t": t, "ad": S["ad"], "ad_tr": S.get("ad_tr", S["ad"]), "cik": cik, "borsa": S.get("borsa", ""),
        "sektor": S.get("sektor", ""), "intro": S.get("intro", ""), "izle": S.get("izle", []), "renk": S.get("renk", ""),
        "fye": fye, "mali_yil": S.get("mali_yil", ""), "periods": periods,
        "fiyat": {"son": son_f[1] if son_f else None, "t": son_f[0] if son_f else None, "kaynak": fkaynak,
                  "gunluk": [[d, round(c, 2)] for d, c in F if d >= (dt.date.today() - dt.timedelta(days=5 * 366)).isoformat()][::1]},
        "sec": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-&dateb=&owner=include&count=40",
        "guncel": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "mix": mix, "kpi": kpi,
    }
    # son başvurular (8-K kazanç duyurusu, 10-Q, 10-K)
    rc = sub.get("filings", {}).get("recent", {})
    basv = []
    for i in range(min(len(rc.get("form", [])), 300)):
        f = rc["form"][i]
        if f not in ("10-Q", "10-K", "8-K"):
            continue
        it = rc.get("items", [""] * 999)[i] or ""
        if f == "8-K" and not any(x in it for x in ("2.02", "1.01", "2.01", "5.02", "8.01", "7.01")):
            continue
        accn = rc["accessionNumber"][i]
        doc = rc["primaryDocument"][i]
        basv.append({"f": f, "t": rc["filingDate"][i], "d": rc.get("reportDate", [""] * 999)[i], "items": it,
                     "u": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{doc}"})
        if len(basv) >= 25:
            break
    out["basvuru"] = basv
    # anlık değerleme: son kapanış × son pay sayısı
    L = periods[-1] if periods else None
    if L and son_f and L.get("pay"):
        pdn = son_f[1] * L["pay"]
        out["anlik"] = {"pd": round(pdn, 1), "fk": round(pdn / L["r"]["ni4"], 2) if L["r"].get("ni4") and L["r"]["ni4"] > 0 else None,
                        "pddd": round(pdn / L["eq"], 2) if L.get("eq") and L["eq"] > 0 else None,
                        "pdsat": round(pdn / L["r"]["rev4"], 2) if L["r"].get("rev4") else None}
    return out


def main():
    S = json.load(open(SIRKET_DOSYA, encoding="utf-8"))
    sec = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] else None
    os.makedirs(CIKTI, exist_ok=True)
    liste_yol = os.path.join(CIKTI, "abd.json")
    liste = json.load(open(liste_yol, encoding="utf-8")) if os.path.exists(liste_yol) else {"sirketler": []}
    by = {x["t"]: x for x in liste.get("sirketler", [])}
    hata = []
    for s in S["sirketler"]:
        if sec and s["t"] not in sec:
            continue
        try:
            d = isle(s)
        except Exception as e:
            print("HATA", s["t"], repr(e))
            hata.append([s["t"], repr(e)[:200]])
            continue
        json.dump(d, open(os.path.join(CIKTI, s["t"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        L = d["periods"][-1] if d["periods"] else {}
        by[s["t"]] = {"t": s["t"], "ad": d["ad"], "grup": s.get("grup", ""), "sektor": d["sektor"], "renk": d["renk"],
                      "p": L.get("p"), "son": L.get("son"), "rev4": L.get("r", {}).get("rev4"), "ni4": L.get("r", {}).get("ni4"),
                      "g_rev": L.get("r", {}).get("g_rev"), "g_ni": L.get("r", {}).get("g_ni"), "opm": L.get("r", {}).get("opm"),
                      "fiyat": d["fiyat"]["son"], "fiyat_t": d["fiyat"]["t"], **(d.get("anlik") or {})}
        print("tamam", s["t"], len(d["periods"]), "dönem; son", L.get("p"), L.get("son"))
    sira = [s["t"] for s in S["sirketler"]]
    liste = {"guncel": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "gruplar": S.get("gruplar", []),
             "sirketler": [by[t] for t in sira if t in by], "hata": hata, "fiyat_kaynak": FIYAT_TANI}
    json.dump(liste, open(liste_yol, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    if hata and len(hata) == len([s for s in S["sirketler"] if not sec or s["t"] in sec]):
        sys.exit(1)


if __name__ == "__main__":
    main()
