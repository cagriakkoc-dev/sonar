"""Sonar Bekçi: KAP'ta izlenen şirketlerin yeni bildirimlerini izler, Telegram'a yollar.
Claude kullanmaz; GitHub Actions'ta çalışır. Durum: bekci/state.json"""
import json, os, re, urllib.request, datetime, time

SIRKETLER = {
    "AGESA": "4028e4a140e95bea0140edeb7a54015d",
    "AKSA": "4028e4a240f2ef470141175e189f0453",
    "ANHYT": "4028e4a140e95be70140ed40cb930098",
    "AVPGY": "8acae2c48c3efabf018c4824da4a0623",
    "FROTO": "4028e4a140f2ed71014106890fae0138",
    "ISMEN": "4028e4a140f275530140f277aa100008",
    "TUPRS": "4028e4a140f2ed720140f37f139c01bc",
    "TOASO": "4028e4a140f2ed710140f328bed700a5",
    "TTRAK": "4028e4a140f2ed720140f3790d6a01ad",
    "AFYON": "4028e4a24158e42401415af83d607fd3",
    "AKCNS": "4028e4a140e8cfa00140e92b0c380016",
    "BASCM": "4028e4a140f2ed7201413a4092720892",
    "BTCIM": "4028e4a140e95be70140ee07044700eb",
    "BSOKE": "4028e4a24158e42401415920fc3308c5",
    "BUCIM": "4028e4a140ee35c00140ee41a5e4000f",
    "CMENT": "4028e4a24158e42401415ad34c7f7db7",
    "CIMSA": "4028e4a240ee866c0140f1f64bdb0014",
    "GOLTS": "4028e4a140e95be70140ee27ccd40129",
    "KONYA": "4028e4a140f2ed720140f3014c9400cf",
    "LMKDC": "8acae2c58b2fa64e018d8cfe461558d3",
    "NUHCM": "4028e4a141558bdd014156053d9f04b2",
    "OYAKC": "4028e4a140f2ed720140f32377aa016c",
    "A1CAP": "4028e4a1416e696301416f37201c5f2e",
    "GEDIK": "4028e4a140e95bea0140ee1edd700174",
    "GLBMD": "4028e4a140e95bea0140ee21b10d0188",
    "INFO": "4028e4a2416e696c01416edd30ca3148",
    "OSMEN": "4028e4a240ee37a30140ee408ef80002",
    "OYYAT": "4028e4a14158e41f01415a5e854d4441",
    "TERA": "4028e4a141733b56014178115f7e51e7",
    "AKSGY": "4028e4a14158e41f01415a865c0e4d13",
    "ISGYO": "4028e4a140f2ed7201412acbeb8b06f7",
    "RGYAS": "4028e4a241b612d80141d9a52e2a2727",
    "TRGYO": "4028e4a1413b7ef5014144f83882011f",
    "DOAS": "4028e4a240e8d16e0140e951bf04007b",
    "OTKAR": "4028e4a140ee35c70140ee4316b3001d",
    "KARSN": "4028e4a140f275530140f2e357a501f7",
    "ASUZU": "4028e4a140e95be70140ed43c4fe00a9",
    "BFREN": "4028e4a140e95bea0140ee30fb6001b9",
    "BRISA": "4028e4a140e95bea0140ee33bff201cd",
    "DITAS": "4028e4a140f2ed710141179798bb02ed",
    "DOKTA": "4028e4a241558bd9014155c9b19e03b7",
    "EGEEN": "1DE05DAA8254073AE0530A4A622A2EBD",
    "FMIZP": "4028e4a240f2ef4701410bb5cdab01cf",
    "GOODY": "4028e4a140f2ed7101412bfc6f340359",
    "JANTS": "4028e4a240f2ef4c01413b1b57300719",
    "PARSN": "4028e4a140ee84900140f1ecef250011",
    "AAGYO": "8acae2c49c81f743019d2dfb40633db8",
    "ADGYO": "8acae2c586d22c53018a737800f804ae",
    "AGYO": "4028e4a240f2ef4c0141164a06d8043a",
    "AHSGY": "8acae2c59145e00a01915a44a01d1179",
    "AKFGY": "4028e4a141733b56014183c1c6ed426e",
    "AKMGY": "4028e4a240e95dc30140ecc218b30032",
    "ALGYO": "4028e4a241462fd801415005df1c3612",
    "ASGYO": "8acae2c562329bd1016464c3796e08a0",
    "ATAGY": "4028e4a140e95bea0140eddf432a0115",
    "AVGYO": "4028e4a240f2ef4c0141029cf7680164",
    "BASGZ": "4028e4a240f2ef4701413a3410a605ce",
    "BEGYO": "8acae2c48b2fa25a018c01ae7c3973de",
    "BKRGY": "8acae2c59f52dae901a02330241164cb",
    "DGGYO": "4028e4a140e8cfa00140e9497d32002f",
    "DZGYO": "4028e4a240ee866c0140f1fad94e0047",
    "EGEGY": "8acae2c59145e00e019406e89bc4222c",
    "EKGYO": "4028e4a2422d9a780142513cda5b232e",
    "EYGYO": "8acae2c48304fe9c01843d2398a50797",
    "FZLGY": "8acae2c586d22c530189534dc2624568",
    "HLGYO": "4028e4a240ee37a30140ee53e47c0057",
    "IDGYO": "4028e4a14184e9c901419d6d716e6b19",
    "KGYO": "4028e4a240f2ef4c0141176f57ca04a5",
    "KLGYO": "4028e4a2415f4f8101415f7009a809a2",
    "KRGYO": "4028e4a244a081810146002d6e0c555f",
    "KZBGY": "8acae2c5794d3d66017aadf2b6b719cb",
    "KZGYO": "8acae2c586d22c53018a02754e924a33",
    "LXGYO": "8acae2c59b85fa03019c74a891e94f5d",
    "MHRGY": "8acae2c486d22a3a018b03ad439129a9",
    "MRGYO": "4028e4a1415f4d9b0141603d2b414108",
    "MSGYO": "8acae2c4540d444501545d374f8d070a",
    "NUGYO": "4028e4a1416e696301416f6100e76fb9",
    "OZGYO": "4028e4a140ee35c70140ee582a75003c",
    "OZKGY": "4028e4a140f2ed720141079632d0024f",
    "PAGYO": "4028e4a240f2ef4c014134d6641f062a",
    "PEKGY": "8acae2c55fc6011001617acbeb1b48da",
    "PSGYO": "8acae2c4794d364a017a51e9e5d256c9",
    "RYGYO": "4028e4a140ee847b0140f20278c00023",
    "SEGYO": "8acae2c56faf888c01718864329b7097",
    "SNGYO": "4028e4a14184e9cf01419c0168dd5a87",
    "SRVGY": "4028e4a1416e696501416f80a3377c4b",
    "SURGY": "8acae2c48b2fa25a018c33a0808a03b0",
    "SVGYO": "8acae2c59b85fa03019c74a8cf6a4f62",
    "TDGYO": "8acae2c45fc5ff9d01613299f17a2065",
    "TSGYO": "4028e4a240f2ef470140f37174c600a7",
    "VKGYO": "4028e4a140f2ed72014101a0d3b501f7",
    "VRGYO": "8acae2c486d22a3a018b27e15c37493e",
    "YGGYO": "4028e4a241733d4201417cda3f421321",
    "ZERGY": "8acae2c5998f25d7019aed48b7597a50",
    "ZGYO": "8acae2c5998f25d7019b732d4d683a5c",
    "ZRGYO": "8acae2c45835eb660158bfedd32d3332",
    "EREGL": "4028e4a240e95dc90140ede4c12a0133",
    "ISDMR": "4028e4a2416e696c01416ee8eb7b3770",
    "KRDMD": "4028e4a140f2ed7201412ace3ada0707",
    "KCAER": "4028e4a2416f888d01416f9ea04a058f",
    "EKDMR": "4028e4a241558bd9014155d8e91505c8",
    "IZMDC": "4028e4a140f275550140f27e319401ca",
    "KOCMT": "4028e4a2416e696c01416f734ce273ad",
    "CEMTS": "4028e4a140ee84900140f1f334ce0025",
    "BRSAN": "4028e4a140f2ed7201412ac9ca5d06e6",
    "BURCE": "4028e4a14158e41e01415b2636586ca7",
    "CELHA": "4028e4a240f2ef4c0141164dd92d044c",
    "ERBOS": "4028e4a14184e9cf01419c006da45a78",
    "ERCB": "2af53003ee3c4464b0b653225816518d",
    "DOGUB": "4028e4a141e536460141ee618a972cf0",
    "YKSLN": "8acae2c569cee403016a6e925a8b5bd8",
    "BMSTL": "8acae2c47f7cb49201802bda6cbf6b77",
    "BMSCH": "8acae2c56eccfc0c016f18f5b1e21747",
    "AYES": "4028e4a1416f846101416f85f6730028",
    "KARCL": "4028e4a1422d986901426b87f6a905e5",
    "AKBNK": "4028e4a240e8d1830140e905edcd0006",
    "ALBRK": "4028e4a240f2ef4c014106a1c5ef016d",
    "GARAN": "4028e4a140f2ed720140f37cb2a601b7",
    "HALKB": "1DE05DAA82C3073AE0530A4A622A2EBD",
    "ISCTR": "4028e4a140f2ed7201411682b0cb05c6",
    "TSKB": "4028e4a140f2ed710140f3831c6300fd",
    "VAKBN": "4028e4a1415f4d9b01415fe3340f36e4",
    "YKBNK": "4028e4a240f2ef4c01412ae6d6630538",
    "ANSGR": "4028e4a140e95bea0140ed21b5c10078",
    "TURSG": "4028e4a140e95be70140ee2f466d0159",
    "AGHOL": "4028e4a240f2ef4c014101b18dc000f7",
    "ALARK": "4028e4a241462fd80141500c738e36be",
    "BINHO": "8acae2c48b2fa25a018bba0a5034596d",
    "BRYAT": "4028e4a1415f4d9b0141603cd3904103",
    "DOHOL": "4028e4a141462df201414ff732983087",
    "ECZYT": "4028e4a1415f4d9901416012a278321f",
    "GLYHO": "4028e4a140e95bea0140ee24416e0197",
    "KCHOL": "4028e4a140f2ed710140f2f4d6c70039",
    "PAHOL": "8acae2c4998f24d8019a5ffde32b0e5a",
    "SAHOL": "4028e4a240ee37a90140ee50087e000b",
    "AEFES": "4028e4a140e95bea0140ed2fde10009d",
    "AHGAZ": "4028e4a14203278a0142095715f914d0",
    "AKFYE": "8acae2c48304fe9e0186a66e7a9568ea",
    "AKSEN": "4028e4a241733d42014179341a147ddb",
    "ALTNY": "8acae2c58b2fa64e018f3d2d712476e2",
    "ARCLK": "4028e4a240e95dc90140ed55b43900cf",
    "ASELS": "4028e4a1413b7ef401413bc2251e0047",
    "ASTOR": "8acae2c562329bd10164405fe6c17996",
    "AYGAZ": "4028e4a140e95be70140ee03bd6000e0",
    "BIMAS": "4028e4a140e95be70140ee1b7b030119",
    "CANTE": "8acae2c578080f31017811f4dca6032d",
    "CCOLA": "4028e4a140ee35c00140ee586bdd0034",
    "CVKMD": "8acae2c586d22c510187381ba299429a",
    "CWENE": "8acae2c56faf888c016fd6c2036e0a5d",
    "ECILC": "4028e4a1415f4d99014160034b683108",
    "EGGUB": "4028e4a2422d9a78014304d729e3673d",
    "ENERY": "4028e4a241733d4201417937d4337e22",
    "ENJSA": "4028e4a1422d98690142bceaa31957cf",
    "ENKAI": "4028e4a240e95dc90140ed3883fe0093",
    "ENTRA": "8acae2c48c3efabf018e64e77b5d3e77",
    "EUREN": "8acae2c580e91030018105632b470bcd",
    "GLRMK": "4028e4a1416e696301416f392897603f",
    "GRSEL": "8acae2c47d3bee50017f2c2fc65150e6",
    "GUBRF": "4028e4a241733d4a01417989f3760a4d",
    "GWIND": "8acae2c46d7599a6016dee0b5aec36b2",
    "HEKTS": "4028e4a140ee35c00140ee5d194a0055",
    "KATMR": "4028e4a14184e9cf01419c001e945a74",
    "KORDS": "4028e4a140f2ed720140f30606a700ec",
    "MAVI": "4028e4a141733b5101417ea9aae11fec",
    "MGROS": "4028e4a141462df2014150162e1c3424",
    "MPARK": "4028e4a1462cc5dd01465c9550782baa",
    "OBAMS": "8acae2c58b2fa64e018dc01d63686b27",
    "ODAS": "4028e4a2416e696c01416edd70713183",
    "PETKM": "4028e4a240f2ef470141165c566a03e4",
    "PGSUS": "4028e4a2422d9a78014232e751bc22a4",
    "RYSAS": "4028e4a140ee847b0140f203980d0030",
    "SASA": "4028e4a240ee866c0140f20abd9500cc",
    "SISE": "4028e4a140f2ed710140f385d5690102",
    "SOKM": "4028e4a14184e9c9014198095f4442bf",
    "TABGD": "4028e4a141e536460141e5aa84740938",
    "TAVHL": "4028e4a140f2ed720140f31195ef010e",
    "TCELL": "4028e4a1486ec80a0148c55510d71d31",
    "TCKRC": "8acae2c48c3efac0019137973fd07e5e",
    "THYAO": "4028e4a140f2ed720140f376bebb01a7",
    "TKFEN": "4028e4a140f2ed720140f31367840112",
    "TRALT": "4028e4a2422d9a6e0142bd91d3687a69",
    "TRENJ": "4028e4a2422d9a6e0142bd9255a37a70",
    "TRMET": "4028e4a2422d9a6e0142bd921d307a6d",
    "TTKOM": "4028e4a241e538ab0141ea9c96912c8b",
    "TUKAS": "4028e4a240f2ef470140f373b77f00ac",
    "ULKER": "4028e4a14184e9c901419801438a422b",
    "VESTL": "4028e4a140f2ed7201412c2000c507db",
    "ZOREN": "4028e4a140f2ed7201412c19687407a7",
}
ONEMLI = re.compile(r"yatırım|sözleşme|ihale|temettü|kar pay|kâr pay|sermaye|geri alım|birleşme|devral|satın al|kapasite|genel müdür|finansal takvim|beklenti|yeni iş|teşvik|dava|derecelendirme|ortaklık yapısı|pay satış|bedelsiz|bedelli", re.I)
STATE = os.path.join(os.path.dirname(__file__), "state.json")
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()

# Rutin bildirimler: Telegram'a "Bildirim" olarak gider, özet kuyruğuna girmez
RUTIN = {t: re.compile(r"varant|sertifika|piyasa yapıcılı|ihraç belgesi|borçlanma aracı|faiz oranı|kupon", re.I) for t in ("ISMEN", "A1CAP", "GEDIK", "GLBMD", "INFO", "OSMEN", "OYYAT", "TERA")}
AD = {"ISMEN": re.compile(r"İş Yatırım|IS YATIRIM|İŞ YATIRIM", re.I)}

def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))

def kap(oid, gun=4):
    oids = oid if isinstance(oid, list) else [oid]
    bugun = datetime.date.today()
    body = {"fromDate": (bugun - datetime.timedelta(days=gun)).isoformat(), "toDate": bugun.isoformat(),
            "memberType": "IGS", "mkkMemberOidList": oids, "inactiveCompanies": "N", "bdkMemberOidList": [],
            "subjectList": [], "srcCategory": "", "index": "", "market": "", "isLate": "", "term": "",
            "ruleType": "", "period": "", "year": "", "disclosureClass": ""}
    return http("https://www.kap.org.tr/tr/api/disclosure/members/byCriteria", json.dumps(body).encode(),
                {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0 Sonar-Bekci"})

KUYRUK = os.path.join(os.path.dirname(__file__), "kuyruk.json")
BILDIR = os.path.join(os.path.dirname(__file__), "bildirimler.json")
GELEN = os.path.join(os.path.dirname(__file__), "gelen")
UA = {"User-Agent": "Mozilla/5.0 Sonar-Bekci"}

def indir(i):
    """Bildirim sayfasını ve eklerini bekci/gelen/<id>/ altına kaydeder."""
    d = os.path.join(GELEN, str(i)); os.makedirs(d, exist_ok=True)
    req = urllib.request.Request(f"https://www.kap.org.tr/tr/Bildirim/{i}", headers=UA)
    html = urllib.request.urlopen(req, timeout=60).read()
    open(os.path.join(d, "bildirim.html"), "wb").write(html)
    ekler = sorted(set(re.findall(rb"file/download/([0-9a-f]{32})", html)))
    out = []
    for oid in ekler[:6]:
        oid = oid.decode()
        try:
            r = urllib.request.urlopen(urllib.request.Request(f"https://www.kap.org.tr/tr/api/file/download/{oid}", headers=UA), timeout=90)
            b = r.read()
            if len(b) > 40_000_000: continue
            ext = ".pdf" if b[:4] == b"%PDF" else ".bin"
            open(os.path.join(d, oid + ext), "wb").write(b); out.append(oid + ext)
        except Exception as e:
            print("ek indirilemedi", i, oid, repr(e)[:120])
    return ["bildirim.html"] + out

def tg(method, **params):
    return http(f"https://api.telegram.org/bot{TOKEN}/{method}", json.dumps(params).encode(), {"Content-Type": "application/json"})

def main():
    st = json.load(open(STATE)) if os.path.exists(STATE) else {"seen": [], "chat_id": None}
    ilk = not st["seen"]
    seen = set(st["seen"])
    yeni = []
    # listeye yeni eklenen şirketin geçmiş bildirimleri sessizce görülmüş sayılır (kuyruk/Telegram yok)
    hata = {}
    izlenen = set(st.get("izlenen") or ([] if ilk else ["AGESA", "AKSA", "ANHYT", "AVPGY", "FROTO", "ISMEN", "TUPRS"]))
    # KAP'a şirket başına istek 173 şirkette 429 (Request Limit Exceeded) veriyordu: 25'erli gruplarla sorulur.
    L = list(SIRKETLER.items())
    for g0 in range(0, len(L), 25):
        grup = dict(L[g0:g0 + 25]); oids = list(grup.values())
        for deneme in range(3):
            try:
                R = kap(oids); break
            except Exception as e:
                R = None; print("KAP hatası (grup", g0, "):", repr(e)[:150])
                if deneme < 2: time.sleep(20 * (deneme + 1))
        if R is None:
            for t in grup: hata[t] = "grup isteği başarısız"
            continue
        for d in R:
            kods = [k.strip() for k in (d.get("stockCodes") or "").split(",")]
            t = next((k for k in kods if k in grup), None)
            if not t: continue
            i = d["disclosureIndex"]
            if i not in seen:
                seen.add(i)
                if t in izlenen: yeni.append((t, d))
        izlenen.update(grup)
        time.sleep(2)
    st["izlenen"] = sorted(izlenen)
    st["kap_hata"] = {"n": len(hata), "ornek": dict(list(hata.items())[:5]), "izlenmeyen": sorted(set(SIRKETLER) - izlenen)}
    if TOKEN and not st.get("chat_id"):
        try:
            print("bot:", tg("getMe").get("result", {}).get("username"))
            ups = tg("getUpdates").get("result", [])
            print("telegram güncelleme sayısı:", len(ups))
            for u in reversed(ups):
                m = u.get("message") or {}
                if m.get("chat", {}).get("type") == "private":
                    st["chat_id"] = m["chat"]["id"]; break
        except Exception as e:
            print("Telegram getUpdates hatası:", repr(e)[:200])
    mesajlar = []
    kuyruk = json.load(open(KUYRUK)) if os.path.exists(KUYRUK) else []
    bekleyen_bildirim = json.load(open(BILDIR)) if os.path.exists(BILDIR) else []
    if TOKEN and st.get("chat_id") and not st.get("welcomed"):
        mesajlar.append("Sonar Bekçi çalışmaya başladı. " + ", ".join(SIRKETLER) + " için KAP bildirimlerini izliyorum. Yeni bildirim geldiğinde buraya yazacağım.")
        st["welcomed"] = True
    if not ilk:
        for t, d in sorted(yeni, key=lambda x: x[1]["disclosureIndex"]):
            fr = d.get("disclosureClass") == "FR"
            metin = (d.get("summary") or "") + " " + (d.get("subject") or "")
            rutin = not fr and t in RUTIN and RUTIN[t].search(metin)
            if t in AD: metin = AD[t].sub(" ", metin)  # şirket adındaki "Yatırım" Önemli sayılmasın
            etiket = "Finansal rapor" if fr else ("Önemli" if not rutin and ONEMLI.search(metin) else "Bildirim")
            donem = f" · {d['year']} {d['ruleType']}" if fr and d.get("year") else ""
            if etiket in ("Finansal rapor", "Önemli") and "Sorumluluk Beyan" not in (d.get("summary") or ""):
                try:
                    dosyalar = indir(d["disclosureIndex"])
                except Exception as e:
                    dosyalar = []; print("indirme hatası", d["disclosureIndex"], repr(e)[:150])
                kuyruk.append({"id": d["disclosureIndex"], "hisse": t, "tur": etiket, "ozet": d.get("summary") or d.get("subject"),
                               "tarih": d.get("publishDate"), "yil": d.get("year"), "donem": d.get("ruleType"), "durum": "bekliyor", "dosyalar": dosyalar})
            mesajlar.append(f"{t} · {etiket}{donem}\n{d.get('summary') or d.get('subject')}\n{d.get('publishDate','')}\nhttps://www.kap.org.tr/tr/Bildirim/{d['disclosureIndex']}")
    # elle kuyruğa ekleme (test / geçmiş bildirim): KUYRUGA_EKLE="ANHYT:1687664,AKSA:123"
    for parca in filter(None, os.environ.get("KUYRUGA_EKLE", "").replace(" ", "").split(",")):
        t, i = parca.split(":"); i = int(i)
        if any(k["id"] == i for k in kuyruk): continue
        try:
            d = next((x for x in kap(SIRKETLER[t], gun=30) if x["disclosureIndex"] == i), {})
            kuyruk.append({"id": i, "hisse": t, "tur": "Finansal rapor" if d.get("disclosureClass") == "FR" else "Önemli",
                           "ozet": d.get("summary") or d.get("subject"), "tarih": d.get("publishDate"), "yil": d.get("year"),
                           "donem": d.get("ruleType"), "durum": "bekliyor", "dosyalar": indir(i)})
            print("elle kuyruğa eklendi", t, i)
        except Exception as e:
            print("elle ekleme hatası", parca, repr(e)[:150])
    # SPK bültenleri / SPK basın duyuruları / Borsa İstanbul duyuruları (bekci/duzenleyici.py → bekci/duyurular.json)
    try:
        import duzenleyici
        dm, dh = duzenleyici.tara()
        mesajlar += dm
        st["duyuru_hata"] = dh
    except Exception as e:
        print("duyuru taraması hatası:", repr(e)[:200]); st["duyuru_hata"] = [repr(e)[:80]]
    mesajlar += bekleyen_bildirim
    try:
        import datetime
        open("/tmp/sonar_son_kontrol", "w").write((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)).strftime("%d.%m.%Y %H:%M"))
    except Exception:
        pass
    if os.environ.get("TETIK") == "1" and not mesajlar:
        mesajlar.append("Kontrol tamam: yeni KAP bildirimi yok.")
    print(f"yeni bildirim: {len(yeni)}, ilk çalışma: {ilk}, mesaj: {len(mesajlar)}")
    if mesajlar and TOKEN and st.get("chat_id"):
        for m in mesajlar:
            try:
                tg("sendMessage", chat_id=st["chat_id"], text=m, disable_web_page_preview=True)
            except Exception as e:
                print("Telegram gönderim hatası:", repr(e)[:200])
    elif mesajlar:
        print("Telegram ayarlı değil; mesajlar gönderilmedi.")
    if bekleyen_bildirim and TOKEN and st.get("chat_id"):
        json.dump([], open(BILDIR, "w"))
    json.dump(kuyruk, open(KUYRUK, "w"), ensure_ascii=False, indent=1)
    st["seen"] = sorted(seen)[-1500:]
    st["last_run"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
