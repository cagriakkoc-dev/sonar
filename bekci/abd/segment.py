#!/usr/bin/env python3
"""Sonar ABD · kırılımlar ve sektöre özgü göstergeler.

1) XBRL boyutlu veri: her 10-Q/10-K'nin XBRL örneğinden (…_htm.xml) hasılat, faaliyet kârı, satış maliyeti ve
   kalan edim yükümlülüğü (RPO) için tek boyutlu olgular (ürün/hizmet, faaliyet bölümü, coğrafya; bölüm × ürün
   ikilisinde ürün). Başvuru başına ayrıştırılmış sonuç önbellekte: bekci/abd/xbrl/<T>/<accn>.json.
2) Metin göstergeleri: 10-Q/10-K metninden şirkete özgü düzenli ifadelerle (META DAP/ARPP/reklam, TSLA üretim/
   teslimat/depolama, MSFT Azure büyümesi, GOOGL tıklama ve TAC…). Önbellek: bekci/abd/metin/<T>/<accn>.json.
edgar.isle() bu modülü çağırır ve şirket JSON'una "mix" ve "kpi" alanlarını ekler.
"""
import json, os, re, html, datetime as dt, xml.etree.ElementTree as ET

BURA = os.path.dirname(os.path.abspath(__file__))
SURUM_X, SURUM_M = 3, 5   # ayrıştırma kuralı değişince artır → önbellek yenilenir

KAVRAM = {  # XBRL kavramı → ölçü
    "RevenueFromContractWithCustomerExcludingAssessedTax": "rev", "Revenues": "rev", "SalesRevenueNet": "rev",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "rev",
    "OperatingIncomeLoss": "op", "CostOfRevenue": "cogs", "CostOfGoodsAndServicesSold": "cogs",
    "RevenueRemainingPerformanceObligation": "rpo", "CostsAndExpenses": "gider",
}
EKSEN = {"ProductOrServiceAxis": "urun", "StatementBusinessSegmentsAxis": "segment", "StatementGeographicalAxis": "bolge",
         "ProductsOrServicesSecondaryCategorizationAxis": "urun2", "MajorCustomersAxis": "musteri"}
ATLA_UYE = {"OperatingSegmentsMember"}

AD = {  # üye → Türkçe ad
    "IPhoneMember": "iPhone", "MacMember": "Mac", "IPadMember": "iPad", "WearablesHomeandAccessoriesMember": "Giyilebilir, ev ve aksesuar",
    "ServiceMember": "Hizmetler", "ProductMember": "Ürünler", "ServicesMember": "Hizmetler",
    "AmericasSegmentMember": "Amerika", "EuropeSegmentMember": "Avrupa", "GreaterChinaSegmentMember": "Büyük Çin", "JapanSegmentMember": "Japonya",
    "RestOfAsiaPacificSegmentMember": "Diğer Asya-Pasifik", "US": "ABD", "CN": "Çin", "TW": "Tayvan", "OtherCountriesMember": "Diğer ülkeler",
    "NonUsMember": "ABD dışı", "AzureMember": "Azure", "MicrosoftThreeSixFiveCloudMember": "Microsoft 365 bulut",
    "ProductivityAndServerLicensingMember": "Verimlilik ve sunucu lisansları", "SearchAndAdvertisingMember": "Arama ve reklam",
    "XBOXMember": "Xbox", "IndustrySolutionsMember": "Sektör çözümleri", "WindowsOEMAndDevicesMember": "Windows OEM ve cihazlar",
    "FrontierAndSupportServicesMember": "Frontier ve destek hizmetleri", "ServiceOtherMember": "Hizmet ve diğer", "MicrosoftCloudMember": "Microsoft Cloud",
    "AgentsAndInfraMember": "Ajanlar ve altyapı", "DevicesAndConsumerMember": "Cihazlar ve tüketici",
    "ProductivityAndBusinessProcessesMember": "Verimlilik ve iş süreçleri", "IntelligentCloudMember": "Akıllı bulut", "MorePersonalComputingMember": "Kişisel bilişim",
    "ServerProductsAndCloudServicesMember": "Sunucu ürünleri ve bulut hizmetleri", "MicrosoftOfficeMember": "Office ürünleri ve bulut",
    "OfficeProductsAndCloudServicesMember": "Office ürünleri ve bulut", "LinkedInCorporationMember": "LinkedIn", "LinkedInMember": "LinkedIn",
    "WindowsAndDevicesMember": "Windows ve cihazlar", "GamingMember": "Oyun", "DynamicsProductsAndCloudServicesMember": "Dynamics",
    "EnterpriseServicesMember": "Kurumsal hizmetler", "EnterpriseAndPartnerServicesMember": "Kurumsal ve iş ortağı hizmetleri",
    "SearchAndNewsAdvertisingMember": "Arama ve haber reklamları", "OtherProductsAndServicesMember": "Diğer",
    "GoogleServicesMember": "Google Services", "GoogleCloudMember": "Google Cloud", "AllOtherSegmentsMember": "Diğer girişimler (Other Bets)",
    "OtherBetsMember": "Diğer girişimler (Other Bets)", "GoogleSearchOtherMember": "Google arama ve diğer", "YouTubeAdvertisingRevenueMember": "YouTube reklamları",
    "GoogleNetworkMember": "Google Network", "SubscriptionsPlatformsAndDevicesRevenueMember": "Abonelik, platform ve cihazlar",
    "GoogleOtherMember": "Google diğer", "GoogleAdvertisingRevenueMember": "Google reklam (toplam)", "EMEAMember": "EMEA",
    "AsiaPacificMember": "Asya-Pasifik", "AmericasExcludingUnitedStatesMember": "Amerika (ABD hariç)", "HedgingGainsLossesMember": "Riskten korunma",
    "NorthAmericaSegmentMember": "Kuzey Amerika", "InternationalSegmentMember": "Uluslararası", "AmazonWebServicesSegmentMember": "AWS",
    "OnlineStoresMember": "Çevrimiçi mağazalar", "PhysicalStoresMember": "Fiziksel mağazalar", "ThirdPartySellerServicesMember": "Üçüncü taraf satıcı hizmetleri",
    "AdvertisingServicesMember": "Reklam hizmetleri", "SubscriptionServicesMember": "Abonelik hizmetleri", "AmazonWebServicesMember": "AWS",
    "OtherServicesMember": "Diğer", "DataCenterMember": "Veri merkezi", "GamingMember_": "Oyun", "ProfessionalVisualizationMember": "Profesyonel görselleştirme",
    "AutomotiveMember": "Otomotiv", "OEMAndOtherMember": "OEM ve diğer", "ComputeAndNetworkingSegmentMember": "Hesaplama ve ağ",
    "GraphicsSegmentMember": "Grafik", "HyperscaleMember": "Hiper ölçekli bulut", "AICloudsIndustrialEnterpriseMember": "Yapay zekâ bulutları, sanayi ve kurumsal",
    "EdgeComputingMember": "Uç bilişim", "ComputeMember": "Hesaplama", "NetworkingMember": "Ağ",
    "FamilyOfAppsMember": "Uygulama ailesi (FoA)", "RealityLabsMember": "Reality Labs", "USCanadaMember": "ABD ve Kanada", "EuropeMember": "Avrupa",
    "RestOfWorldMember": "Dünyanın geri kalanı", "AdvertisingMember": "Reklam", "OtherRevenueMember": "Diğer gelir",
    "AutomotiveSalesMember": "Otomotiv satışları", "AutomotiveRegulatoryCreditsMember": "Karbon kredileri", "AutomotiveLeasingMember": "Otomotiv kiralama",
    "AutomotiveRevenuesMember": "Otomotiv (toplam)", "EnergyGenerationAndStorageMember": "Enerji üretimi ve depolama",
    "ServicesAndOtherMember": "Hizmet ve diğer", "AutomotiveSegmentMember": "Otomotiv", "EnergyGenerationAndStorageSegmentMember": "Enerji üretimi ve depolama",
    "EnergyGenerationAndStorageSalesMember": "Enerji satışları", "EnergyGenerationAndStorageLeasingMember": "Enerji kiralama",
    "SalesAndServicesMember": "Satış ve hizmet",
    "ChinaIncludingHongKongMember": "Çin (Hong Kong dahil)", "SG": "Singapur", "OtherAsiaPacificMember": "Diğer Asya-Pasifik",
    "AllOtherCountriesNotSeparatelyDisclosedMember": "Diğer ülkeler", "OtherRevenuesMember": "Diğer gelirler",
    "MicrosoftThreeSixFiveCommercialProductsAndCloudServicesMember": "Microsoft 365 ticari", "MicrosoftThreeSixFiveConsumerProductsAndCloudServicesMember": "Microsoft 365 bireysel",
    "SearchAdvertisingMember": "Arama reklamları", "WindowsMember": "Windows", "DevicesMember": "Cihazlar",
    "AutomotiveSalesWithoutResaleValueGuaranteeMember": "Otomotiv satışları (geri alım garantisiz)", "AutomotiveSalesWithResaleValueGuaranteeMember": "Otomotiv satışları (geri alım garantili)", "AutomobilesMember": "Otomobil", "HedgingGainsLossesMember": "Riskten korunma kazanç/kaybı",
 "CommercialCustomersMember": "Ticari müşteriler",
}
ES = {"GoogleServicesSegmentMember": "GoogleServicesMember", "GoogleCloudSegmentMember": "GoogleCloudMember",
      "GraphicsMember": "GraphicsSegmentMember", "ComputeAndNetworkingMember": "ComputeAndNetworkingSegmentMember",
      "AmericasMember": "AmericasSegmentMember", "EuropeMember_": "EuropeSegmentMember"}
GRUP_AD = {"urun": "Ürün / hizmet", "segment": "Faaliyet bölümü", "bolge": "Coğrafya", "urun2": "İkincil kategori"}
OLCU_AD = {"rev": "Hasılat", "op": "Faaliyet kârı", "cogs": "Satışların maliyeti", "gider": "Toplam gider", "rpo": "Kalan edim yükümlülüğü (sipariş birikimi)"}


def ad(m):
    if m in AD:
        return AD[m]
    s = re.sub(r"Member$", "", m.split(":")[-1])
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)


def _yerel(tag):
    return tag.split("}")[-1]


def xbrl_ayristir(xml_bayt):
    """→ [(ölçü, grup, üye, başlangıç|None, bitiş, değer)]"""
    kok = ET.fromstring(xml_bayt)
    ctx = {}
    for c in kok.iter():
        if _yerel(c.tag) != "context":
            continue
        dims, typed = [], False
        bas = son = None
        for e in c.iter():
            t = _yerel(e.tag)
            if t == "explicitMember":
                dims.append((e.get("dimension").split(":")[-1], (e.text or "").strip().split(":")[-1]))
            elif t == "typedMember":
                typed = True
            elif t == "startDate":
                bas = e.text.strip()
            elif t in ("endDate", "instant"):
                son = e.text.strip()
        if typed:
            continue
        dims = [d for d in dims if not (d[0] == "ConsolidationItemsAxis" and d[1] in ATLA_UYE)]
        ctx[c.get("id")] = (dims, bas, son)
    out = []
    for e in kok:
        cr = e.get("contextRef")
        if not cr or cr not in ctx:
            continue
        k = _yerel(e.tag)
        ns = e.tag.split("}")[0]
        if k not in KAVRAM or "us-gaap" not in ns:
            continue
        dims, bas, son = ctx[cr]
        if not dims:
            grup, uye = "_", "_"
        elif len(dims) == 1 and dims[0][0] in EKSEN:
            grup, uye = EKSEN[dims[0][0]], dims[0][1]
        elif len(dims) == 2 and {d[0] for d in dims} == {"ProductOrServiceAxis", "StatementBusinessSegmentsAxis"}:
            grup, uye = "urun", [d for d in dims if d[0] == "ProductOrServiceAxis"][0][1]
        else:
            continue
        try:
            v = float(e.text)
        except (TypeError, ValueError):
            continue
        out.append((KAVRAM[k], grup, uye, bas, son, v))
    return out


# ---------------------------------------------------------------- metin göstergeleri
def _sayi(s):
    return float(s.replace(",", ""))


def _ps(s):
    return -_sayi(s.strip("()")) if s.startswith("(") else _sayi(s)


def _adet(m):
    v, b = _sayi(m.group(1)), (m.group(2) or "").strip()
    return round(v * 1000 if b == "million" else v if b == "thousand" else v / 1000, 1)


def _yon(s):
    return -1 if re.search(r"decreas|declin", s, re.I) else 1


KURAL = {
    "META": [
        ("dap", r"(?:Family )?daily active people \(DAP\) (?:was|were) ([\d.]+) billion on average", lambda m: _sayi(m.group(1)), "d"),
        ("arpp", r"worldwide ARPP was \$([\d.]+)", lambda m: _sayi(m.group(1)), "q"),
        ("imp_g", r"Ad impressions delivered across our Family of Apps in the \w+ quarter of \d{4} (increased|decreased) (?:by )?(\d+)%", lambda m: _yon(m.group(1)) * _sayi(m.group(2)), "q"),
        ("ppa_g", r"(?:average price per ad|Average price per ad) in the \w+ quarter of \d{4} (increased|decreased) (?:by )?(\d+)%", lambda m: _yon(m.group(1)) * _sayi(m.group(2)), "q"),
        ("calisan", r"Headcount was ([\d,]+) as of", lambda m: _sayi(m.group(1)), "d"),
    ],
    "TSLA": [
        ("uretim_ytd", r"we produced (?:approximately )?([\d.,]+) (million |thousand )?(?:consumer )?vehicles", _adet, "ytd"),
        ("teslimat_ytd", r"(?:and )?delivered (?:approximately )?([\d.,]+) (million |thousand )?(?:consumer )?vehicles", _adet, "ytd"),
        ("depolama_ytd", r"we deployed ([\d.]+) GWh of energy storage products", lambda m: _sayi(m.group(1)), "ytd"),
    ],
    "MSFT": [
        ("azure_g", r"Azure and other cloud services revenue (grew|increased|decreased) (\d+)%", lambda m: _yon(m.group(1)) * _sayi(m.group(2)), "q"),
        ("mcloud_g", r"Microsoft Cloud revenue (?:increased|grew) (\d+)% to \$([\d.]+) billion", lambda m: _sayi(m.group(1)), "q"),
        ("m365c_g", r"Microsoft 365 Commercial cloud revenue (?:increased|grew) (\d+)%", lambda m: _sayi(m.group(1)), "q"),
    ],
    "GOOGL": [
        ("tiklama_g", r"Paid clicks change\s*(\(?\d+\)?)\s*%", lambda m: _ps(m.group(1)), "q"),
        ("tbm_g", r"Cost-per-click change\s*(\(?\d+\)?)\s*%", lambda m: _ps(m.group(1)), "q"),
        ("gosterim_g", r"Impressions change\s*(\(?\d+\)?)\s*%", lambda m: _ps(m.group(1)), "q"),
        ("tbg_g", r"Cost-per-impression change\s*(\(?\d+\)?)\s*%", lambda m: _ps(m.group(1)), "q"),
        ("tac_oran", r"TAC rate (?:increased|decreased|remained).{0,40}?to ([\d.]+)% from the three months", lambda m: _sayi(m.group(1)), "q"),
        ("calisan", r"[Ww]e had ([\d,]+) employees", lambda m: _sayi(m.group(1)), "d"),
    ],
    "AMZN": [
        ("calisan", r"employed approximately ([\d,]+) full-time and part-time employees", lambda m: _sayi(m.group(1)), "d"),
    ],
    "NVDA": [],
    "AAPL": [],
}


def metin_coz(t, metin):
    res = {}
    for k, rx, f, tur in KURAL.get(t, []):
        m = re.search(rx, metin)
        if m:
            try:
                res[k] = [f(m), tur]
            except Exception:
                pass
    return res


def html_metin(b):
    s = b.decode("utf-8", "replace")
    s = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", s)
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s))


# ---------------------------------------------------------------- başvuru listesi
def basvurular(al, sub, cik):
    """2021'den bu yana 10-Q/10-K: [(accn, form, reportDate, primaryDocument)]"""
    L = []

    def ekle(rc):
        for i in range(len(rc.get("form", []))):
            if rc["form"][i] in ("10-Q", "10-K") and (rc.get("reportDate", [""])[i] or "") >= "2020-09-01":
                L.append((rc["accessionNumber"][i], rc["form"][i], rc["reportDate"][i], rc["primaryDocument"][i]))
    ekle(sub.get("filings", {}).get("recent", {}))
    for f in sub.get("filings", {}).get("files", []):
        if (f.get("filingTo") or "") >= "2020-10-01":
            try:
                ekle(al("https://data.sec.gov/submissions/" + f["name"]))
            except Exception as e:
                print("eski liste alınamadı", f["name"], e)
    return sorted(set(L), key=lambda x: x[2])


def onbellek(t, tur, accn):
    return os.path.join(BURA, tur, t, accn + ".json")


def topla(al, al_bayt, t, cik, sub):
    """Her başvuru için XBRL olguları ve metin göstergeleri (önbellekli)."""
    olgu, metin = [], []
    for accn, form, rd, doc in basvurular(al, sub, cik):
        klasor = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/"
        yx = onbellek(t, "xbrl", accn)
        d = json.load(open(yx)) if os.path.exists(yx) else None
        if not d or d.get("v") != SURUM_X:
            try:
                ad_ = doc.rsplit(".", 1)[0] + "_htm.xml"
                try:
                    b = al_bayt(klasor + ad_)
                except Exception:
                    idx = al(klasor + "index.json")
                    ad_ = [x["name"] for x in idx["directory"]["item"] if x["name"].endswith(".xml") and not re.match(r"(FilingSummary|R\d+|MetaLinks|.*_(cal|def|lab|pre))", x["name"])][0]
                    b = al_bayt(klasor + ad_)
                d = {"v": SURUM_X, "accn": accn, "form": form, "rd": rd, "u": klasor + doc, "o": xbrl_ayristir(b)}
                os.makedirs(os.path.dirname(yx), exist_ok=True)
                json.dump(d, open(yx, "w"), separators=(",", ":"))
            except Exception as e:
                print("xbrl hatası", t, accn, repr(e)[:150])
                d = None
        if d:
            olgu.append(d)
        ym = onbellek(t, "metin", accn)
        m = json.load(open(ym)) if os.path.exists(ym) else None
        if (not m or m.get("v") != SURUM_M) and KURAL.get(t):
            try:
                m = {"v": SURUM_M, "accn": accn, "form": form, "rd": rd, "u": klasor + doc, "g": metin_coz(t, html_metin(al_bayt(klasor + doc)))}
                os.makedirs(os.path.dirname(ym), exist_ok=True)
                json.dump(m, open(ym, "w"), ensure_ascii=False, separators=(",", ":"))
            except Exception as e:
                print("metin hatası", t, accn, repr(e)[:150])
                m = None
        if m:
            metin.append(m)
    return olgu, metin


def _gun(s):
    return dt.date.fromisoformat(s)


def kur(t, olgu, metin, periods, ceyrek_seri):
    """periods: edgar dönemleri (son, p). → mix, kpi"""
    uclar = [p["son"] for p in periods]
    pkey = {p["son"]: p["p"] for p in periods}

    def eslestir(e):
        for u in uclar:
            if abs((_gun(u) - _gun(e)).days) < 20:
                return u
        return None
    # (ölçü, grup, üye) → {(bas, son): (değer, dosyalama sırası, accn, form, '')}
    S = {}
    kaynak = {}
    for d in olgu:
        for olc, grup, uye, bas, son, v in d["o"]:
            if olc == "rpo":
                bas = None
            u = eslestir(son)
            if not u:
                continue
            if olc != "rpo" and bas is None:
                continue
            uye = ES.get(uye, uye)
            k = (olc, grup, uye)
            anahtar = (bas, u) if olc != "rpo" else (None, u)
            eski = S.setdefault(k, {}).get(anahtar)
            if eski is None or d["rd"] >= eski[1]:
                S[k][anahtar] = (v, d["rd"], d["accn"], d["form"], "")
        kaynak[d["rd"]] = d["u"]
    mix = {}
    for (olc, grup, uye), O in S.items():
        if grup == "_" and olc != "rpo":
            continue
        if olc == "rpo":
            seri = {pkey[e]: round(v[0] / 1e6, 1) for (b, e), v in O.items() if e in pkey}
        else:
            Q = ceyrek_seri(O, uclar)
            seri = {pkey[e]: round(v[0] / 1e6, 1) for e, v in Q.items() if e in pkey}
        if not seri:
            continue
        g = mix.setdefault(f"{olc}:{grup}", {"olcu": olc, "grup": grup, "ad": OLCU_AD.get(olc, olc) + (" · " + GRUP_AD[grup] if grup in GRUP_AD else ""), "kalem": {}})
        g["kalem"][uye] = {"ad": ad(uye), "seri": seri}
    # yalnız anlamlı kırılımlar: en az 2 kalem ve son 4 dönemde veri
    son4 = [p["p"] for p in periods[-4:]]
    for key in list(mix):
        K = mix[key]["kalem"]
        if mix[key]["olcu"] == "rpo":
            continue
        canli = {u: k for u, k in K.items() if any(p in k["seri"] for p in son4)}
        if len(canli) < 2:
            mix.pop(key)
            continue
    # parçalar: her dönem için toplamı şirket hasılatına eşit olan en ince kalem kümesi (toplam/alt kalem çift sayımını önler).
    # Ürün kırılımı tek başına toplamı vermiyorsa (ör. GOOGL, META) bölüm kalemleri tamamlayıcı aday olur (Cloud, Reality Labs).
    import itertools
    totp = {p["p"]: p.get("rev") for p in periods}
    seg = mix.get("rev:segment", {}).get("kalem", {})
    for key, g in mix.items():
        K = g["kalem"]
        if g["olcu"] != "rev":
            g["parca"] = list(K)
            continue
        aday = dict(K)
        if g["grup"] == "urun":
            for u, k in seg.items():
                if u not in aday:
                    aday[u] = k
        pp = {}
        onceki = None
        for p in reversed([p["p"] for p in periods]):
            T = totp.get(p)
            if not T:
                continue
            bul = None
            for havuz, tolo in ([(K, 0.0005), (aday, 0.0005), (K, 0.004), (aday, 0.004)] if g["grup"] == "urun" else [(K, 0.0005), (K, 0.004)]):
                uy = [u for u in havuz if p in havuz[u]["seri"]]
                if len(uy) > 18:
                    uy = sorted(uy, key=lambda u: -len(havuz[u]["seri"]))[:18]
                if len(uy) < 2:
                    continue
                tol = max(2.0, tolo * abs(T))
                en = None
                for n in range(len(uy), 1, -1):
                    for c in itertools.combinations(uy, n):
                        if abs(sum(havuz[u]["seri"][p] for u in c) - T) <= tol:
                            skor = (len(set(c) & set(onceki or [])), n)
                            if en is None or skor > en[0]:
                                en = (skor, list(c))
                    if en and onceki is None:
                        break
                if en:
                    bul = en[1]
                    break
            if bul:
                pp[p] = bul
                onceki = bul
        sira = []
        for p in sorted(pp, key=lambda x: [q["p"] for q in periods].index(x), reverse=True):
            for u in pp[p]:
                if u not in sira:
                    sira.append(u)
        for u in sira:
            if u not in K:
                K[u] = dict(aday[u], ek=1)
        g["parca"] = sira
        g["parca_p"] = pp
        g["tam"] = bool(pp)
    # ---------------- metin göstergeleri
    kpi = {}
    for m in metin:
        u = eslestir(m["rd"])
        if not u:
            continue
        for k, (v, tur) in (m.get("g") or {}).items():
            kpi.setdefault(k, {"tur": tur, "seri": {}, "kaynak": {}})
            kpi[k]["seri"][pkey[u]] = v
            kpi[k]["kaynak"][pkey[u]] = m["u"]
    # yılbaşından (ytd) → tek çeyrek
    pq = {p["p"]: p for p in periods}
    for k in [k for k in kpi if kpi[k]["tur"] == "ytd"]:
        Y = kpi[k]["seri"]
        tek = {}
        for p, v in Y.items():
            P = pq[p]
            if P["q"] == 1:
                tek[p] = v
            else:
                onceki = f"{P['fy']}Q{P['q'] - 1}"
                if onceki in Y:
                    tek[p] = round(v - Y[onceki], 2)
        kpi[k.replace("_ytd", "")] = {"tur": "q", "seri": tek, "kaynak": kpi[k]["kaynak"], "ytd": k}
    return mix, kpi


# ---------------------------------------------------------------- türetilmiş göstergeler ve açıklamalar
KPI_AD = {  # anahtar: (ad, birim, açıklama)
    "dap": ("Günlük aktif kişi (DAP)", "milyar", "Facebook, Instagram, Messenger veya WhatsApp'tan en az birini her gün kullanan tekil kişi sayısı; çeyreğin son ayı ortalaması."),
    "arpp": ("Kişi başı gelir (ARPP)", "$", "Uygulama ailesi gelirinin ortalama DAP'a bölümü; çeyreklik."),
    "imp_g": ("Reklam gösterimi · yıllık değişim", "%", "Uygulama ailesinde gösterilen reklam sayısındaki yıllık değişim."),
    "ppa_g": ("Reklam başı fiyat · yıllık değişim", "%", "Reklam başına ortalama fiyattaki yıllık değişim."),
    "calisan": ("Çalışan sayısı", "kişi", "Dönem sonu çalışan sayısı."),
    "uretim": ("Araç üretimi", "bin adet", "Tek çeyrek; 10-Q'daki yılbaşından birikimli (yuvarlanmış) rakamların farkı, yaklaşık."),
    "teslimat": ("Araç teslimatı", "bin adet", "Tek çeyrek; 10-Q'daki yılbaşından birikimli (yuvarlanmış) rakamların farkı, yaklaşık."),
    "depolama": ("Enerji depolama kurulumu", "GWh", "Tek çeyrek kurulan Megapack/Powerwall kapasitesi; yılbaşından birikimli rakamların farkı."),
    "azure_g": ("Azure ve diğer bulut · yıllık büyüme", "%", "Microsoft'un 10-Q'da açıkladığı Azure gelir büyümesi."),
    "mcloud_g": ("Microsoft Cloud · yıllık büyüme", "%", "Azure, Microsoft 365 ticari bulut, Dynamics 365 bulut ve diğer bulut gelirleri."),
    "m365c_g": ("Microsoft 365 ticari bulut · yıllık büyüme", "%", ""),
    "tiklama_g": ("Ücretli tıklama · yıllık değişim", "%", "Google arama ve diğer mülklerde ücretli tıklama sayısı."),
    "tbm_g": ("Tıklama başı maliyet · yıllık değişim", "%", "Reklamverenin tıklama başına ödediği ortalama tutar."),
    "gosterim_g": ("Network gösterimleri · yıllık değişim", "%", ""),
    "tbg_g": ("Gösterim başı maliyet · yıllık değişim", "%", ""),
    "tac_oran": ("Trafik edinme maliyeti (TAC) oranı", "%", "Dağıtım ve Network ortaklarına ödenen payın reklam gelirine oranı; düşmesi kârlılığa olumlu."),
}


def _s(mix, key, uye):
    g = mix.get(key)
    return (g or {}).get("kalem", {}).get(uye, {}).get("seri", {}) if g else {}


def tureve(t, mix, kpi, periods):
    P = [p["p"] for p in periods]
    tot = {p["p"]: p.get("rev") for p in periods}

    def oran(a, b, k, ad_, acik, ters=False, yuzde=True):
        seri = {}
        for p in P:
            if a.get(p) is not None and b.get(p):
                seri[p] = round(100 * a[p] / b[p], 2) if yuzde else round(a[p] / b[p], 2)
        if len(seri) >= 2:
            kpi[k] = {"tur": "q", "seri": seri, "ad": ad_, "birim": "%", "aciklama": acik, "turev": 1}

    def marj(cogs, rev, k, ad_, acik):
        seri = {p: round(100 * (1 - cogs[p] / rev[p]), 2) for p in P if cogs.get(p) is not None and rev.get(p)}
        if len(seri) >= 2:
            kpi[k] = {"tur": "q", "seri": seri, "ad": ad_, "birim": "%", "aciklama": acik, "turev": 1}

    def tutar(seri, k, ad_, acik, birim="mn $"):
        if len(seri) >= 2:
            kpi[k] = {"tur": "q", "seri": seri, "ad": ad_, "birim": birim, "aciklama": acik, "turev": 1}

    # her faaliyet bölümü için faaliyet marjı
    segr, sego = mix.get("rev:segment", {}).get("kalem", {}), mix.get("op:segment", {}).get("kalem", {})
    for u, k in sego.items():
        if u in segr and any(abs(k["seri"].get(p, 0) / segr[u]["seri"][p]) > 1 for p in segr[u]["seri"] if segr[u]["seri"][p]):
            if t != "META":
                tutar(k["seri"], "sonuc_" + u, f"{k['ad']} · faaliyet sonucu", f"{k['ad']} bölümünün çeyreklik faaliyet kârı/zararı; hasılatı küçük olduğu için marj anlamlı değil.")
            continue
        if u in segr:
            oran(k["seri"], segr[u]["seri"], "marj_" + u, f"{k['ad']} · faaliyet marjı", f"{k['ad']} bölümünün faaliyet kârı ÷ bölüm hasılatı (tek çeyrek).")
    if t == "AAPL":
        r, c = mix.get("rev:urun", {}).get("kalem", {}), mix.get("cogs:urun", {}).get("kalem", {})
        if "ServiceMember" in r and "ServiceMember" in c:
            marj(c["ServiceMember"]["seri"], r["ServiceMember"]["seri"], "hizmet_bm", "Hizmetler brüt marjı", "App Store, iCloud, Apple Music, AppleCare, reklam ve ödeme hizmetlerinin brüt marjı.")
            oran(r["ServiceMember"]["seri"], tot, "hizmet_pay", "Hizmetlerin hasılat payı", "Hizmet gelirlerinin toplam hasılat içindeki payı.")
        if "ProductMember" in r and "ProductMember" in c:
            marj(c["ProductMember"]["seri"], r["ProductMember"]["seri"], "urun_bm", "Ürün brüt marjı", "iPhone, Mac, iPad ve giyilebilir cihazların toplam brüt marjı.")
        if "IPhoneMember" in r:
            oran(r["IPhoneMember"]["seri"], tot, "iphone_pay", "iPhone'un hasılat payı", "")
        g = mix.get("rev:segment", {}).get("kalem", {})
        if "GreaterChinaSegmentMember" in g:
            oran(g["GreaterChinaSegmentMember"]["seri"], tot, "cin_pay", "Büyük Çin'in hasılat payı", "Çin, Hong Kong ve Tayvan.")
    if t == "TSLA":
        r, c = mix.get("rev:urun", {}).get("kalem", {}), mix.get("cogs:urun", {}).get("kalem", {})
        if "AutomotiveSalesMember" in r and "AutomotiveSalesMember" in c:
            marj(c["AutomotiveSalesMember"]["seri"], r["AutomotiveSalesMember"]["seri"], "oto_bm", "Otomotiv brüt marjı (karbon kredisi hariç)", "Araç satış geliri ve maliyetinden; karbon (düzenleyici) kredileri ve kiralama hariç. Tesla'nın en çok izlenen kârlılık göstergesi.")
        if "AutomotiveRevenuesMember" in r and "AutomotiveRevenuesMember" in c:
            marj(c["AutomotiveRevenuesMember"]["seri"], r["AutomotiveRevenuesMember"]["seri"], "oto_bm_top", "Otomotiv brüt marjı (toplam)", "Karbon kredileri ve kiralama dahil.")
        if "EnergyGenerationAndStorageMember" in r and "EnergyGenerationAndStorageMember" in c:
            marj(c["EnergyGenerationAndStorageMember"]["seri"], r["EnergyGenerationAndStorageMember"]["seri"], "enerji_bm", "Enerji brüt marjı", "Enerji üretimi ve depolama işinin brüt marjı.")
        if "AutomotiveRegulatoryCreditsMember" in r:
            tutar(r["AutomotiveRegulatoryCreditsMember"]["seri"], "kredi", "Karbon kredisi geliri", "Diğer üreticilere satılan düzenleyici kredilerden gelir; maliyeti yok denecek kadar az, doğrudan kâra yazılır.")
        if "teslimat" in kpi and "AutomotiveSalesMember" in r:
            s = {p: round(1000 * r["AutomotiveSalesMember"]["seri"][p] / kpi["teslimat"]["seri"][p], 1) for p in P if p in kpi["teslimat"]["seri"] and kpi["teslimat"]["seri"][p] and p in r["AutomotiveSalesMember"]["seri"]}
            tutar(s, "arac_basi", "Araç başı satış geliri", "Otomotiv satış geliri ÷ teslimat (yaklaşık; teslimat yuvarlanmış).", "$")
    if t == "AMZN":
        r = mix.get("rev:urun", {}).get("kalem", {})
        for u, k_, a_ in (("AdvertisingServicesMember", "reklam_pay", "Reklamın hasılat payı"), ("AmazonWebServicesMember", "aws_pay", "AWS'nin hasılat payı"), ("SubscriptionServicesMember", "abone_pay", "Aboneliklerin hasılat payı")):
            if u in r:
                oran(r[u]["seri"], tot, k_, a_, "")
        o = mix.get("op:segment", {}).get("kalem", {})
        if "AmazonWebServicesSegmentMember" in o:
            top = {p["p"]: p.get("op") for p in periods}
            oran(o["AmazonWebServicesSegmentMember"]["seri"], top, "aws_kar_pay", "AWS'nin faaliyet kârı payı", "AWS faaliyet kârı ÷ toplam faaliyet kârı.")
    if t == "GOOGL":
        r = mix.get("rev:urun", {}).get("kalem", {})
        for u, k_, a_ in (("GoogleCloudMember", "cloud_pay", "Google Cloud'un hasılat payı"), ("YouTubeAdvertisingRevenueMember", "yt_pay", "YouTube reklamlarının hasılat payı")):
            src = r.get(u) or mix.get("rev:segment", {}).get("kalem", {}).get(u)
            if src:
                oran(src["seri"], tot, k_, a_, "")
        rp = mix.get("rpo:segment", {}).get("kalem", {}).get("GoogleCloudMember")
        if rp:
            tutar(rp["seri"], "cloud_rpo", "Google Cloud sipariş birikimi (RPO)", "Google Cloud'un henüz gelire dönüşmemiş sözleşmeli tutarı (kalan edim yükümlülüğü).")
    if t == "MSFT":
        r = mix.get("rev:urun", {}).get("kalem", {})
        if "AzureMember" in r:
            tutar(r["AzureMember"]["seri"], "azure", "Azure geliri", "Mali yıl 2027'den itibaren ayrı açıklanıyor.")
        mc = mix.get("rev:urun2", {}).get("kalem", {}).get("MicrosoftCloudMember")
        if mc:
            tutar(mc["seri"], "mcloud", "Microsoft Cloud geliri", "Azure, Microsoft 365 ticari bulut, Dynamics 365 ve diğer bulut gelirleri.")
        rp = mix.get("rpo:musteri", {}).get("kalem", {}).get("CommercialCustomersMember")
        if rp:
            tutar(rp["seri"], "ticari_rpo", "Ticari sipariş birikimi (RPO)", "Ticari müşterilerle imzalanmış, henüz gelire dönüşmemiş sözleşmeler.")
    if t == "NVDA":
        r = mix.get("rev:urun", {}).get("kalem", {})
        if "DataCenterMember" in r:
            oran(r["DataCenterMember"]["seri"], tot, "dc_pay", "Veri merkezinin hasılat payı", "Yapay zekâ hızlandırıcıları ve ağ ürünleri.")
        b = mix.get("rev:bolge", {}).get("kalem", {})
        if "ChinaIncludingHongKongMember" in b:
            oran(b["ChinaIncludingHongKongMember"]["seri"], tot, "cin_pay", "Çin'in (Hong Kong dahil) hasılat payı", "Faturalama adresine göre; ihracat kısıtlarının etkisini izlemek için.")
    if t == "META":
        o = mix.get("op:segment", {}).get("kalem", {})
        if "RealityLabsMember" in o:
            tutar(o["RealityLabsMember"]["seri"], "rl_zarar", "Reality Labs faaliyet sonucu", "Sanal/artırılmış gerçeklik ve giyilebilir cihazlara yatırımın çeyreklik faaliyet zararı.")
    # toplam RPO
    rp = mix.get("rpo:_", {}).get("kalem", {}).get("_")
    if rp:
        tutar(rp["seri"], "rpo", "Toplam sipariş birikimi (RPO)", "Henüz gelire dönüşmemiş toplam sözleşmeli tutar (kalan edim yükümlülüğü).")
    for k, v in kpi.items():
        if k in KPI_AD:
            v.setdefault("ad", KPI_AD[k][0]); v.setdefault("birim", KPI_AD[k][1]); v.setdefault("aciklama", KPI_AD[k][2])
    return {k: v for k, v in kpi.items() if not k.endswith("_ytd") and v.get("seri")}
