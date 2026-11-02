# Sonar otomatik akış · Claude görevi talimatı

Bu dosyayı zamanlanmış Claude görevi her çalıştığında izler. Kısa ve ucuz olmalı: iş yoksa hemen bitir.

## 0. İş var mı?
`curl -s https://raw.githubusercontent.com/cagriakkoc-dev/sonar/main/bekci/kuyruk.json`
"durum": "bekliyor" olan kayıt yoksa HİÇBİR ŞEY YAPMA, kısa bir cümleyle bitir (dosya okuma, Mac, proje yok).

## 1. Hazırlık (yalnız iş varsa)
İki depo var (27 Eki 2026'dan beri):
- **cagriakkoc-dev/sonar** (açık): KAP bekçisi. `bekci/kuyruk.json`, `bekci/gelen/<id>/`, `bekci/bildirimler.json`, `bekci/araclar/kap_oku.py`, bu dosya. Site buradan yayınlanır ama yalnız `public/` klasörü (otomatik üretilir, ELLE DÜZENLEME).
- **cagriakkoc-dev/sonar-site** (özel): site kaynağı `index.html` (taslaklar, X/Substack, geliştirici notları dahil), `icerik/`, `bekci/araclar/site.py`. Buraya her push'ta `yayin.yml` açık siteyi ve şifreli yönetim panelini derleyip `sonar/public/`'e yazar.

- Mac (device_bash): `git clone` https://github.com/cagriakkoc-dev/sonar → `$HOME/fr-oto` ve https://github.com/cagriakkoc-dev/sonar-site → `$HOME/fr-site` (varsa ikisinde de `git pull --rebase`).
  Token: `$HOME/mnt/sonar/.gizli/github_token` (iCloud sonar klasörü). Klonlama/push: `git -c http.extraHeader="Authorization: Basic $(printf 'x-access-token:%s' $TOKEN | base64 -w0)" …`.
- Yazım dili: proje dokümanı `claude/smartcuzdan-yazim-dili.md` (Projects aracı varsa oku). Yoksa aşağıdaki kurallar yeterli.
- Bildirim dosyalarını `$HOME/fr-oto/bekci/gelen/<id>/` altından oku; `site.py` komutlarını `$HOME/fr-site` içinde çalıştır.

## 2. Her kayıt için
Dosyalar: `bekci/gelen/<id>/bildirim.html` (+ PDF ekler).
- Metin: `python3 bekci/araclar/kap_oku.py bekci/gelen/<id>/bildirim.html`
- XBRL tablo: `python3 bekci/araclar/kap_oku.py … --xbrl` (sigorta: satır 305–400 gelir tablosu; sütunlar cari birikimli | önceki birikimli | cari 3 ay | önceki 3 ay)
- PDF: `pdftotext -layout dosya.pdf -` (Mac'te yoksa ek okumadan devam et)

### "Önemli" (haber) → haber özeti
JSON (bkz. şema) yaz, `python3 bekci/araclar/site.py ekle-haber <HİSSE> haber.json`.
Şema: {"id": <bildirim no>, "date": "GG.AA.YYYY", "title": "<KAP başlığı>", "tur": "Önemli", "headline": "<tek cümle, olgu>",
 "bullets": ["<olgu 1>", "<olgu 2>", …], "context": "<varsa şirketin açıkladığı gerekçe/hedef>", "sources": [{"l": "KAP · <başlık>", "u": "https://www.kap.org.tr/tr/Bildirim/<id>"}],
 "social": {"tweets": [{"t": "<tweet>", "card": {"type": "facts", "head": "<HİSSE> · KAP · GG.AA.YYYY", "title": "<kısa başlık>", "rows": [["etiket", "değer"], …]}}, …, {"t": "<son tweet>", "card": null}]},
 "note": "Bu özet KAP açıklaması temel alınarak Claude tarafından yazıldı."}

#### Kâr payı / temettü bildirimi (Kar Dağıtım Önerisi, Kar Payı Dağıtımına İlişkin Bildirim)
Haber özetine ek olarak şirket sayfasındaki Temettü tablosu güncellenir (index.html veri JSON'u, şirketin `div` dizisi, ödeme yılı satırı):
- Yönetim kurulu önerisi (GK onayı bekliyor): o yılın satırına `"prop": {"g": brüt TL/pay, "n": net TL/pay (A grubu/işlem gören), "gy": brüt verim %, "ny": net verim %, "badge": "Öneri · GK GG.AA", "note": "<öneri tarihi, kaynak (dönem kârı/yedekler), GK tarihi, hak kullanım/ödeme tarihleri>", "src": [KAP linkleri], "news": <bildirim no>}`. Verim, satırdaki referans fiyatla hesaplanır (gy = g / (satırın g / gy)).
- GK onaylayıp ödeme kesinleşince: `prop` kaldırılır, tutar satırın `g`/`n`/`gy`/`ny` değerlerine eklenir, `src`'ye KAP linki eklenir.

### "Finansal rapor" → dönem özeti
Aynı hisse+dönemin bütün FR kayıtlarını birlikte işle (finansal rapor + faaliyet raporu). Şablon: `python3 bekci/araclar/site.py ornek ANHYT` (ANHYT 2026-09 özeti).
Yıllık = geçen yılın aynı çeyreği (XBRL "önceki 3 ay"), çeyreklik = bir önceki çeyrek (sitedeki c.fin tek çeyrek değeri veya önceki raporun 3 aylık sütunu).
Reel / nominal (1 Kas 2026 kuralı): TMS 29 uygulayan şirketlerde yıllık kıyas cari raporun karşılaştırma sütunundan alınır (aynı fiyat esası = reel); "basis" alanına mutlaka "<önceki yıl> değerleri <cari> raporunun karşılaştırma sütunundan (<ay yıl> fiyatları)" yazılır — site yıllık sütuna "reel" etiketini bu ifadeden koyar, yoksa "nominal" gösterir. Çeyreklik kıyas (önceki çeyrek kendi fiyatında) her zaman nominal. Bankalar, sigortacılar ve TMS 29 uygulamayanlar (c.no29) her yerde nominal. "take" metinlerinde ve X/Substack metinlerinde değişim oranı yazılırken esas belirtilir: "[[reel|reel]] %3,1", "[[reel|nominal]] %6,5" (X'te düz "reel"/"nominal"). Görsellerde başlık/alt satırda dönem esası ("tek çeyrek" / "9 ay birikimli") ve reel/nominal yazılır.
`python3 bekci/araclar/site.py ekle-ozet <HİSSE> ozet.json`. Dönem özeti yayında eklenir (onay yok; Cagri, 2 Kas); haber özetleri gizli başlar. Özeti yazdıktan sonra sayısal serileri de güncelle (aşağıda "Sayısal seriler güncellenince") ve özetin "note" alanına "Grafik serileri henüz güncellenmedi" yazma.
X kısmı ikili seri düzeninde: `"social": {"mode": "ikili", "tweets": [...]}`. Her tweet bir serinin ana tweeti (tek not + kendi kartı); yanıt ("Okumak için: <Substack linki>", ilk seride yalnız link) site tarafından substack.published'tan üretilir, JSON'a yazılmaz. 1. seri net kâr kartını anlatır ve "<YYYY>/<ay> bilançosunu Substack'te özetledim. Okumak için👇🏻" ile biter. Sonraki seriler: yıllık kıyas, çeyreklik kıyas, segment, vergi/diğer, rakip. Her ana tweet hisse adını içerir (ayrı paylaşılır). Kapanış/"Yatırım tavsiyesi değildir." tweeti yok; sıra numarası yok. İsteğe bağlı tek ek tweet: tweet nesnesine "ek". Sayısal serileri (c.fin) güncellemek bu sürümde YOK: özetin "note" alanına "Grafik serileri henüz güncellenmedi" yaz.

#### SPK ve Borsa İstanbul duyuruları (bekci/duzenleyici.py)
Bekçi her çalışmada SPK bültenleri (spk.gov.tr/spk-bultenleri/<yıl>-yili-spk-bultenleri), SPK basın duyuruları (spk.gov.tr/duyurular/basin-duyurulari/<yıl>) ve Borsa İstanbul duyurularını (borsaistanbul.com/duyurular) tarar; yenileri `bekci/duyurular.json`'a ekler (en yeni üstte, en çok 400) ve Telegram'a yollar. Bülten PDF'i (pypdf) ve duyuru sayfası okunup Sonar şirketleri "kod" (ve bültende bölüm adı "bol") olarak etiketlenir. Site bu dosyayı raw.githubusercontent.com'dan okur (/duyurular/ ve Haberler şeridi); özet yazmak, onay veya yayın gerekmez. Bu kayıtlar kuyruk.json'a girmez. Elle deneme: `python3 bekci/duzenleyici.py --kuru`. Düzeltmeler (panel): `bekci/duyuru_duzelt.json` — {"<id>": {gizli, t, kod_ekle, kod_cikar}, "ekle": [elle kayıtlar]}; duyurular.json'a elle dokunulmaz. Site, kabuk ve Telegram düzeltmeyi uygular (duzelt()).

#### Şirket sitelerinde yatırımcı sunumu (bekci/sunum.py)
Deneme listesi: TUPRS, ANHYT, AVPGY, FROTO, ISMEN, AKSA (sunum.py SITELER: url + bağlantı deseni; ANHYT JSON uç noktası). Şirket başına sayfa 6 saatte bir okunur; TUPRS ve FROTO ("aylik": sunum her ayın başında) ayın 1–3'ünde 30 dakikada bir; hata olursa 1 saat sonra. Yeni bağlantı → Telegram ("<HİSSE> · Yeni yatırımcı sunumu (şirket sitesi)") ve `bekci/sunumlar.json` (şirket başına son 12; site şirket sayfasında "Yatırımcı sunumları" kutusu, raw'dan okur). İlk okumada mevcut liste sessizce alınır. Yeni şirket eklemek: SITELER'e satır (sayfanın düz HTML'inde bağlantı görünmüyorsa tarayıcının ağ isteklerinden JSON uç noktasını bul). Elle deneme: `python3 bekci/sunum.py --kuru`.

#### Sayısal seriler güncellenince (c.fin)
Yeni dönem raporu gelince: XBRL `bekci/xbrl/<id>.json` (yoksa `bekci/gelen/<id>/bildirim.html` üzerinden `xbrl_cek.rows()` ile ya da xbrl.yml), şirketin klasöründe `fr_ids.json`'a dönem id'si, `build_fin.py` + `build_rat.py`, sonra `python3 bekci/araclar/genel/donem_guncelle.py bekci/araclar/<klasör> <HİSSE>` (yalnız periods/fin/rat/kap değişir; grup_ekle tanıtım ve sürücüleri sıfırlar, mevcut şirkete kullanma). Bir şirketin c.fin serilerine yeni dönem eklendiğinde, `$HOME/fr-site` içinde sırayla: `python3 bekci/araclar/genel/amortisman.py`, `python3 bekci/araclar/genel/netborc.py <HİSSE>`, `python3 bekci/araclar/genel/isletme.py <HİSSE>` (banka/sigorta/aracı kurumu kendisi atlar). isletme.py çalışmazsa şirket kartlarındaki alacak/stok/nakit akışı maddeleri son dönemde sessizce düşer. Ardından `python3 bekci/araclar/genel/denetim.py <grup>`.

### "Yatırımcı sunumu" (bekçi sunum.py, şirket sitesi) → sunum özeti
Dosya: bekci/gelen/<id>/sunum.pdf (id: sunum-<hisse>-<başlık>). Haber özeti şemasıyla, ek alanlar: "id": 9 + YYYYAA + sıra (ör. 92026110 = 2026/11'in 1. sunumu), "tur": "Yatırımcı sunumu", "sunum": "<PDF linki>" (şirket sayfasındaki sunum kutusu bu alanla eşler), "kaynak": "Kaynak: <Şirket> yatırımcı sunumu (<Ay YYYY>)" (kart dipnotu). Sources: PDF + şirketin sunum sayfası. Kartlar "facts" türünde, en çok 3: piyasa/operasyon verisi, şirket beklentileri, gerçekleşmeler; şirket sayfasında "Sunumdan öne çıkanlar" olarak da görünür. Sunumdaki grafik değerlerini sayfa görüntüsüyle (pdftoppm) doğrula; finansal tablolar hangi döneme aitse yaz (aylık sunumlarda çoğu zaman son çeyrek). Yorum yok; "önceki beklenti" gibi kıyaslar sunumda yazıyorsa verilir. Örnek: TUPRS 92026110. `site.py ekle-haber <HİSSE> dosya.json` (gizli eklenir).

#### Kalem açıklamaları (c.kalem)
Finansal rapor işlenirken şirketin `kalem` alanına son dönemin dipnot kırılımlarını yaz (matristeki (i) açıklamasının şirkete özel kısmı):
`"kalem": {"cost_of_sales": {"p": "2026-09", "title": "2026 ilk 9 ay, Mn TL", "u": "<KAP bildirim linki>", "pg": <PDF sayfa>, "rows": [["Satılan konut maliyeti", -1626.47], …], "text": "<dipnottaki olgusal açıklama, yorum yok>"}}`
Öncelik: revenue (hasılat dipnotu), cost_of_sales (satışların maliyeti dipnotu), operating_profit (esas faaliyet diğer gelir/gider dipnotu). Yeni dönem gelince aynı anahtarın içeriği değiştirilir. Örnek: AVPGY.

## 3. Bitiş
- `bekci/kuyruk.json`: işlenen kayıtların "durum"unu "hazir" yap (+ "hazir_zaman").
- `bekci/bildirimler.json` listesine ekle: "<HİSSE> · <başlık> özeti hazır (gizli, panelden düzeltip yayına al) · https://sonar.smartcuzdan.io/yonetim.html#haber-<hisse küçük>-<id>" (dönem özeti için `#ozet-<hisse küçük>`). Bekçi bir sonraki çalışmada Telegram'a yollar.
- `$HOME/fr-site`: index.html değişikliğini commit + `git pull --rebase` + push (yayın otomatik, 1-2 dk).
- `$HOME/fr-oto`: kuyruk.json ve bildirimler.json değişikliğini commit (mesaja `[skip render]` ekle) + `git pull --rebase` + push.
- `site.py ekle-haber/ekle-ozet` yeni içeriği **gizli** ekler (`"gizli": true`); Cagri panelde düzeltip "Yayına al" der. Var olan içeriği güncellerken mevcut durum korunur. Sen yayına alma.
- Taslaklar (X, Substack) açık sitede görünmez; Cagri onları https://sonar.smartcuzdan.io/yonetim.html panelinden görür.
- İçeriği iCloud'a da kaydet: `$HOME/mnt/sonar/icerik/<HİSSE>/<YYYY-Qn veya haber-<id>>/x-zinciri.txt` (dönem özetinde "Seri n / Ana tweet / Yanıt" başlıklarıyla).

## Kurallar (yazım dili)
- Ticker'da $ yok, hashtag yok. Yatırım tavsiyesi yok; son tweet/yazı sonunda "Yatırım tavsiyesi değildir."
- Görsel kartlarda yorum yok: yalnız başlık ve veri.
- Karşılaştırma tabanı açık yazılır. Kendi tahminini/yorumunu ekleme; şirketin açıkladığı hedef/gerekçe kaynağıyla verilir.
- Ton: sohbet havasında, birinci tekil, kısa cümleler; "Neyi takip edeceğim?"/"Son söz" gibi kişisel kısımlar kullanıcıya bırakılır.
- X: her tweet ≤280 karakter. Dönem özetinde ikili seri (yukarıda), sıra numarası yok. Haber özetinde şimdilik kısa zincir, (n/N) ile biter.
- Substack/X'te ASLA paylaşım yapma; yalnız taslak.
