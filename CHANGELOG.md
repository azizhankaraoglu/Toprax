# Toprax — Değişiklik Günlüğü

Bu dosya [Keep a Changelog](https://keepachangelog.com/tr/1.0.0/) ruhuyla tutulur.

## [1.2] — Karar Destek Katmanı + Gerçek Türkiye/köy verisi (2026-08-19)

Trial sürümü hedefiyle çok geniş bir tur: ölçüm katmanı (hava, güneş, toprak
biyolojisi, kök sayısı), karar katmanı (su bütçesi, polar/hasat zamanı, sezon
karar takvimi), gerçek il/ilçe/mahalle verisi ve 5 köyün gerçek parselleri.

### Veri temeli
- **İdari alanlar:** yeni `scripts/import_admin_areas.py` ile **81 il + 971 ilçe
  + 50.130 mahalle** içe aktarıldı (133 MB'lık mahalle dosyası akış halinde
  okunur — nginx/parser sınırlarına takılmaz). Hiyerarşi il_plaka→ilce_kodu→
  mahalle_kodu ile kurulur.
  - **İki gerçek veri kalitesi sorunu düzeltildi:** (1) 22 ilin `il_plaka`
    değeri 0'dı (adında Türkçe harf olanlar) → resmî plaka tablosundan
    yeniden türetildi; düzeltilmeden 81 il veritabanında 64 kayda düşüyordu.
    (2) Adlar cp1252 mojibake taşıyordu ("AÄŸri"); karışık metinlerde
    (`"Marmaraereğlisi, TekirdaÄŸ"`) yalnızca bozuk parçalar onarılıyor.
  - `AdminAreaDemographics` ile ~30 tipli kolon (nüfus, hane, yaş/eğitim,
    gelir, ÇKS çiftçi, işlenen arazi, traktör, baskın ürün, hayvan sayıları)
    + `field_definitions` seed'i → SmartDataGrid kolonu ve filtre olarak gelir.
- **5 köyün gerçek parselleri:** `scripts/seed_villages.py` — 5.053 parsel,
  241 çiftçi, 23.808 sözleşme/sezon/ekim, 19.029 verim+kantar, 71.594 sulama.
  Kaynak dosyalardaki kapalı `LineString`'ler poligona çevrildi; delikli
  parseller (halka içinde halka) ayrıştırıldı; alan gerçek geometriden
  hesaplandı.
- **Harita performansı:** `GET /admin-areas` artık `bbox` + seviye filtresi
  alıyor. Eskiden 51 bin kayıttan alfabetik ilk 2000'i döndürüyordu; kullanıcı
  haritada "3-5 poligon" görüyordu.

### Yeni ölçüm modülleri
- `weather.py` — Open-Meteo (güncel + 16 gün tahmin, ET0, radyasyon) +
  ERA5-Land (GEE, iklim normalleri) + büyüme derece-gün (GDD).
- `remote_sensing/solar.py` — Copernicus DEM GLO-30'dan eğim/bakı + saatlik
  gölge profili + ürün bazlı güneş yeterliliği.
- `soil_biology.py` — 18 organizmalık katalog (Heterodera schachtii dahil),
  9 mikrobiyal ölçüm, ağırlıklı toprak sağlığı skoru.
- `crop_stand.py` — ekim geometrisinden kök sayısı + uydu eğrisinden ürün
  tahmini. **Uydudan tek bitki sayılamaz** (bkz. `docs/vhr-fizibilite.md`).

### Yeni karar modülleri
- `water_budget.py` — FAO-56 toprak su dengesi; sulama ihtiyacı mm ve m³.
- `polar_engine.py` — polar tahmini (açıklanabilir katkı dökümü + güven
  aralığı), ekim penceresi, olgunlaşma endeksi, söküm penceresi.
- `season_planner.py` — fenolojik aşamaya (GDD) göre karar kartları; kabul
  edilen karar mevcut Saha Görevi/sulama kaydına yazılır.
- `confidence.py` — her tavsiyede "ölçüldü / tahmin / eksik" rozeti.
- `sustainability.py` — karbon ayak izi + iyileştirme önerileri + fayda raporu.
- `harvest_logistics.py` — fabrika kampanya çizelgesi + kantar randevusu.
- `agronomy.py` — toplu sorgu artık **yüzdelik uygunluk + gerekçe** döner,
  köy/mahalle ve idari sınır poligonuyla filtrelenir; sonuç üzerinde toplu
  mesaj, toplu ekim, **toplu sözleşme** (`POST /contracts/bulk-create`) ve
  CSV çıktı.

### Yangın (NASA FIRMS)
- Parsel bazlı **20 km yakınlık bariyeri** (mesafe + yön ile) ve kooperatif
  geneli **50 km özeti**; Dashboard'da tıklanabilir uyarı şeridi.

### Yerel LLM
- `toprax-ollama` GPU'lu ayağa kaldırıldı; `qwen3:8b` ve `qwen3:14b` kuruldu,
  `backend/ollama/Modelfile.toprax` ile `toprax-ai:8b`/`:14b` üretildi.
- **Ölçüm (RTX 5070, 8 GB VRAM):** 8B **31,2 token/sn** (32 sn/yanıt) —
  14B **2,2 token/sn** (212 sn/yanıt, VRAM taşıp CPU'ya iniyor). 14B, 60 sn'lik
  istek zaman aşımını aştığı için **8B aktif edildi**; 14B kurulu kalıyor.

### Düzeltilen gerçek hatalar
- **Service Worker HTML döndürüyordu:** başarısız bir JS/CSS parçası isteğinde
  `caches.match("/")` ile index.html dönüyordu → "unknown error when fetching
  the script" + yarım yüklenen uygulama ("l is not a function"). Artık HTML
  yedeği yalnızca navigasyon isteklerinde verilir; cache sürümü v2.
- **Parsel/çiftçi/verimlilik ekranları çöküyordu** (`undefined.toFixed`,
  `undefined.toLowerCase`) → yeni `lib/num.js` (fx/fmtNum/ratio) ile
  null-güvenli hale getirildi; eksik veri "—" gösterir, sayfa düşmez.
- **Parsel seçici boş görünüyordu:** `parcel-search` 2 karakter yazılmadan boş
  liste dönüyordu; artık odaklanınca ilk 20 parsel gelir.
- **`seed-defaults` kendini onarır:** ürün kataloğu migrasyondan bozuk gelmişse
  (label "pancar", tek match_term) kanonik değerlerle tamamlanır — bozukken
  münavebe/polar sinyalleri sessizce boş kalıyordu.

### Altyapı
- `cloudflared/config.yml` + kimlik dosyası eklendi: tünel bağlanıyor ama
  **hiçbir hostname bir servise eşlenmediği için tüm alan adları 503**
  dönüyordu. Artık toprax.com.tr / demo. / app. → `toprax-frontend:80`.

**Doğrulama:** 62/62 pytest yeşil; 157 frontend dosyası babel ile hatasız;
canlı Docker'da uçtan uca — Sezon Karar Takvimi gerçek parselde 3 karar üretti
(GDD 936, su açığı 220 mm/eşik 121 mm, veri güveni %35 dökümüyle), idari alan
seçici 81/971/50.130 sayılarıyla çalıştı, parsel popup'ı il/ilçe/mahalle/parsel
bağlantılarını verdi, tünelden üç alan adı da 200 döndü.

## [Yayınlanmadı] — "Toprax Uydu": çok-indeksli GEE analizi + UI'da EOSDA'nın yerini alması (2026-08-18)

> Build ALINMADI (kullanıcı kararı: başka iyileştirmeler de gelecek, derleme
> toplu yapılacak). Backend konteyneri bu değişikliklerle güncellendi ve canlı
> doğrulandı; frontend değişiklikleri sıradaki toplu derlemede devreye girer.

### 1. GEE/HLS sağlayıcısı 10 indekse çıktı (Çiftçi AI'dan port)
`backend/remote_sensing/providers/gee_hls/service.py` Faz 9C'de bilinçli
olarak sadece NDVI üretiyordu. Çiftçi AI projesinde (`backend/services/
satellite_service.py`) olgunlaşmış çok-indeksli boru hattı TOPRAX'a taşındı:
katalogdaki 10 indeksin tamamı (NDVI/NDRE/RECI/CCCI/NDWI/MSI/MSAVI/SAVI/EVI/
LAI), sensör ayrımı (S30/L30), gerçek renkli küçük resim, yeni
`get_latest_thumbnail_url()` ve `POST /v1/field-thumbnail` ucu. `indices`
parametresi opsiyonel — verilmezse tüm katalog (GEE hepsini TEK sahne
taramasında hesaplar, ek kota maliyeti YOK).

**Bu sırada bulunan GERÇEK hata (TOPRAX'ta):** S30 ve L30 koleksiyonları
harmonize edilmeden birleştirilip `normalizedDifference(["B5","B4"])`
kullanılıyordu. HLS'te bant adları tek hanelidir ve L30'da B5 = NIR iken
S30'da B5 = Red Edge 1'dir (NIR = B8A) — yani Sentinel-2 sahnelerinde
NDVI SİSTEMATİK OLARAK YANLIŞ hesaplanıyordu. Artık iki koleksiyon ortak
bant setine çevrildikten sonra birleşiyor.

Çiftçi AI'da canlı yaşanmış üç tuzak da yorumlarıyla korundu: (a) yansıma
değerleri GEE'de zaten 0-1 ölçeğinde — ikinci kez `0.0001` ile çarpmak
sabit içeren formülleri (SAVI/MSAVI/EVI/LAI) ve RGB render'ını sıfırlar;
(b) Landsat'ta Red Edge yok, sabit (projeksiyonsuz) bantlarla tamamlanıyor
ve küçük resim üretilirken RGB bantları ÖNCE seçilmezse görüntü tamamen
siyah çıkıyor; (c) Earth Engine tarih biçimi JODA kalıbıdır (`yyyy-MM-dd`,
`YYYY-MM-DD` değil). Landsat sahnelerinde Red Edge'e dayalı indeksler
(NDRE/RECI/CCCI) sıfır DEĞİL `null` döner.

### 2. Uzaktan algılamanın adı artık "Toprax Uydu", motoru GEE
Kullanıcı isteği: *"UI'da EOSDA olan yerlerin hepsine GEE entegrasyonunu
yerleştir ve adına Toprax Uydu de."*
- `providers/__init__.py`: `SATELLITE_BRAND = "Toprax Uydu"` (ekranlarda
  gösterilecek TEK kaynak), `DEFAULT_PROVIDER = "gee_hls"` (eskiden `eosda`),
  `PROVIDER_INTEGRATION_TYPES` eşlemesi.
- `services.py` durum ucu artık AKTİF sağlayıcının entegrasyon kaydına bakıyor
  (sabit `eosda` yerine) ve `brand` döndürüyor; manuel senkron varsayılanı
  NDVI'den TÜM kataloğa çıktı.
- `monitoring.py` sağlayıcı-bağımsız oldu; EOSDA trial kotası alanları
  yalnızca EOSDA aktifken doldurulur, aksi halde `null` (uydurma kota yerine
  dürüst "yok"). Ekran o KPI kartını gizler.
- `tasks.py`: GEE için kota muhasebesi tarama başına 1 birim (indeks başına
  3 değil) — aksi halde Monitoring kotayı 30 kat şişik gösteriyordu.
- Frontend: Ayarlar › Entegrasyonlar'daki EOSDA kartı yerine **Toprax Uydu**
  kartı (servis hesabı e-postası + JSON anahtar + proje + mock);
  `RemoteSensingPanel`/`RemoteSensing`/`BulkRemoteSensing`/`ParcelDetail`
  metinleri `brand` alanından besleniyor; toplu analiz ekranı sabit iki
  checkbox yerine katalogdan gelen 10 indeksi listeliyor; panelin çok-indeksli
  grafiği artık "S2 varsa S2" yerine EN ÇOK İNDEKS TAŞIYAN seriyi kullanıyor.

**EOSDA silinmedi:** sınıfı, entegrasyon tipi ve `provider_override:"eosda"`
yolu duruyor — sadece varsayılan olmaktan ve ekranlardan çıktı.

### Doğrulama
- `tests/test_gee_hls_indices.py` (12 yeni test) — indeks doğrulama, mock seri
  şekli, Landsat'ta `null` kuralı, provider sözleşmesi. Tüm paket: **62/62 yeşil**.
- Değişen `.py` dosyaları `py_compile`, değişen 5 `.jsx` babel ile hatasız.
- **Canlı GEE:** gerçek servis hesabı Integration Center'a kaydedildi; gerçek
  parselde (Hacıveli Tarlası 1) `POST /remote-sensing/manual-sync` → **119
  ölçüm × 10 indeks**, `api_calls: 1`, `provider: gee_hls`; parselin
  `remote_sensing.last_indices` alanı 10 indeksle doldu; L30 noktalarında
  Red Edge indeksleri yok (beklenen). `providers/status` → `brand: "Toprax
  Uydu"`, `is_real: true`.

### Bilinen dış engel (kod dışı)
Servis hesabında `earthengine.thumbnails.create` yetkisi YOK → sayısal analiz
çalışıyor ama **uydu görüntüsü üretilemiyor**. Google Cloud Console'da hizmet
hesabına *Earth Engine Resource Writer* rolü verilmeli. Kod bunu çökmeden
yönetir (görüntü alanı `null` döner, analiz tamamlanır).

## [1.1] — Ollama düzeltme + GEE canlı doğrulama + NASA FIRMS + TAKBİS/MERNİS UI + Harita + Integration Hub (2026-07-25, Build 25072026-0431)

Önceki build'in (25072026-0324) hemen ardından kullanıcı canlı testte 5 şey
buldu/istedi:

### 1. Ollama "Connection refused" — kök neden: yanlış host
Ayarlar'daki Ollama testi `http://localhost:11434`'e gidiyordu ama backend
DOCKER KONTEYNERİ İÇİNDE çalışıyor — kendi `localhost`'u kendisidir, Ollama
konteyneri DEĞİL. `ollama_base_url` config'i `http://ollama:11434` (docker-
compose servis adı) olarak güncellendi — health-check artık "Ollama
erişilebilir" dönüyor. *(Not: `docker-compose.ollama.yml`'in host portu bu
oturumun ERKEN bir aşamasında zaten 11434→11435 taşınmıştı — bu makinede
TOPRAX'a ait olmayan başka bir Ollama kurulumuyla çakışma yüzünden; bu,
konteyner-içi `ollama:11434` adresini ETKİLEMEZ, ayrı bir konudur.)*

### 2. Google Earth Engine — kullanıcı Google Cloud Console'u düzeltti, CANLI doğrulandı
Kullanıcı proje IAM/API-etkinleştirme sorununu Google Cloud Console'dan
giderdi. Yeniden test edildi: `ee.Initialize()` + `POST /api/v1/analyze-
field` GERÇEK NASA HLS verisiyle uçtan uca çalışıyor — 9 gerçek NDVI
gözlemi (Mayıs-Temmuz 2026, ~2-3 günlük aralıklarla, kullanıcının "yüksek
sıklık" isteğiyle birebir), gerçek imzalı `earthengine.googleapis.com`
thumbnail URL'i, gerçek alan hesabı. Entegrasyon artık tam olarak
kullanıcının istediği gibi çalışıyor.

### 3. NASA FIRMS yangın izleme — key kaydedildi + tam entegrasyon
Kullanıcının verdiği MAP_KEY Integration Center'a kaydedildi (otomatik
gerçek moda geçti). Yeni:
- `satellite_provider.py`: `GET/PUT /satellite/fire-scan-settings`
  (parametrik sorgulama frekansı, saat cinsinden, admin ayarlanabilir,
  varsayılan 6 — `karne_parameters` ile AYNI tek-doküman ayar deseni) +
  `POST /satellite/fire-scan/run` (tick-endpoint, cron YOK — proje
  konvansiyonu). Kota/süre koruması: NASA FIRMS senkron `requests` ile
  çağrıldığından tek tick'te EN FAZLA 25 parsel taranır (`process_pending_
  tasks(max_tasks=25)` İLE AYNI mantık) — kalan parseller sıradaki tick'te
  işlenir, `more_due` ile dürüstçe bildirilir (canlı test sırasında bulunan
  gerçek bir zaman-aşımı bug'ı — ilk denemede 954 parselin TAMAMI tek
  istekte taranmaya çalışılıp timeout oluyordu).
- Tespit varsa yeni `nasa_firms_alert_detected` Communication Policy
  event'i (event_bus.py + communication_policy.py'ye ikişer satır).
- `Parcel.fire_status` alanı + parsel kartında yangın göstergesi
  (ParcelDetail.jsx, `Flame` ikonlu rozet — kırmızı=alarm, nötr=temiz).
- Ayarlar'da "Otomatik Tarama" bölümü: frekans input + "Taramayı Şimdi
  Çalıştır" butonu.
- Gerçek NASA FIRMS'e karşı canlı doğrulandı (954 parsel, 25 tarandı,
  0 alarm — gerçek API yanıtı).

### 4. TAKBİS/MERNİS — arka uç zaten TAMAMDI (Faz 3), sadece EKSİK UI eklendi
Araştırma: `POST /gov/mernis/verify` + `POST /gov/takbis/query` zaten
tam çalışır durumdaydı; MERNİS zaten FarmerDetail.jsx'te vardı. Eksik olan
SADECE: TAKBİS artık Parseller sayfasının "Manuel"/"Çiz" parsel EKLEME
formlarında VE ParcelDetail.jsx'in "Hızlı İşlemler" bölümünde (önceden
SADECE "Düzenle" moduna girince görünüyordu); MERNİS artık Çiftçiler
sayfasının "Yeni Çiftçi" EKLEME modalında (TC No alanının hemen altında,
doğum yılı + doğrula — kayıt oluşunca AYNI uç farmer_id ile tekrar
çağrılıp kalıcı işaretleniyor).

### 5. Parsel haritası — Hybrid basemap + yakın zoom
`ParcelDetail.jsx`'in kendi Leaflet haritası CartoDB (sokak/etiket)
basemap'inden `HaritaPaneli.jsx`'in MEVCUT "hibrit" tanımıyla AYNI Esri
World Imagery + sınır/etiket overlay'ine geçirildi (yeni bir basemap
kataloğu icat edilmedi), zoom 14→17.

### 6. Integration Hub → God Mode
`PlatformAdmin.jsx`'in `SYSTEM_SCREENS` listesindeki jenerik "Ayarlar"
etiketi "Entegrasyonlar"a çevrildi — buton zaten `/ayarlar`'a (SADECE
`&lt;AyarlarEntegrasyon/&gt;` render eden, App.js:121) gidiyordu, yani
Integration Hub zaten God Mode'dan (Tenantlar → tenant satırı → sistem
ekranı butonları) erişilebiliyordu, sadece etiketi bunu belli etmiyordu.

### Doğrulama
50 pytest yeşil, `craco build` hatasız (ilgisiz dosyalarda önceden var
olan ESLint uyarıları dışında). Tüm yeni arayüz parçaları (yangın rozeti,
TAKBİS toggle, MERNİS doğrula, hibrit harita, otomatik tarama ayarları)
gerçek tarayıcıda canlı test edildi, konsol hatası yok.

## [1.1] — Çoklu-İndeks Uzaktan Algılama + Google Earth Engine/NASA HLS (2026-07-25, Build 25072026-0324)

Kullanıcının Sentinel Hub "Test Et" butonunun kimlik-doğrulama-only olduğunu
sorması ve "NDVI dışında kaç veri noktası alabiliriz" sorusu, bunun
üzerine **9 indeksin tamamının hem EOSDA hem Sentinel-2'de**, "optimum
tasarım" (2 sütun) + AI yorumu + bildirim entegrasyonuyla eklenmesi ve
ayrıca **Google Earth Engine + NASA HLS** yeni bir sağlayıcı olarak
kurulması istendi.

### 1. Sentinel-2 görüntüsü gösterilmiyordu — GERÇEK bug bulundu
`RemoteSensingPanel.jsx`'in istatistik yükleme kodu `provider !== "sentinel2"`
filtresiyle Sentinel-2 serilerini DIŞLIYORDU — salt Sentinel-2 taraması
yapılmış (hiç EOSDA çalışmamış) bir parselde panelin TAMAMI "henüz veri
yok" gösteriyordu, backend'de görüntü gerçekten kayıtlı olsa bile. Ayrıca
Sentinel-2'nin görüntü seçimi EOSDA'nın slider tarihine bağlıydı — iki
bağımsız uydu geçişi farklı tarihlerde olduğunda görüntü hiç görünmüyordu.
Her ikisi de düzeltildi (EOSDA/Sentinel-2 serileri artık ayrı tutulur,
panel ikisinden biri veri taşırsa render olur; S2 görüntüsü kendi tarih
çizgisine göre seçilip bulunamazsa en son S2 görüntüsüne düşer).

### 2. 9 indeks — tek kaynak katalog + Sentinel-2 (ücretsiz) + EOSDA
Yeni `backend/remote_sensing/indices.py` — NDVI/NDRE/RECI/CCCI/NDWI/MSI/
MSAVI/SAVI/EVI/LAI için TEK kaynak katalog (formül, kategori, TR etiket,
"tahmini" bayrağı). `sentinel2.py` artık TEK bir çok-bantlı evalscript ile
(8 ayrı istek değil) tüm indeksleri bir CDSE Statistics API çağrısında
hesaplıyor. `eosda.py`, EOSDA'nın istek başına 3-indeks sınırını 3'lü
gruplara bölüp sıralı isteklerle aşıyor (LAI EOSDA'ya hiç gönderilmez,
NDVI'den yerel türetilir) — kullanıcının açık isteği "hem EOSDA'da hem
Sentinel'de" karşılandı, maliyet uyarısıyla (otomatik taramada varsayılan
hâlâ sadece NDVI, 9-indeks sadece manuel akışta). `base.py`'nin
`parse_statistics`/`detect_anomaly` NDVI/NDRE hardcode'undan kurtarılıp
katalog üzerinden genellendi; `tasks.py` `Parcel.remote_sensing.last_ndvi`'yi
KORUYARAK yanına `last_indices` dict'i ekliyor.

### 3. AI yorumu + Bildirim
`services.py`'nin AI/kural metni artık NDVI'nin yanında su stresi (NDWI/
MSI) ve klorofil/azot (NDRE/RECI/CCCI) bulgularını veri-güdümlü olarak
ekliyor. Yeni `remote_sensing_water_stress_detected` Communication Policy
event'i (mevcut `remote_sensing_anomaly_detected`'ten AYRI — admin farklı
ekibe yönlendirebilsin diye), event_bus.py + communication_policy.py'ye
ikişer satırlık ekleme.

### 4. Frontend — 2 sütunlu "optimum tasarım"
Eski tam-genişlik tek NDVI grafiği, mevcut görüntü panelinin grid deseniyle
2 sütuna bölündü: "Bitki Örtüsü & Klorofil" (NDVI hep açık+kalın, diğer 7
indeks legend'e tıklayarak aç/kapa) + "Su Stresi & Nem" (NDWI+MSI, hep
açık). 9 ayrı tam-genişlik grafik YOK. Yeni `GET /remote-sensing/index-catalog`
ucu — frontend TR etiketleri hardcode ETMEDEN çeker.

### 5. Google Earth Engine + NASA HLS (yeni üçüncü sağlayıcı)
Kullanıcının verdiği tam spesifikasyona göre `POST /api/v1/analyze-field`
— HLSS30+HLSL30 birleştirme, %20 bulut filtresi, 30m tampon (hem istatistik
alanı hem kırpma), NDVI=(B5-B4)/(B5+B4), True Color thumbnail. Literal
istek/yanıt şeması korunur (TOPRAX'ın standart zarfı kullanılmaz).
Integration Center'a yeni `google_earth_engine` tipi (service account
email + JSON key + proje ID, mock-capable — kimlik yoksa/hatalıysa ASLA
crash olmaz, mock moda düşer). AYRICA `IRemoteSensingProvider` arayüzüne
sarılıp (`GEEHLSProvider`) mevcut Tarama Politikası/AI-yorumu/bildirim
boru hattına `provider_override="gee_hls"` ile bağlanabilir hale getirildi.
**Gerçek kimlik bilgisiyle canlı doğrulandı** — kod Google'ın gerçek
altyapısına başarıyla kimlik doğruluyor (`ee.Initialize` + `ee.Number(1).
getInfo()` başarılı); verilen proje ID'si ("seismic-operand-307212") Google
tarafında SİLİNMİŞ, alternatif olarak denenen proje ID'sinde ise servis
hesabının gerekli IAM izni yok — bu, TOPRAX kodundan değil kullanıcının
Google Cloud Console yapılandırmasından kaynaklanan, kod dışı bir engel
(net Google hata mesajlarıyla doğrulandı, sessizce yutulmadı).

### Doğrulama
50 pytest yeşil. `base.py`/`sentinel2.py`/`eosda.py` mock modda gerçek
9-indeks çıktısı üretildiği doğrulandı (birim test). `eosda.py`'nin 3'lü
gruplama+birleştirme mantığı mock HTTP yanıtlarıyla 3 senaryoda test
edildi (9 indeks, LAI+küçük istek, düz NDVI — hepsi doğru). GEE entegrasyonu
gerçek Google altyapısına karşı canlı test edildi (yukarıda). Frontend
`craco build` hatasız derlendi.

## [Yayınlanmamış] — İdari Alanlar: İKİNCİ kök neden (2026-07-25, Build 25072026-0100)

Madde 4'teki (aşağıda) nginx/`insert_many` düzeltmesi GEREKLİYDİ ama
YETERSİZDİ — kullanıcı gerçek bir "ilçe" GeoJSON'u (1100 kayıt, ~2.6 MB,
boyut sınırının çok altında) yüklediğinde toplu içe aktarma HÂLÂ "sunucuda
hata" ile çöküyordu.

- **Gerçek kök neden (canlı backend logundan bulundu):** kaynak
  shapefile'daki bazı ilçe poligonlarında (örn. "Hasankeyf") bitişik
  YİNELENEN köşe noktaları var — TUİK/il-ilçe sınır verilerinde sık
  rastlanan bir kalite sorunu. MongoDB'nin `admin_areas.geometry` üzerindeki
  2dsphere indeksi bunu geçersiz halka ("Loop is not valid ... Duplicate
  vertices") sayıp reddediyor; `insert_many` VARSAYILAN OLARAK sıralı
  (`ordered=True`) olduğundan tek bir geçersiz kayıt TÜM 2000'lik parçayı
  `BulkWriteError` ile çökertiyor, bu da yakalanmadan 500 Internal Server
  Error olarak kullanıcıya "sunucuda hata" şeklinde yansıyordu.
- **Düzeltme (`backend/admin_areas.py`):** (1) yeni `_dedupe_ring`/
  `_clean_geometry` — bitişik aynı köşe noktalarını otomatik temizler
  (halkanın şeklini bozmadan) ve gerçek Hasankeyf-tipi hatayı KÖKTEN
  çözer; (2) `insert_many(..., ordered=False)` + `BulkWriteError`
  yakalama — dedup'ın kurtaramadığı GERÇEKTEN geçersiz geometriler (örn.
  kendisiyle kesişen poligon) artık tüm isteği çökertmek yerine sadece o
  kayıt(lar) atlanıp isim listesiyle Türkçe uyarı olarak dönülür, geri
  kalan TÜM geçerli kayıtlar yine de kaydedilir.
- **Doğrulama:** gerçek MongoDB'ye (2dsphere indeksli test koleksiyonu)
  karşı üç senaryo test edildi — (a) Hasankeyf-tipi yinelenen köşe →
  dedup sonrası BAŞARIYLA eklendi, (b) kasıtlı kendisiyle kesişen poligon
  → çökme YOK, isimle raporlanıp atlandı, (c) normal geçerli poligon →
  sorunsuz eklendi. 50 pytest yeşil.
- **Not:** kullanıcının önceki başarısız deneme(ler)inden kalan kısmi
  kayıtlar (662 adet — 83 il / 578 ilçe / 1 mahalle) veritabanında duruyor;
  toplu içe aktarma idempotent OLMADIĞINDAN yeniden yüklemeden önce
  kullanıcıyla birlikte temizlenmesi gerekiyor (mükerrer kayıt oluşmaması
  için).

## [Yayınlanmamış] — Kullanıcı Geri Bildirimi Turu (2026-07-24/25, Build 25072026-0015)

Denetim raporu + 8 fazın tamamlanmasının ARDINDAN kullanıcının canlı ekranı
inceleyip bildirdiği 5 madde.

### 1. FilterPanel "Koşul" satırı + arama kutusu — KÖK NEDEN düzeltmesi
- **Kök neden bulundu:** `index.css`'teki `.card/.btn/.input/.badge*`
  sınıfları `@tailwind utilities`'in ALTINDA, katmansız düz CSS olarak
  tanımlıydı — Tailwind'de layer'sız kurallar utilities'ten SONRA gelir
  ve aynı özgüllükte (tek class) olduklarından kaynak SIRASI kazanır. Yani
  `.input{width:100%}` HER ZAMAN `w-32` gibi bir genişlik utility'sini
  eziyordu (`!` işaretsiz hiçbir boyut/padding utility'si `.input`/`.btn`/
  `.card` ile birleşince çalışmıyordu) — FilterPanel'in Koşul satırındaki
  "birinci kutu küçük, ikincisi büyük" karışıklığının VE arama kutusundaki
  ikon/metin çakışmasının (arka planda `pl-11`'in `.input`'un `padding:
  10px 14px`'i tarafından ezilmesi) TEK kök nedeniydi.
- **Düzeltme:** bu sınıflar `@layer components { ... }` içine alındı —
  Tailwind'in doğal katman sırası (base < components < utilities) geri
  geldi, TÜM `input`/`btn`/`card`/`badge` + boyut/padding utility
  kombinasyonu UYGULAMA GENELİNDE düzeldi (tek tek her kullanım yerini
  işaretlemek yerine kök neden giderildi — Farmers.jsx'te ölçüldü: field
  select 312px, operator 128px, value 312px; arama kutusu padding-left
  44px, artık ikonla çakışmıyor).
- `FilterPanel.jsx`: kapalıyken artık `AiAssistantBox` ile AYNI kompakt
  "btn btn-ghost" pill'i (önceden her zaman tam genişlikte bir "card"tı).
- `Farmers.jsx`: arama + bölge/karne + AI Asistanı + Gelişmiş Filtre TEK
  esnek (flex-wrap) satıra alındı.
- `Parcels.jsx`: AI Asistanı butonu artık "Liste & Filtre"/"Uzaktan
  Algılama" ile AYNI satırda (kendi ayrı satırından kaldırıldı).

### 2. Ekim Karar Motoru → Ekim Planlama'nın altına + toplu sorgu + parametrik ürün
- `backend/agronomy.py`: yeni `agronomy_crops` kataloğu (`GET/POST/PUT/
  DELETE /agronomy/crops`, soft-delete + YENİDEN ETKİNLEŞTİRME) — kural
  kütüphanesi (`agronomy_rules.crop`) ve AI şablonu (`agronomy_prompts`,
  `ekim_planlama_{crop}` anahtarıyla) artık ÜRÜNE göre ayrılıyor. Sinyal
  kataloğu (toprak/uydu/sulama/hastalık/geçmiş verim) ürünler arasında
  ORTAK kalır — sadece kuralların eşiği/skoru ürüne göre değişir. Münavebe
  sinyali (`ardisik_pancar_yili`) ÖNCEDEN hardcoded "ancar" alt-string
  eşleşmesiydi, artık seçili ürünün `match_terms` listesine göre çalışır.
  Çeşit lookup grubu da parametrik (`{crop}_cesidi`).
- Yeni `POST /ekim-planlama/bulk-analyze` — "bu sene X ekmeye en uygun
  parseller hangileri" toplu sorgusu: tekil analizin AYNI kural motorunu
  (AI çağrısı OLMADAN, hızlı) bir parsel havuzuna uygular, skora göre
  sıralar; il ile daraltılabilir, "truncated" bayrağıyla dürüst sınır
  bildirimi (crud_base.py'nin CSV export sınırlamasıyla aynı aile).
- **Veri migrasyonu:** mevcut (crop alanı olmayan) 18 varsayılan kural +
  1 özel kural + 1 AI şablonu, yeni crop-etiketli seed'in ürettiği
  kopyalarla ÇAKIŞMIŞTI (aynı isim, farklı crop durumu) — tek seferlik
  migrasyonla eski kayıtlar `crop:"pancar"` ile etiketlenip yinelenen
  taze kopyalar silindi; özel kural ("ZZ TEST...") KAYBOLMADI.
- Frontend: `EkimPlanlama.jsx`'e ürün seçici + "Yeni Ürün" formu + "Toplu
  Sorgu" sekmesi (3. sekme) + "Bilgi Kütüphanesi"nde ürün kataloğu listesi
  eklendi. `EkimKaydi.jsx`'e gömüldü — artık `/ekim` sayfasının "Karar
  Motoru" sekmesi (SahaOperasyonlari.jsx'in `?view=raporlar` deseniyle
  AYNI, IT-41 emsali), ayrı bir üst menü öğesi DEĞİL. Eski `/ekim-
  planlama` route'u `/ekim?view=karar-motoru`'ya yönlenir (eski linkler
  kırılmaz). Layout.jsx'te "Ekim Kaydı" → "Ekim Planlama" olarak yeniden
  adlandırıldı, ayrı "Ekim Karar Motoru" nav kaydı kaldırıldı.

### 3. Sentinel Hub — gerçek kimlik bilgisi
- Kullanıcının verdiği CDSE (Copernicus) `client_id`/`client_secret`
  Integration Center'a kaydedildi — `mock_mode` otomatik `false` oldu
  (mevcut "kimlik girilince otomatik canlı moda geç" davranışı, IT-01).
  Gerçek token alışverişi (`HTTP 200`) VE gerçek bir parselde uçtan uca
  görüntü/istatistik çekimi (62 gerçek NDVI noktası, 1 gerçek sahne — 31
  saniyelik gerçek ağ gecikmesiyle, demo modun anlık davranışından FARKLI)
  doğrulandı.

### 4. İdari Alanlar — ilçe/mahalle toplu yükleme hatası
- **İKİ gerçek kök neden bulundu:** (a) `Dockerfile.frontend`'in nginx
  yapılandırmasında `client_max_body_size` HİÇ ayarlanmamıştı — nginx'in
  VARSAYILANI (1 MB) hem dosya yüklemesini hem ayrıştırılmış geometrinin
  geri POST'unu (~1100 ilçe / ~60.000 mahalle için kolayca aşılan bir
  sınır) istek backend'e ULAŞMADAN sessizce 413 ile reddediyordu; (b)
  `admin_areas.py`'nin toplu içe aktarma uçu HER feature için AYRI bir
  `await db.admin_areas.insert_one(doc)` yapıyordu — 60.000 kayıt için
  bu, dakikalarca süren sıralı network round-trip'i demekti (gateway
  timeout riski).
- **Düzeltme:** nginx `client_max_body_size 60M` + `proxy_read_timeout
  300s` (Dockerfile.frontend); `geo_import.py`'nin `MAX_UPLOAD_BYTES`ı
  20→50 MB; `admin_areas.py`'nin döngüsü tek tek `insert_one` yerine
  2000'lik PARÇALAR halinde `insert_many` kullanacak şekilde yeniden
  yazıldı.
- **Doğrulama:** frontend'in GERÇEK nginx proxy yolu üzerinden (backend'e
  doğrudan değil, `frontend` servisi üzerinden) sentetik 60.000 feature'lı
  20 MB'lık bir GeoJSON yüklendi — ayrıştırma 2.2s, toplu içe aktarma
  2.4s'de tamamlandı (önceden dakikalarca sürüp timeout riski taşıyordu).
  Test verisi (75.000 kayıt) temizlendi.

### 5. Parseller — AI Asistanı konumu
- (Madde 1'in bir parçası olarak yukarıda ele alındı — "Liste & Filtre"/
  "Uzaktan Algılama" satırına taşındı.)

### Doğrulama
- `py_compile`+`pyflakes` (0 uyarı) + 50 pytest yeşil.
- Tüm değişiklikler gerçek Docker deployment'ta uçtan uca doğrulandı
  (yukarıdaki her madde kendi doğrulama notunu taşıyor).

## [Yayınlanmamış] — Faz 8: Rol Bazlı Offline (2026-07-24, Build 24072026-2359)

Denetim raporunun kullanıcı tarafından onaylanan 8 maddesinden #2: "hangi
fonksiyonlar hangi rolde offline çalışmalı" — proje zaten IT-35/36/37/38/39
ile önemli bir offline altyapısına (`lib/offlineQueue.js`, `MobilDashboard.
jsx`) sahipti; bu faz İKİ gerçek boşluğu kapattı: (1) kuyruktaki bir isteğin
sunucuya ULAŞIP işlendiği HALDE yanıtın kaybolması durumunda TEKRAR
gönderilip kaydın İKİ KEZ yazılması riski, (2) plan'ın "eksik formlar"
listesindeki destek talebi/kantar/toprak örneği'nin offline kuyruğa hiç
bağlı olmaması.

### Eklendi
- Yeni `backend/idempotency.py` — `X-Idempotency-Key` header'ına göre
  "bu istek daha önce işlendi mi" kontrolü; varsa kaydedilmiş yanıtı
  AYNEN döner (yeni yazma YAPMAZ). Geriye dönük uyumlu: header yoksa
  (eski istemciler) sessizce devre dışı. `idempotency_keys` koleksiyonu
  7 gün TTL index'li.
- İdempotency 7 uca eklendi: `POST /visits`, `PUT /tasks/{id}/transition`
  (replay artık "bu durum terminaldir" 400'üne çarpmaz), `POST /soil-
  samples/field`, `POST /kantar/records`, `POST /farmer/irrigation`,
  `POST /portal/support-requests`, `POST /forms/{id}/submit`.
- `lib/offlineQueue.js`: her kuyruğa eklenen isteğe `makeIdempotencyKey()`
  ile benzersiz bir anahtar atanır — İLK (çevrimiçi) denemeden İTİBAREN
  sabit tutulur (`MobilDashboard.jsx`'in TÜM yazma akışları güncellendi),
  `flush()` tekrar denemede AYNI anahtarı gönderir.
- `MobilDashboard.jsx`'e İKİ YENİ offline akış: "Yeni Destek Talebi"
  (çiftçi, `/portal/support-requests` — önceden sadece `QUICK_ACTION_
  LABELS`'ta rozet olarak vardı, GERÇEK bir form YOKTU) ve "Kantar
  Tartımı" (kantar_personeli, `/kantar/records`, `Extras.jsx`'teki
  masaüstü `KantarHizliGiris` ile AYNI alan şeması + `/search` ile canlı
  çiftçi arama) — kantar personelinin sahada field_task'ı olmadığından
  (sabit konumlu iş) generic görev akışına hiç girmiyordu, kendi bölümü
  yoktu. `saveSoilSample` de (önceden offline fallback'i HİÇ yoktu) artık
  kuyruğa düşüyor.
- `experience_profile.py`: `ROLE_OFFLINE_DEFAULTS` + idempotent `POST
  /experience-profiles/seed-role-defaults` — plan'ın rol×offline-yetenek
  matrisini 5 Experience Profile'a yazar (`offline_sync_rules` alanı
  IT-34'ten beri opak/boştu, bu fazın İLK gerçek içeriği).
- `docs/offline-test-kontrol-listesi.md` — rol×aksiyon manuel test matrisi.

### Bilinçli kapsam notları
- Okuma-tarafı önbellek (`lib/offlineStore.js`, "günün verisi") bu
  iterasyona ALINMADI — yazma tarafının (veri kaybı riski taşıyan)
  kuyruklanması önceliklendirildi; sayfa açılışında bir kez veri çekilmiş
  olması hâlâ gerekiyor.

### Doğrulama
- `py_compile`+`pyflakes` (0 uyarı) + 50 pytest yeşil (3 yeni idempotency
  testi: replay tek kayıt, header'sız istemci devre dışı, farklı uçlar
  çapraz cevap dönmez).
- **Gerçek Docker deployment'ta uçtan uca doğrulandı:** gerçek bir görev
  üzerinde `POST /visits`'e AYNI `X-Idempotency-Key` ile 2 istek atıldı —
  ikisi de AYNI `id`'yi döndü, DB'de TEK kayıt oluştu (2 değil); `PUT
  /tasks/{id}/transition`'a aynı geçiş idempotency anahtarıYLA 2 kez
  gönderildi — ikisi de 200 (anahtarSIZ 3. deneme doğru şekilde 400 ile
  reddedildi, mekanizmanın gerçekten iş yaptığının kanıtı). **Gerçek
  tarayıcıda:** kantar_personeli girişiyle "Kantar Tartımı" formu (çiftçi
  arama → seç → plaka/brüt/dara/polar → kaydet) uçtan uca çalıştı
  ("Tartım kaydedildi — net 9.30 t."); ciftci girişiyle "Yeni Destek
  Talebi" formu (üretim sezonu + destek tipi + miktar) uçtan uca çalıştı
  ("Destek talebi oluşturuldu."), `POST /portal/support-requests` 200
  döndü. Konsolda hiç hata yok. Test verisi temizlendi.

## [Yayınlanmamış] — Faz 7: Harita Stüdyosu (2026-07-24, Build 24072026-2345)

### Eklendi
- Yeni `backend/map_studio.py` — kişisel harita çalışma alanları. Veri
  modeli: `map_layers` (stil + popup config), `map_layer_features`
  (2dsphere index'li gerçek coğrafi kayıtlar), `map_projects` (katmanları
  birleştiren, kaydedilebilir/yayınlanabilir harita). `HaritaPaneli.jsx`'e
  BİLİNÇLİ OLARAK DOKUNULMADI — ayrı bir sayfa/ihtiyaç.
- Dosyadan içe aktarma: `geo_import.py`'nin (IT-13.5) parse fonksiyonları
  AYNEN kullanılıyor (GeoJSON/KML/KMZ/SHP/DXF) + bu modüle özel yeni bir
  CSV lat/lon ayrıştırıcı (`_parse_csv_latlon`). `POST /map-layers/{id}/
  import` sonucu DOĞRUDAN katmana yazar (10 MB/20k feature limitli).
- Elle çizim: yeni, kendi kendine yeten bir `L.Control.Draw` sarmalayıcısı
  (`StudioDrawControl`, marker+polyline+polygon) — `MapDrawTools.jsx`
  (parsel akışlarına özel, marker/polyline desteklemez) YENİDEN
  KULLANILMADI, paylaşılan bileşene dokunma riski alınmadı.
- Paylaşım İKİ BAĞIMSIZ boyut (forms_module.py'nin `share_mode` deseniyle
  AYNI aile): (1) tenant-içi görünürlük `share_scope`: private/org_unit
  (map_snapshots.py'nin `_user_unit_chain` mantığının küçük bir kopyası)/
  tenant/users (elle `shared_user_ids`); (2) `is_public` + `public_token`
  — herkese açık link, login GEREKMEZ. Bir proje aynı anda hem özel hem
  herkese açık linkli olabilir.
- İzinler `map_studio: view/create/share` + feature flag `map_studio`.
- Frontend `pages/HaritaStudyosu.jsx` (`/harita-studyosu`, SAHA & LOJİSTİK
  grubu) — katman/proje yöneticisi, stil/popup editörü, dosya yükleme,
  harita üzerinde çizim, yayınla dialogu. Public görüntüleyici
  `pages/PublicMapViewer.jsx` (`/harita/:token`).

### Bilinçli kapsam notları
- "Belirli Kullanıcılar" paylaşımı v1'de kullanıcı ID'si elle girilir
  (report_builder'ın personel alıcı seçimi v1'iyle AYNI sadeleştirme).
- Ölçüm aracı / adres arama / otomatik lejant kapsam dışı bırakıldı —
  temel katman/stil/popup/paylaşım akışı önceliklendirildi.

### Doğrulama
- `py_compile` + `pyflakes` (0 uyarı) + 47 pytest yeşil.
- **Gerçek Docker deployment'ta uçtan uca doğrulandı:** katman oluşturma/
  stil/popup config; CSV (lat/lon) + GeoJSON toplu içe aktarma (4 kayıt,
  feature_count doğru arttı); koordinat sütunu bulunamayan CSV 400 ile
  reddedildi; proje oluşturma + katman ekleme + kaydetme; `/map-projects/
  {id}/full` tek istekte proje+katman+feature bundle'ı döndü; herkese açık
  link paylaşımı sonrası `/public/maps/{token}` Authorization header
  OLMADAN 200 döndü; feature flag kapatılınca `/map-layers` 403 döndü.
  **Gerçek tarayıcıda** (leaflet-draw'a DOM üzerinden gerçek mouse event'i
  gönderilerek) haritaya tıklanıp bir marker çizildi — bu GERÇEKTEN
  `POST /map-layers/{id}/features`'ı tetikledi (network log'da 200
  doğrulandı) ve katmanın feature sayısı UI'da 0→1 güncellendi; "Yayınla"
  dialogundan üretilen link YENİ bir sekmede açılıp (login OLMADAN) gerçek
  Leaflet haritasının render olduğu, konsolda hiç hata olmadığı
  doğrulandı. Test verisi temizlendi.

### Bulunan ve düzeltilen bir bug (deploy öncesi, canlıya hiç gitmedi)
- `map_projects.public_token` için `sparse=True` unique index YANLIŞTI —
  her proje dokümanı `public_token: None`'ı AÇIKÇA taşıdığından (alan hep
  "var", sadece null), MongoDB'nin sparse index'i bunu yine de
  indeksleyip İKİNCİ private proje oluşturulduğunda unique çakışmasıyla
  patlardı. `partialFilterExpression: {"public_token": {"$type":
  "string"}}` ile düzeltildi — SADECE gerçek (yayınlanmış) token'lar
  indekslenir. `docker compose up` sırasında index oluşturma başarıyla
  tamamlandığı (hata yok) ve ikinci bir private proje oluşturmanın
  gerçekten sorunsuz çalıştığı (doğrulama script'inde 2 proje art arda
  oluşturuldu) doğrulandı.

## [Yayınlanmamış] — Faz 6: Elastik Rapor Modülü (2026-07-24, Build 24072026-2315)

### Eklendi
- Yeni `backend/report_builder.py` — şablon tasarımcı (modül + kolonlar +
  Query Engine filtre DSL'i + opsiyonel grupla/topla) + paylaşım (kanal veya
  link) + periyodik gönderim. Veri kaynağı DOĞRUDAN `query_engine.
  execute_query()` — izin/maskeleme (IT-07/IT-08) rapor tarafından bypass
  edilmez. Şablon sahiplik kalıbı `saved_queries.py` (IT-09) ile BİREBİR AYNI
  (özel/paylaşılan, sahibi düzenler/siler, admin+ moderasyon).
- `query_engine.py`'ye yeni `support_requests` modülü (örnek şablonlardan
  biri — "Destek Talepleri Özeti" — için).
- Render: pandas ile groupby/agg (sum/avg/count/min/max); CSV export
  `crud_base.py`'nin `io.StringIO`+`csv.DictWriter` kalıbıyla AYNI; PDF
  export reportlab ile — kendi paketiyle gelen `Vera.ttf`'i (Bitstream Vera
  Sans) kayıt ederek GERÇEK Türkçe karakter desteği sağlar (yeni bağımlılık
  YOK, mevcut PDF uçlarına dokunulmadı).
- Paylaşım `communications.send_via_channel()` üzerinden (Kara Liste/Tercih
  Merkezi/Feature Flag gate'i otomatik uygulanır). `report_runs` — paylaşım
  anında render edilmiş bir JSON SNAPSHOT (canlı sorgu değil); public link
  `GET /public/reports/{token}` login GEREKTİRMEZ (forms_module.py'nin
  `_unscoped` token-arama kalıbıyla AYNI).
- Zamanlama: `report_schedules` CRUD + `POST /reports/run-scheduled` tick
  (campaigns.py'nin run-scheduled deseniyle AYNI aile, ama TEKRARLI —
  `next_run_at` her çalıştırmada frekansa göre yeniden hesaplanır).
- İzinler `report_builder: read/create/share/schedule` (`permissions.py`) +
  feature flag `report_builder` (`platform_core.py`, God Mode raporlar
  grubunun altında).
- Frontend `pages/ReportBuilder.jsx` (`/rapor-olusturucu`, RAPORLAR grubu) —
  şablon listesi + tasarımcı (kolon seçici + gömülü `FilterPanel` + grupla/
  topla builder) + önizleme/CSV/PDF/paylaşım/zamanlama drawer'ları. Public
  görüntüleyici `pages/PublicReportViewer.jsx` (`/rapor/:token`).

### Bilinçli kapsam notları
- Alıcı seçimi sadeleştirildi: çiftçi alıcılar için `/search` (IT-10) ile
  canlı arama var, personel alıcılar için v1'de doğrudan kullanıcı ID'si
  girilir (tam bir personel seçici kapsam dışı — `settings:users_view` her
  role açık değil).
- Önizleme/export ilk 500 kayıtla sınırlı (`crud_base.py`'nin CSV export
  sınırlamasıyla AYNI aile) — `truncated` alanı bunu dürüstçe bildirir.

### Doğrulama
- `py_compile` + `pyflakes` (0 uyarı) + 47 pytest yeşil.
- **Gerçek Docker deployment'ta uçtan uca doğrulandı** (bkz. aşağıdaki
  "Dağıtım ortamı düzeltmesi" notu): örnek şablonlar seed edildi; gerçek
  201 çiftçi/1036 parsel verisiyle önizleme (düz liste VE risk_level'a göre
  gruplanmış toplam alan) doğru sonuç verdi; CSV/PDF export (geçerli
  `%PDF-1.3` header) çalıştı; link paylaşımı ile üretilen `/rapor/{token}`
  Authorization header OLMADAN 200 döndü; zamanlama oluşturuldu, tick
  henüz-zamanı-gelmemiş durumda `executed:[]` döndürdü. Tarayıcıda "Yeni
  Şablon" formuyla gerçek bir şablon uçtan uca oluşturuldu. Test verisi
  temizlendi, sadece 3 örnek şablon kaldı.

### Dağıtım ortamı düzeltmesi (bu oturumda keşfedildi)
- Çalışan `toprax-backend`/`toprax-frontend`/`toprax-mongo` Docker
  container'larının **`C:\App\TOPRAX_Final_12072026_00`** adlı, bu oturumun
  çalışma dizininden (`C:\Users\Azizhan\Desktop\toprax_guncel\
  TOPRAX_Final_12072026_00`) TAMAMEN AYRI bir git deposundan build edildiği
  bulundu — iki depo bağımsız olarak gelişmiş (C:\App'te kendi
  `elastic_reports.py`/`marnis_takbis.py` dosyaları + uncommitted
  değişiklikler vardı). Kullanıcı kararıyla bu çalışma dizini (Desktop
  kopyası) esas alındı: `docker compose build` ile backend/frontend imajları
  BU depodan yeniden derlendi, mongo container'a DOKUNULMADI (aynı
  `toprax_final_12072026_00_mongo_data` volume — proje klasör adı aynı
  olduğu için otomatik eşleşti — veri kaybı YOK, `.env` sırları da zaten
  birebir aynıydı). Ayrıca eksik olan `docker-compose.override.yml`
  (`tests/` bind mount'u) eklendi. **Bir sonraki oturum için önemli:**
  artık `docker compose` komutları BU dizinden (`C:\Users\Azizhan\Desktop\
  toprax_guncel\TOPRAX_Final_12072026_00`) çalıştırılmalı; `C:\App` kopyası
  kullanıcı tarafından ayrıca değerlendirilecek.



### Eklendi
- Yeni `backend/remote_sensing/providers/sentinel2.py` — `IRemoteSensingProvider`
  arayüzüne bağlı `Sentinel2Provider`. CDSE (Copernicus Data Space, ücretsiz)
  Process API + Statistics API SENKRONDUR — EOSDA'nın 3-adımlı async task
  modeline `request_image_download`/`request_statistics` içinde işi hemen
  bitirip sonucu örnek-seviyesi bir cache'e (`task_id → bytes/series`) gömüp
  `get_task_status`'un anında "completed" dönmesiyle uyarlandı — `tasks.py`/
  `scheduler.py` TEK SATIR değişmeden mevcut kuyruk mimarisine bağlandı.
  30 m tampon `pyproj` ile parselin UTM diliminde hesaplanır (shapely YOK);
  gerçek kırpma CDSE'nin kendi `geometry` parametresiyle sunucu tarafında
  yapılır. Görüntü NDVI renk haritalı (kırmızı→sarı→yeşil) PNG — EOSDA'nın
  true-color görüntüsünü tekrarlamak yerine tamamlayıcı bir ürün. Demo mod
  CRC32-tohumlu deterministik gradyan (Pillow — zaten proje bağımlılığı,
  yeni paket eklenmedi).
- **Kimlik bilgisi — yeni entegrasyon tipi YOK:** mevcut `sentinel_hub`
  entegrasyonundaki (Ayarlar > Entegrasyonlar) `client_id`/`client_secret`
  aynen kullanılır (`satellite_provider.SentinelHubProvider` ile aynı CDSE
  hesabı). `providers/__init__.py` factory'sine `"sentinel2"` eklendi.
- `remote_sensing/dto.py`: `ScanFrequency.BES_GUNDE_BIR` (5 gün) — Sentinel-2'nin
  gerçek yeniden-ziyaret süresine en yakın seçenek (mevcut 2/7/30 gün
  seçenekleri yetersizdi).
- `remote_sensing/tasks.py`: `create_task()` artık `provider_override`'ı
  GERÇEKTEN task dokümanına yazıyor — **bulunan bir hata**: bu alan
  `TaramaPolicy`'de vardı ama hiçbir zaman task'a aktarılmıyordu,
  `process_pending_tasks`'ın okuduğu `task.get("provider_override")` her
  zaman `None` dönüyordu (politika farklı bir sağlayıcı seçse bile etkisiz
  kalıyordu). `scheduler.py` artık `provider_override="sentinel2"` olan
  politikalar için hem `statistics` hem `download` task'ı otomatik kuyruğa
  alıyor (tek `statistics` yeterli değildi — görüntü ayrı task_type).
- Yeni `POST /remote-sensing/sentinel2/fetch {parcel_id}` — "Yeni Görüntü
  Getir" manuel tetikleme (istatistik + görüntü tek çağrıda).
- Frontend `RemoteSensingPanel.jsx` yeniden düzenlendi: sol slot EOSDA
  görüntüsü (değişmedi), **sağ slot artık Sentinel-2 görüntüsü** (aynı
  "seçili tarihe ≤ son bilinen görüntü" deseniyle, ayrı `provider` alanına
  göre filtrelenmiş); NDVI/NDRE/bulut/uydu bilgi satırı görüntülerin ALTINA
  taşındı; "Yeni Görüntü Getir (Sentinel-2)" butonu eklendi. **Bilinçli
  sadeleştirme:** birincil NDVI grafiği/slider'ı hâlâ SADECE EOSDA
  istatistiğine dayanır (iki farklı sağlayıcının NDVI serisini birleştirmek
  yerine mevcut çalışan grafik korundu) — Sentinel-2 görüntüsü aynı zaman
  çizgisine "son bilinen görüntü" deseniyle bağımsız eklenir.

### Doğrulama
- Backend: py_compile + pyflakes (yeni dosyalarda 0 uyarı) + 47 pytest yeşil.
- 30 m tampon fonksiyonu birim test edildi (bbox gerçekten genişliyor);
  demo PNG üretimi birim test edildi (gerçek/geçerli PNG magic byte'ları).
- **Gerçek mongo'ya bağlı canlı boot ile uçtan uca (demo mod, CDSE kimlik
  bilgisi bu ortamda yok):** `POST /remote-sensing/sentinel2/fetch` gerçek
  bir parselde çağrıldı — 2 görev kuyruğa alındı ve işlendi (istatistik: 74
  nokta, ort NDVI 0.515; görüntü: 1 sahne, 1 kaydedildi); `remote_sensing_
  images`'a `provider:"sentinel2"` ile GERÇEK bir kayıt yazıldığı, dosyanın
  diske kaydedildiği ve `GET /remote-sensing/images/file/{name}?token=`
  ucundan 200 + geçerli PNG (magic byte doğrulandı, 41889 bayt) olarak
  servis edildiği doğrulandı; `bes_gunde_bir` + `provider_override:
  "sentinel2"` ile bir Tarama Politikası oluşturulup doğru kaydedildiği
  doğrulandı. Test verisi (sentinel2 görüntü/istatistik/task/politika
  kayıtları) MongoDB'den temizlendi.

## [Yayınlanmamış] — Faz 4: Ollama Hibrit Yerel LLM (2026-07-24, Build 24072026-2000)

### Eklendi
- Yeni `backend/ai_router.py` — `ai_provider.py`'nin ABC+factory kalıbının
  bir üst katmanı: `OllamaProvider` (yerel LLM, API key gerektirmez,
  `/api/chat` üzerinden metin+görüntü) + `HybridAIRouter` (3 strateji:
  `local_only`, `external_only` [varsayılan, geriye dönük uyumlu],
  `hybrid_confidence`). Hibrit modda yanıttan `GUVEN: 0.x` satırı ayrıştırılır
  (`_extract_confidence`) — eşiğin altındaysa istek otomatik dış API'ye
  (Gemini/OpenAI/Anthropic) eskale edilir; kısa/refusal benzeri yanıtlar
  düşük varsayılan skorla (0.3) güvenli tarafta kalır. `routed_as` alanı
  ("local"/"external"/"escalated") her çağrıdan sonra metering için okunur.
- `integrations.py`: `ai_service` config'i genişletildi
  (`local_llm_enabled`/`ollama_base_url`/`ollama_text_model`/
  `ollama_vision_model`/`strategy`/`confidence_threshold`) — yeni bir
  `VALID_TYPES` girdisi DEĞİL, mevcut `ai_service` dokümanının parçası.
  `_has_credentials`, `/test`, `/health` yalnız yerel LLM açıkken de
  (dış sağlayıcı olmadan) gerçek bir Ollama bağlantı kontrolü yapar
  (`_probe_ollama` — `/api/tags` ile yüklü modelleri listeler).
- Çağrı noktaları hibrit router'a taşındı: `extras.py` (`ai_disease_detect`
  vision çağrısı, `_call_ai_text`/`ai_copilot` metin çağrısı — `ai_usage_logs`
  kaydına artık `routed` alanı işleniyor), `agronomy.py` (ekim planlama AI
  anlatımı). `ai_engine.py`'nin (FAZ 18) "cloud escalation"ı BİLİNÇLİ OLARAK
  dokunulmadı — o modül zaten tamamen simülasyon (`simulate_local_models()`),
  gerçek bir `generate_vision` çağrısı hiç yapmıyordu; onu gerçek hale
  getirmek bu iterasyonun kapsamı dışında bırakıldı.
- Frontend: Ayarlar > Entegrasyonlar > AI Servisi kartına "Yerel LLM
  (Ollama)" bölümü — etkinleştirme, URL/model alanları, strateji radyoları,
  hibrit modda güven eşiği slider'ı.
- Ops: `docker-compose.ollama.yml` (ana compose'a `-f` ile eklenir, sadece
  localhost'a açık port, mevcut `toprax-net` ağını yeniden kullanır),
  `scripts/ollama-modelleri-indir.ps1`/`.sh`, `docs/yerel-llm-kurulum.md`.

### Doğrulama
- Backend: py_compile + pyflakes (0 undefined name, 1 gerçek hata bulunup
  düzeltildi — `ai_copilot`'ta kalan `ai_cfg` referansı `ai_ready`'e
  çevrildi) + 47 pytest yeşil.
- `_extract_confidence()` birim test edildi: `GUVEN: 0.85` satırı doğru
  ayrıştırıldı ve metinden temizlendi, kısa yanıt (fallback 0.3), GUVEN
  satırsız uzun yanıt (fallback 0.5), `GUVEN: 1` (1.0) — hepsi doğru.
- **Gerçek Ollama konteyneriyle uçtan uca (qwen2.5:0.5b, gerçek indirme):**
  `docker-compose.ollama.yml` birleşik config'i doğrulandı (`docker compose
  config` — tek ağa çözüldü); `/integrations/ai_service/test` gerçek
  `/api/tags` çağrısıyla yüklü modeli gördü; `strategy=local_only` ile
  `POST /ai/copilot` **gerçek yerel modelden** geçerli bir JSON filtre
  üretti, Query Engine üzerinden 20 gerçek Konya parselini döndürdü,
  `ai_usage_logs`'a `routed:"local"` yazıldığı doğrulandı; imkânsız yüksek
  eşik (0.99) + dış API yokken hibrit mod düşük güvenli de olsa yerel
  sonucu döndürdü (çökme yok); erişilemez Ollama URL'i + dış API yokken
  temiz bir 500 döndü ve sunucu `healthy` kalmaya devam etti (çökme yok).
  Test verisi (ai_service config, ai_usage_logs kayıtları) temizlendi.

## [Yayınlanmamış] — Faz 3: MERNİS + TAKBİS Entegrasyonları (2026-07-24, Build 24072026-1800)

### Eklendi
- Yeni `backend/gov_providers.py` — `satellite_provider.py`/`channel_providers.py`
  ile aynı ABC+factory kalıbı: `IdentityProvider` (MERNİS/KPS) +
  `CadastreProvider` (TAKBİS). `validate_tc_checksum()` gerçek TC Kimlik No
  algoritmasıyla (resmi 11-hane formülü) doğrulama yapar. `DemoMernisProvider`/
  `DemoTakbisProvider` CRC32-tohumlu deterministik demo veri üretir
  (`DemoSatelliteProvider` ile aynı teknik); `RealMernisProvider` KPS
  `TCKimlikNoDogrula` SOAP 1.1 zarfını elle kurar (`zeep` bağımlılığı
  eklenmedi), `RealTakbisProvider` kurumsal REST/SOAP servisine bağlanır.
  Gerçek sağlayıcılar sadece kimlik bilgisi (`username`/`password`/
  `service_url`) girilip `mock_mode` kapatılınca devreye girer — mevcut
  eosda/sentinel_hub mock-capable deseniyle birebir.
- `integrations.py`: `SECRET_FIELDS`/`MOCK_CAPABLE_TYPES`'a `mernis`/`takbis`
  eklendi; `_has_credentials`, yıkıcı olmayan health probe'ları
  (`_probe_mernis`/`_probe_takbis`) ve `/integrations/{mernis,takbis}/test`
  uçları eklendi — mevcut Ayarlar > Entegrasyonlar akışıyla (maskeleme,
  demo→aktif otomatik geçiş, health-check) tam uyumlu.
- `platform_core.py FEATURE_FLAG_LABELS`'a `mernis`/`takbis` eklendi — God
  Mode'un modül aç/kapa listesi (`MODULE_TOGGLE_LABELS = FEATURE_FLAG_LABELS`
  referansı sayesinde) otomatik olarak bu iki modülü de kapsıyor.
- Yeni `backend/gov_integration_routes.py` — `POST /gov/mernis/verify`
  (`farmers:edit` + feature `mernis`; `farmer_id` verilirse başarılı
  doğrulamada `Farmer.mernis_verified`/`mernis_verified_at` yazar + audit),
  `POST /gov/takbis/query` (`parcels:edit` + feature `takbis`; sadece
  sorgu sonucunu döner, kaydetme çağıranın işi — `geo_import.py`'nin
  "ayrıştırır ama kaydetmez" felsefesiyle aynı ayrım).
- Frontend: `FarmerDetail.jsx`'e TC alanının yanına "MERNİS ile Doğrula"
  mini-formu (doğum yılı + doğrula) + başarılı doğrulamada yeşil "✓ MERNİS
  Doğrulandı" rozeti; `ParcelDetail.jsx`'in düzenleme moduna "TAKBİS Tapu
  Sorgu" kutusu (il/ilçe/ada/parsel → malik/nitelik/alan/tapu tarihi
  gösterimi + `il`/`ilce`/`ada_no`/`parsel_no_tapu`/`area_dekar` alanlarını
  otomatik doldurur, kullanıcı gözden geçirip Kaydet'e basar); `Extras.jsx`
  AyarlarEntegrasyon'a MERNİS + TAKBİS kimlik kartları (eosda kartıyla aynı
  düzen: kullanıcı adı/şifre/servis URL'i + demo mod checkbox'ı + Test Et).

### Doğrulama
- Backend: `py_compile` + pyflakes (0 undefined name) + 47 pytest yeşil.
- Gerçek TC checksum algoritması bilinen geçerli/geçersiz TC no'larla
  doğrulandı; demo sağlayıcıların deterministik olduğu (aynı girdi → aynı
  çıktı) doğrulandı.
- **Canlı mongo'ya bağlı boot ile uçtan uca:** `/gov/mernis/verify` gerçek
  bir çiftçiye `farmer_id` ile çağrıldı — `mernis_verified:true` +
  `mernis_verified_at` DB'ye yazıldığı `GET /farmers/{id}` ile ve audit
  log'daki old/new değerleriyle doğrulandı; geçersiz checksum'lı TC no
  `verified:false` ile reddedildi. `/gov/takbis/query` gerçek bir
  il/ilçe/ada/parsel ile çağrılıp tutarlı (deterministik) tapu verisi
  döndürdüğü doğrulandı. `PUT /integrations/mernis` ve `/takbis` ile
  kimlik bilgisi kaydedilip `mock_mode` açıkken DEMO, kapatılınca gerçek
  kimlik bilgisiyle otomatik AKTİF'e geçtiği (`active`/`is_demo` alanları)
  doğrulandı; `/health` ve `/test` uçları mock modda başarıyla çalıştı.
  Test verisi (mernis/takbis config'leri) doğrulama sonrası boşaltıldı.

## [Yayınlanmamış] — Denetim Düzeltmeleri Faz 2 (2026-07-24, Build 24072026-1600)

### Değişti (A6 — server.py modülerleştirme)
- `server.py` **3273 → 684 satır**. Endpoint blokları BİREBİR (davranış
  değişikliği YOK) 6 yeni modüle taşındı, `register_X_routes(...)` konvansiyonu
  ve **route kayıt sırası korunarak** (register çağrısı bloğun orijinal
  konumundan yapılır — Starlette route-order tuzağı):
  - `auth_routes.py` (login/refresh/me/public-contact)
  - `farmer_routes.py` (/farmer/* portalı + Çiftçi CRUD)
  - `parcel_routes.py` (Parsel CRUD + geo işlemler + import)
  - `dashboard_routes.py` (dashboard/bildirim/bölge/lojistik/karne)
  - `listing_routes.py` (toprak/sözleşme/ekim/sulama/operasyon/analitik listeleri)
  - `seed_routes.py` (/admin/seed + /, /health, /roles)
- Doğrulama: `py_compile` + `import server` (509 route) + pyflakes (0 undefined
  name) + 47 pytest yeşil + **gerçek mongo'ya bağlı canlı boot** ile taşınan her
  modülden temsili endpoint'lerin gerçekten çalıştığı (login → /farmers arama +
  detay + mask, /parcels detay, /dashboard/overview, /regions cache) 200/403 ile
  teyit edildi.

### Düzeltildi (A3 regresyonu — canlı boot'ta yakalandı)
- `server.py current_user`: kullanıcı DB araması `db.users` (tenant-scoped) →
  `raw_db.users`. Faz 0'daki fail-closed değişikliği, tenant_id=None taşıyan
  platform_admin hesabının kullanıcı kaydını bulamamasına ve HER authenticated
  isteğin 401'e düşmesine yol açıyordu. Kimlik JWT ile imzalı user_id'den
  çekildiği için çapraz-tenant sızıntı yok; asıl veri sorguları hâlâ scoped
  `db`'den geçer. **Bu regresyon yalnız gerçek boot + curl ile görülebilirdi;
  unit testler yakalamadı.**

## [Yayınlanmamış] — Denetim Düzeltmeleri Faz 1 (2026-07-24, Build 24072026-1400)

### Eklendi
- **A8 Sunucu tarafı şekille seçim**: yeni `POST /parcels/select-by-geometry`
  (`$geoIntersects`, `/parcels/{parcel_id}`'den önce tanımlı);
  `HaritaPaneli.jsx` "Şekille Seç" artık Turf.js tarayıcı taraması yerine bu
  ucu kullanır (1000+ parselde donma giderildi; sunucu hatasında eski
  yönteme sessiz geri dönüş).
- **A9 Topoloji doğrulaması**: yeni `backend/geo_validation.py` (saf Python
  self-intersection/halka kontrolü, shapely bağımlılığı YOK) — parsel
  create/update/split/import-geojson uçlarında 400; `Parcels.jsx` çiziminde
  `turf.kinks` ile erken uyarı.
- **A10 Görev erteleme**: `field_ops.py` yeni `ertelendi` durumu — saha
  aşamalarından geçilebilir, checklist zorunluluğundan muaf (yalnız `kapandi`
  ister), `ertelendi → planlandi` yeniden planlama; kanban'a "Ertelendi"
  sütunu; `SahaOperasyonlari.jsx` + `MobilDashboard.jsx` ALLOWED_NEXT senkron.
- **A12 Kantar hızlı giriş**: Kantar Kayıtları'na klavye-öncelikli "Hızlı
  Giriş" formu (Enter alan geçişi, Ctrl+Enter/F2 kayıt, kayıt sonrası odak
  başa) + `docs/kantar-rs232-kopru.md` (RS232 keyboard-wedge köprü kılavuzu,
  pyserial örneğiyle).
- **A14 Gerçek iletişim sağlayıcıları**: `channel_providers.py`'ye
  `RealSmsProvider` (Netgsm/Twilio/webhook — integrations._probe_sms_send
  yeniden kullanımı) + `SmtpEmailProvider`; yeni async
  `get_channel_provider_for(db, channel)` factory'si entegrasyon kaydı
  etkin+dolu ise gerçek, değilse simüle döner; `communications.
  send_via_channel` bu factory'ye geçti (KVKK gate değişmedi).
- **A15 Test seti**: `tests/test_audit_fixes_faz1.py` (12 test — A9 topoloji,
  A10 geçiş kuralları, A11 düzeltme işareti). Toplam 47 test yeşil.

### Düzeltildi
- **A7 (STAB-B1)**: `/admin-areas/bulk-import` Point/LineString kayıtları
  artık sessizce atlamaz — tip başına sayılıp Türkçe `warnings[]` döner,
  `AdminAreaManagement.jsx` gösterir.
- **A11 Ledger düzeltme takibi**: `POST /ledger/{id}/reverse` bağlı kaynak
  belgeyi (`support_request`/`entitlement`/`reconciliation`/`einvoice`)
  `correction_status: "Düzeltildi"` ile işaretler (belgenin kendi durum
  makinesine dokunmaz) + audit; `ProductionCycleDetail.jsx` rozet gösterir.
- **A13 KPI drill-down**: Dashboard'da hedefsiz 4 kart bağlandı
  (Hedef Hasat/Gerçekleşen → /verimlilik vb.); `UfydDashboard.jsx` KPI
  bileşenine `to` desteği eklendi (global liste sayfası olmayan finans
  kartları bilinçli olarak tıklamasız bırakıldı).

## [Yayınlanmamış] — Denetim Düzeltmeleri Faz 0 (2026-07-24, Build 24072026-1200)

### Güvenlik
- **A3 Tenant izolasyonu FAIL-CLOSED** (`tenant_context.py`): `current_tenant_id`
  None iken artık filtre atlanmıyor — `{"tenant_id": "__UNAUTHORIZED__"}`
  sentinel'i enjekte edilir, bağlamsız sorgu HER ZAMAN boş döner. Meşru
  bağlamsız yollar `raw_db`'ye taşındı: login e-posta araması + SHA256→bcrypt
  rehash (`server.py`), `/auth/refresh` kullanıcı sorgusu (+ token-tenant
  eşleşme ve aktiflik kontrolü eklendi), `storage.py` `?token=` dosya indirme
  yetkilendirmesi, `remote_sensing/services.py` görüntü sunumu. Aggregate
  pipeline'ları da fail-closed. Yeni `tests/test_tenant_fail_closed.py` (6 test).
- **API key isteklerinde tenant bağlamı** (`server.py current_user`):
  middleware yalnız JWT çözdüğü için `toprax_key_` isteklerinde bağlam boş
  kalıyordu — makine anahtarı TÜM tenant'ların verisini okuyabiliyordu.
  Bağlam artık anahtarın tenant'ıyla kurulur.

### Düzeltildi
- **A1 Impersonation redirect loop**: `god_mode.py /god-mode/tenants/{id}/enter`
  artık gerçek bir `refresh_token` da döner; `PlatformAdmin.jsx` boş string
  yerine bunu saklar; `api.js` refresh yanıtında dönebilecek yeni refresh
  token'ı persist eder. "Kooperatif olarak gir" sonrası sayfa geçişlerinde
  login'e fırlatılma sorunu giderildi.
- **A2 Saved Queries `title`/`name`**: kod düzeyinde doğrulandı —
  `FilterPanel.jsx` zaten `name` gönderiyor, `saved_queries.py` `name`
  bekliyor; denetim raporundaki uyumsuzluk daha önce kapatılmış. Değişiklik yok.
- **H/UI Bildirim çekmecesi**: başlıklar `truncate` yerine `line-clamp-2`
  ile 2 satıra sarılır (`WorkspaceDrawer.jsx`).
- **H/UI Ekim Planlama Karar Motoru**: sayfanın kullandığı `.page/.tabs/.tab/
  .table/.muted/.page-header` sınıfları CSS'te hiç tanımlı değildi — tablolar
  stilsiz render olup metinler üst üste biniyordu; `index.css`'e mevcut
  tasarım diliyle tanımlandı.

### Eklendi
- **A4 Bileşik indeksler** (`server.py` startup): 14 koleksiyona
  `(tenant_id, created_at)`, durum makineli 6 koleksiyona `(tenant_id, status)`,
  çiftçi-çocuk 7 koleksiyona `(tenant_id, farmer_id)` isimli idempotent indeks.
- **A5 Yetim kayıt koruması** (`server.py delete_farmer`): aktif üretim
  sezonu varken çiftçi silinemez (409, parsel/sözleşme guard'ına ek);
  silinen çiftçinin bağlı kayıtları `farmer_inactive: true` ile işaretlenir
  (kendi durum alanlarına dokunulmaz) + koleksiyon başına audit.

## [Yayınlanmamış] — FAZ 18: Agricultural Intelligence Engine (IT-47..53)

### Eklendi
- **IT-47** AI Knowledge Library çekirdeği — `ai_datasets` / `ai_knowledge_records` /
  `ai_taxonomy` koleksiyonları, versiyonlama (`previous_version_id`, ledger silinmezlik
  deseni), toplu import, annotation, onay iş akışı, 20+ örnek taksonomi seed'i
  (`backend/ai_engine.py`).
- **IT-48** Yerel AI pipeline + Confidence Engine — kural motoru → simüle yerel model →
  çoklu-model konsensüsü (çelişki güveni düşürür) → karar; SAF FONKSİYONLAR (birim-test
  edilebilir); atomik `find_one_and_update` job claim + in-process async worker.
- **IT-49** Bulut escalation + tenant AI kotası — `ai_tenant_quota` atomik `$inc`,
  zorunlu redaksiyon filtresi (çiftçi kimlik alanları buluta gitmez), kota dolunca sessiz
  hata YOK (`low_confidence_no_cloud_budget`).
- **IT-50** Active Learning — `ai_active_learning_queue` + `case_management.py` köprüsü
  (`category="AI Doğrulama"` Case), uzman kararı knowledge_record'a `source="hibrit"` yeni
  versiyon yazar (golden dataset).
- **IT-51** MLOps model registry — `ai_models` durum makinesi, golden dataset regresyon
  kapısı (yeni F1 < production F1 → deploy reddi), `previous_model_id` rollback, Health
  Center'a "AI Model Sağlığı" satırı (`platform_core.py`).
- **IT-53** Menü/RBAC konsolidasyonu — `permissions.py` PERMISSION_CATALOG'a `ai_engine`
  modülü (ai_knowledge/ai_model/ai_prediction:*), Query Engine'e `ai_knowledge_records`,
  Ayarlar altında tek "AI Bilgi Kütüphanesi" ekranı (4 sekme, `AiKnowledgeLibrary.jsx`).
- Not: GodMode (FAZ 16) ve açılış popup/duyuru bildirimleri bu çalışmada KORUNDU, dokunulmadı.

## [2.1.0] — On-Premise Ürünleştirme (ROADMAP-URUNLESTIRME.md)

### Eklendi
- **PR-01** Multi-stage Docker paketleme, healthcheck'ler, `/api/health`.
- **PR-02** Web tabanlı kurulum sihirbazı (`/kurulum`) — tenant + süper admin + SMTP + lisans, self-lock.
- **PR-03** Kurulum ön-koşul kontrolcüsü (`scripts/check-requirements.sh`).
- **PR-04** Versiyonlu migration runner + otomatik rollback (`migrations_engine.py`, `upgrade.sh`).
- **PR-05** Offline/air-gapped kurulum paketi (`build-offline-bundle.sh`, `install-from-bundle.sh`).
- **PR-06** TLS/sertifika otomasyonu (Let's Encrypt + certbot otomatik yenileme).
- **PR-07** Kurulum sonrası smoke test (`scripts/smoke-test.sh`).
- **PR-08** Kapsamlı IT admin kurulum kılavuzu (`docs/KURULUM-KILAVUZU.md`).
- **PR-22** Versiyonlu, standart zarflı API yüzeyi (`/api/v1/*`), mevcut `/api/*` değişmeden korundu.
- **PR-23** Generic CRUD + Soft-Delete base class (`crud_base.py`) — yeni modüller için.
- **PR-24** Tenant'a bağlı, scope'lu, rate limitli API Key mekanizması (`api_keys.py`).
- **PR-25** OpenAPI'den otomatik Postman/Insomnia collection üretimi.
- **PR-26** Geliştirici Portalı (Swagger, Postman indirme, API Key yönetimi, changelog).

### Önceki oturum (bu sürümden hemen önce)
- Organizasyon Hiyerarşisi + Onay Zinciri Motoru + Case Management (IT-42/43/46).
- Uydu görüntü sağlayıcı mimarisi (Sentinel Hub, NASA FIRMS, UP42, Demo fallback).

## [2.0.0]

- Rebranding, bcrypt, refresh token, rol hiyerarşisi, merkezi audit log, Entegrasyonlar modülü.
