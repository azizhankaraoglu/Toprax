# OTURUM DEVAM NOTU — 2026-08-19

---
# 📋 18 MADDELİK DURUM İNCELEMESİ (2026-08-19, tur sonu)

Kullanıcının sunduğu 18 maddelik liste **canlı sistemde tek tek doğrulandı**.
Liste, imajlar yeniden derlenmeden ÖNCEKİ bir ana ait olduğu için A ve B
gruplarının bir kısmı artık geçerli değil. Aşağıdaki tablo doğrulama
komutlarıyla birlikte gerçek durumu gösteriyor.

## ✅ Bu oturumda YAPILDI (liste artık geçersiz)

| # | Maddedeki iddia | GERÇEK DURUM | Kanıt |
|---|---|---|---|
| A1 | "Backend imajı eski, dosyalar sadece `docker cp` ile kopyalandı" | **YANLIŞ — imaj kaynaktan derlendi.** `docker run --rm toprax-backend:latest` ile İMAJIN İÇİ kontrol edildi: `crop_classification.py` (38.077 B), `ai_governance.py`, `sustainability.py` imajda MEVCUT | `docker run --rm --entrypoint sh toprax-backend:latest -c "ls -la /app/crop_classification.py"` |
| A2 | "Frontend canlı build v1.2 (`main.fc3fe5c9.js`), 3 ekran tarayıcıda yok" | **YANLIŞ — canlı build `main.8d76bf9e.js` = v1.3.** Bundle içinde `19082026-1700` damgası VE `urun-tanima` + `karbon-ayak-izi` route'ları var | `docker exec toprax-frontend grep -o '19082026-[0-9]*' .../main.8d76bf9e.js` |
| A3 | "`COMPOSE_BAKE=false` gerekli, `--remove-orphans` kullanılmamalı" | **DOĞRU ve uygulandı.** Tüm derlemeler `$env:COMPOSE_BAKE="false"` ile yapıldı; `--remove-orphans` hiç kullanılmadı, `toprax-ollama` ayakta | — |
| B4 | "`crop_classification.py`'nin son iki düzeltmesi deploy edilmedi" | **YANLIŞ — imajda var.** Kalibrasyonun *ayrı örnek sayısına* bakması (`ornek_sayisi`, 7 geçiş) ve boş taramada `uyari` alanı (4 geçiş) imajda mevcut | `docker run --rm ... grep -c 'ornek_sayisi' /app/crop_classification.py` → 7 |
| 18 | "`docker-compose.yml`'deki obsolete `version:` temizlenmedi" | **BU TURDA YAPILDI.** `version: "3.9"` HEM `docker-compose.yml` HEM `docker-compose.ollama.yml`'den kaldırıldı; `docker compose config --quiet` artık uyarısız geçiyor | — |
| 13 (kısmen) | "İl/ilçe lookup'ı hâlâ sadece Konya + Ankara" | **VERİ TARAFI ÇÖZÜLDÜ: lookup'ta 81 il / 973 ilçe var.** Bu turda `POST /field-definitions/sync-il-ilce-from-admin-areas` eklendi ve çalıştırıldı — 81 ili koda yazmak yerine `admin_areas`'tan türetiyor. **Kalan:** `TR_IL_ILCE` kod sabiti hâlâ 2 il (yeni/boş kurulumlar için başlangıç verisi; artık kritik değil çünkü sync ucu var) | `db.lookup_values.countDocuments({group_id: il.id})` → 81 |

## ⚠️ DOĞRU — açık kalan, veri/ortam kaynaklı (kod kusuru DEĞİL)

| # | Konu | Neden açık |
|---|---|---|
| B5 | Ürün tanıma gerçek veriyle zayıf | **5.053 parselin ~12'sinde uydu serisi var.** `from-plantings` 300 beyandan 3 örnek üretebildi, kalibrasyon %33,3'te kaldı. Motor doğru (sentetik veriyle 7/7); eksik olan veri. **Çözüm sırası:** Uzaktan Algılama → toplu tarama → `from-plantings` → `calibrate` |
| B6 | Alan taraması hiç ürün bulmuyor | Sentinel-2/GEE **mock modda**; kayıtsız alanlara zaman serisi üretmiyor. Integration Center'dan gerçek mod kimlik bilgisi girilmeli. Bu turda eklendi: boş sonuçta artık SEBEBİ `uyari` alanında dönüyor (sessiz boş harita yok) |
| B7 | Copernicus CLMS iskelet | **Bilinçli.** Bağlanmadı, boş döner, uydurma sonuç ÜRETMEZ. Zincir Sentinel-2'ye düşer. Not: `sentinel2.py` zaten Copernicus CDSE'dir — "Copernicus" ve "Sentinel-2" ayrı kaynak değil |
| 15 | `l is not a function` | Hiçbir rotada tekrar üretilemedi (bu turda 20 + önceki turda 33 rota tarandı). Tekrarlarsa **hangi sayfa + hangi tıklama + hangi rol** gerekiyor |

## ❌ HİÇ YAPILMADI — sıradaki iş

| # | Konu | Durum |
|---|---|---|
| 8 | **Mobil derinleştirme** — uzmanla iletişim, kendi verisini girme, fabrika randevusu, kooperatifle çift yönlü yazışma | Kod yazılmadı |
| 9 | **VRA (değişken oranlı uygulama)** — zon haritası → shapefile/ISOXML dışa aktarma | Kod yazılmadı |
| 10 | **Demo senaryo oynatıcı** — `scripts/demo_scenario.py` + "Senaryoyu Oynat" ekranı | Kod yazılmadı |
| 11 | **Bildirim merkezi** — sunucu tarafı sayfalama/filtre VAR (`dashboard_routes.py`, `{items,total,unread}` zarfı); **eksik:** gün bazlı gruplama, arşivleme, kişiye özel hedefleme (bildirimler hâlâ tenant geneli) | Yarım |
| 12 | **Harita Stüdyosu elden geçirme** | Kullanıcı bilinçli erteledi ("en son onu beraber elden geçirelim") |
| 14 | **Çiftçi self-servis 3 akışı** — sözleşme onaylama, ekim planlama, randevu alma | Ertelendi; üçü de veri modeli kararı gerektiriyor (Karar Protokolü) |
| 16 | **Devir dokümanı** | Yazılmadı. **Not:** BU dosya fiilen devir dokümanı işlevi görüyor (ortam, kök nedenler, kalan işler); ayrı/resmî bir belge isteniyorsa kapsamı netleştirilmeli |
| 17 | **`CLAUDE.md` "Mevcut Durum" güncellemesi** | Bu turun işleriyle güncellendi — bkz. CLAUDE.md sonundaki 2026-08-19 girdisi |

---
## ✅ 2. TUR TAMAMLANDI (v1.3 · Build 19082026-1700)

Docker Desktop geri geldi, **imajlar kaynaktan yeniden derlendi**
(`main.8d76bf9e.js`), 20 rota tarayıcıda çökme taramasından geçti, geçici
test kullanıcısı silindi. Aşağıdaki "yarıda kesildi" bölümü ARŞİVDİR —
tüm maddeleri tamamlandı.

**Yeni eklenenler:** `crop_classification.py` + `CropDetection.jsx`
(`/urun-tanima`), `Sustainability.jsx` (`/karbon-ayak-izi`),
`sustainability.py`'ye `/summary` ucu, `catalog_registry`'ye
`crop_signatures` kataloğu.

**Canlı doğrulanan sonuçlar:**
- Dashboard: sözleşme 23.808→**4.779**, gerçekleşme %817,5→**%0** (2026
  henüz hasat edilmedi), NDVI 0→**0,505**, alan açığı 55.308→**0**,
  bölge tablosu 8 boş satır→**5 dolu bölge**
- Guardrail IBAN sorgusunu **422** ile engelledi, normal copilot sorgusu
  hâlâ geçerli JSON döndürdü (structured mod çalışıyor)
- Hasat çizelgesi: kapasite aşımı **0 gün**, 1 gün→**6 güne** yayıldı
- Ürün tanıma: 25 parsel analiz edildi, 3 ürün, **2 beyan uyuşmazlığı**,
  verisi olmayan parseller "uydu verisi yetersiz" dedi (uydurmadı)
- Karbon: 200 parselde **897,92 ton CO₂e**, en büyük kalem azotlu gübre
  (%33,7), 4 iyileştirme fırsatı kazançla sıralı

---
## 📦 ARŞİV — 2. tur yarıda kesildiğinde alınan not

**Durum:** Kod değişikliklerinin TAMAMI diskte ve doğru. Ama **backend imajı
ESKİ** — bu turda dosyalar `docker cp` ile container'a kopyalanıp
`docker restart` ile çalıştırılmıştı; imaja YAZILMADI.

### Yeni oturumda İLK yapılacak (sırayla)

```bash
# 1) Docker Desktop'ı ELLE başlat, hazır olmasını bekle.
#    ASLA Docker Desktop kapalıyken `docker compose up` ÇALIŞTIRMA —
#    WSL'in kendi daemon'una düşer, BOŞ volume ile mongo açar ve
#    "tüm veri silinmiş" gibi görünür (bkz. CLAUDE.md ORTAM TUZAĞI).
docker volume ls        # ~28 volume görmelisin; 2 tane görüyorsan YANLIŞ daemon

# 2) İmajları kaynaktan yeniden derle (kopyalanan dosyalar imajda YOK)
cd C:\Users\Azizhan\Desktop\toprax_guncel\TOPRAX_Final_12072026_00
$env:COMPOSE_BAKE="false"
docker compose build backend frontend
docker compose up -d backend frontend
```

`COMPOSE_BAKE="false"` gerekli — bake ile derleme bu makinede
`exit status 0xc0000005` ile çöküyor.

### Bu turda TAMAMLANANLAR (hepsi diskte, test edildi)

| Madde | Konu | Dosyalar | Doğrulama |
|---|---|---|---|
| B1 | AI çağıranları `governed_generate`'e bağlandı | `ai_governance.py`, `extras.py`, `agronomy.py`, `remote_sensing/services.py` | ✅ guardrail IBAN'ı engelledi (422), normal sorgu geçerli JSON döndü |
| A1 | Dashboard sezon filtresi | `dashboard_routes.py` | ✅ sözleşme 23.808→4.779, gerçekleşme %817,5→%0 |
| A2 | Bölge tablosu | `dashboard_routes.py` | ✅ 8 boş satır→5 dolu bölge |
| A3 | Uydu KPI'ları | `dashboard_routes.py` | ✅ NDVI 0→0,505 (12 parselde ölçüm) |
| A4 | Alan muhasebesi | `dashboard_routes.py` | ✅ 55.308 dekar açık→0 |
| B2 | Hasat çizelgesi yığılması | `harvest_logistics.py` | ✅ kapasite aşımı 0 gün, 1 gün→6 güne yayıldı |
| B4 | ilçe lookup temizliği | (Mongo) | ✅ 5 test kaydı silindi, 978→973 |
| B4 | pypdf + python-docx | `requirements.txt` | ✅ container'a kuruldu, import doğrulandı |
| B3 | Karbon ekranı | yeni `pages/Sustainability.jsx`, `sustainability.py` `/summary` ucu | ✅ backend test edildi (286 ton CO₂e); **ekran DERLENMEDİ** |
| C1 | Sınıflandırıcı çekirdeği | yeni `crop_classification.py` | ✅ 7/7 doğru, gürültülü veride %96 |
| C2/C3 | Sağlayıcı zinciri + uçlar | `crop_classification.py`, `server.py`, `catalog_registry.py` | ✅ uçlar 200 döndü |
| C4 | Eğitim + kalibrasyon + doğruluk | `crop_classification.py` | ✅ çalışıyor (bulgular aşağıda) |

### KALAN İŞ (bu turda bitmedi)

1. **`crop_classification.py`'nin SON İKİ düzeltmesi deploy edilmedi**
   (docker cp tam o anda koptu — kod diskte doğru):
   - kalibrasyon eşiği artık *ayrı örnek sayısına* bakıyor (ay-gözlemine değil)
   - alan taraması boş dönerse SEBEBİNİ `uyari` alanında söylüyor
2. **`pages/CropDetection.jsx` HİÇ YAZILMADI** — ürün tanıma ekranı (3 sekme:
   "Bölgede ne ekili?" / "Alanı tara" / "Eğitim & Doğruluk"). Backend hazır,
   uçlar test edildi; sadece UI eksik. Plan dosyasında tasarım detayı var:
   `C:\Users\Azizhan\.claude\plans\crispy-wibbling-bengio.md`
3. **`Sustainability.jsx` derlenmedi/deploy edilmedi** (route + menü girdisi
   `App.js` ve `Layout.jsx`'e eklendi, sözdizimi kontrolünden geçti).
4. **`version.js` → v1.3** güncellenmedi.
5. Tam rota çökme taraması yapılmadı (son build `main.fc3fe5c9.js` = v1.2).

### C modülünün DÜRÜST DURUMU (kullanıcıya bildirilmeli)

Sınıflandırıcı **sentetik veriyle mükemmel** (7/7, gürültülü seride %96), ama
**gerçek veriyle zayıf** — sebebi motor değil, veri:

- **5.053 parselin yalnızca ~12'sinde uydu zaman serisi var.**
  `from-plantings` ile 300 beyan tarandı, 297'si "seri yok" diye atlandı,
  yalnızca 3 eğitim örneği üretilebildi.
- Gerçek parsellerde güven skorları düşük (0,17–0,44) — demo NDVI verisi
  gerçek fenolojiyi taşımıyor.
- **Kalibrasyon doğruluğu değiştirmedi (%33,3 → %33,3)** — 3 örnekle ve hepsi
  aynı üründen olunca ayırt edicilik artmıyor. Ölçüm bunu dürüstçe gösterdi;
  bu yüzden eşik "3 ayrı örnek" olarak sıkılaştırıldı (madde 1).
- **Alan taraması hiç ürün bulamadı** — Sentinel-2/GEE mock modda olduğu için
  kayıtsız alanlara zaman serisi üretilmiyor. Gerçek modda kimlik bilgisi
  girilmeli (ikisi de daha önce canlı doğrulanmıştı).
- **Copernicus CLMS katmanı bilinçli olarak iskelet** — bağlanmadı, boş döner,
  uydurma sonuç üretmez.

**Sonuç:** modül teknik olarak çalışıyor; anlamlı sonuç için önce parsellere
gerçek uydu taraması yapılmalı (Uzaktan Algılama > toplu tarama), sonra
`from-plantings` + `calibrate` tekrar çalıştırılmalı.

---


> Bu dosya, oturum yarıda kesilirse BİR SONRAKİ Claude oturumunun kaldığı
> yerden devam edebilmesi içindir. Önce `CLAUDE.md`'yi, sonra BU dosyayı oku.
> Kullanıcı talimatı: "komuta sende, otomatik devam ettir" — yani aşağıdaki
> "KALAN İŞLER" listesi sırayla, ek soru sormadan ilerletilecek.

## Ortam (bu oturumda doğrulandı)

- Çalışan container'lar: `toprax-backend` (8001), `toprax-frontend` (3000, nginx,
  **derlenmiş** build `main.92519ade.js`), `toprax-mongo`, `toprax-ollama` (host 11435).
- Mongo DB adı: **`tarim_kooperatif`** (kimlik: `.env` içindeki
  `MONGO_ROOT_USERNAME`/`MONGO_ROOT_PASSWORD`, authSource `admin`).
- Ollama'da yüklü modeller: `toprax-ai:14b`, `qwen3:14b`, `toprax-ai:8b`, `qwen3:8b`.
  **Vision modeli YOK** (llava çekilmemiş).
- Frontend nginx'ten statik servis edildiği için **kod değişiklikleri
  `docker compose build frontend` + `up -d` yapılmadan canlıya YANSIMAZ.**
  Backend değişikliği için `docker cp` + restart yeterli.

### Minified hataları çözmenin yolu (bu oturumda kuruldu, TEKRAR KULLAN)

`main.92519ade.js.map` mevcut. Hata satır/sütununu kaynak dosyaya çevirmek için:

```bash
docker cp toprax-frontend:/usr/share/nginx/html/static/js/main.92519ade.js.map ./main.map
docker cp ./main.map toprax-backend:/tmp/main.map
docker cp ./resolve.py toprax-backend:/tmp/resolve.py
docker exec toprax-backend python /tmp/resolve.py /tmp/main.map <satir> <sutun>
```

`resolve.py` basit bir VLQ source-map çözücüsüdür (scratchpad'de yazıldı; yoksa
yeniden yazılabilir — sourcemap `mappings` alanını çözüp
`sources[i]:line:col` döndürür).

## BU OTURUMDA TAMAMLANANLAR

| # | Konu | Dosya | Durum |
|---|---|---|---|
| 1 | Parsel harita lejantı | `frontend/src/pages/Parcels.jsx` (`MapLegend`) | ✅ |
| 2 | Sezon Karar Takvimi aşama şeridi tıklanabilir | `frontend/src/pages/SezonKararTakvimi.jsx` | ✅ |
| 4 | Ollama 404 | `backend/ai_router.py` | ✅ |
| 10 | Sayfa çökmeleri | `HaritaPaneli.jsx`, `WorkspaceDrawer.jsx` | ✅ |
| 11 | **AI Yönetişimi (Prompt + Guardrail + RAG)** | `backend/ai_governance.py`, `frontend/src/pages/AiGovernance.jsx` | ✅ |
| 12 | AI Bilgi Kütüphanesi dataset düzenle/sil | `frontend/src/pages/AiKnowledgeLibrary.jsx` | ✅ |

| 3 | İdari sınırlar / il-ilçe lookup | `backend/admin_areas.py`, `backend/field_definitions.py`, `Parcels.jsx`, `AdminAreaManagement.jsx`, `QuickAdd.jsx` | ✅ |

| — | Parseller: "Araçlar" menüsü + harita üzeri Katmanlar/Altlık kontrolü | `Parcels.jsx`, yeni `lib/basemaps.js` | ✅ |
| — | Menü yeniden sınıflandırma: yeni **KARAR DESTEK** grubu | `Layout.jsx` | ✅ |
| — | Sürüm damgası v1.1 → **v1.2 / Build 19082026-1215** | `frontend/src/version.js` | ✅ |

| 5,6,7 | Karar Paneli: Open-Meteo + ekim penceresi + polar/söküm | yeni `components/ParcelDecisionPanel.jsx`, `ParcelDetail.jsx`, `SezonKararTakvimi.jsx` | ✅ |
| 8 | Hasat / Kampanya Lojistiği ayrımı | `HasatLojistigi.jsx`, `Layout.jsx` | ✅ |
| 9 | Yönetilebilir sabit katalogları | yeni `backend/catalog_registry.py`, yeni `components/CatalogManager.jsx`, `soil_biology.py`, `FormYonetimi.jsx` | ✅ |

**KULLANICININ 12 MADDESİNİN TAMAMI + ek istekler TAMAMLANDI.**

**Canlı build:** frontend `main.fc3fe5c9.js` (v1.2 · Build 19082026-1215),
backend imajı yeniden derlendi. 33 rota tarayıcıda çökme taramasından geçti.
`nomic-embed-text` (274 MB) Ollama'ya çekildi — RAG artık **anlamsal** modda.

### #11 mimarisi (özet)

`governed_generate(db, scope, soru)` TEK kapıdır:
prompt birleştir → RAG getir → girdi guardrail → `ai_router` → çıktı guardrail
→ zorunlu uyarı → `ai_governance_logs`.
Koleksiyonlar: `ai_system_prompts` (+`ai_prompt_versions`), `ai_guardrails`,
`ai_rag_documents`, `ai_rag_chunks` (embedding satır içinde),
`ai_governance_logs`. Kapsam listesi `AI_SCOPES` (kod seviyesi registry).
Embedding yoksa **anahtar kelimeye düşer** ve bunu `rag_mode` ile bildirir.
İzinler: `ai_governance:view` / `:manage` (sadece admin katmanı).

**Uçtan uca doğrulandı** (geçici `gov-test@toprax.local` süper admini ile —
test sonrası SİLİNDİ): guardrail IBAN sorusunu engelledi, yüklenen sulama
politikası belgesi 0.70 kosinüs skoruyla getirildi ve yerel model yanıtı
GERÇEKTEN o belgeye dayandırdı ("son 21 gün", "polar 0.8 puan").

**KALAN BAĞLANTI İŞİ:** mevcut AI çağıranları (`extras.py`'nin copilot +
disease uçları, `agronomy.py`, `season_planner.py`) hâlâ `ai_router`'ı
DOĞRUDAN çağırıyor — yani guardrail/RAG'den GEÇMİYORLAR. Bunlar tek tek
`governed_generate`'e taşınmalı (ekran zaten hazır, sadece çağrı noktası
değişecek).

### Kök neden notları (tekrar araştırmayın)

**#4 — Ollama 404.** URL doğruydu; `http://ollama:11434/api/chat` backend
container'ından `toprax-ai:8b` ile 200 dönüyor. Gerçek sebep:
`ollama_vision_model` DB config'inde boştu → kod `DEFAULT_OLLAMA_VISION_MODEL`
(`llava:7b`) kullanıyordu → **Ollama YÜKLÜ OLMAYAN model için 404 döner** ve
`raise_for_status()` bunu "endpoint yok" gibi gösteriyordu.
Düzeltme: `available_models()` eklendi, vision modeli yüklü değilse metin
modeline düşülüyor, 404 artık modeli adıyla söyleyen Türkçe bir hata veriyor,
yerel timeout 60 → 300 sn.

**#10 — Sayfa çökmeleri.** 44 rotanın tamamı canlı tarayıcıda tarandı.
- `/harita-paneli`: `MapClickAdminPopup is not defined` + `AdminAreaPopupLinks`
  — JSX'te kullanılıp import EDİLMEMİŞ. İkisi de eklendi.
- Bildirim çekmecesi (`aside` içindeki `WorkspaceDrawer`): `d.slice is not a
  function`. Sebep: `GET /notifications` 2026-08-19'da düz diziden
  `{items,total,unread}` zarfına geçti (`dashboard_routes.py:201`), ama
  `WorkspaceDrawer.jsx` hâlâ dizi bekliyordu. `Other.jsx` (`/bildirimler`
  sayfası) zaten geriye-uyumluydu. `asList()` helper'ı eklendi.
- **`l is not a function` HİÇBİR rotada tekrar üretilemedi.** Source map onu
  `pages/Extras.jsx:730` (`HastalikTespiti`) olarak çözüyor ama o sayfa
  sorunsuz açılıyor — muhtemelen belirli bir ETKİLEŞİM veya ROL'de tetikleniyor.
  Kullanıcıdan "hangi sayfa + neye tıkladın" bilgisi alınmalı.
- Kullanılıp import edilmemiş JSX bileşenlerini tarayan bir script yazıldı;
  tüm kod tabanında SADECE yukarıdaki iki gerçek bulgu çıktı.

## KALAN / BİLİNEN AÇIKLAR (yeni oturum buradan devam edebilir)

1. **`governed_generate` bağlantısı.** AI Yönetişimi ekranı hazır ve çalışıyor,
   ama mevcut AI çağıranları (`extras.py`'nin copilot + disease uçları,
   `agronomy.py`, `season_planner.py`) hâlâ `ai_router`'ı DOĞRUDAN çağırıyor —
   yani guardrail/RAG'den GEÇMİYORLAR. Tek tek `governed_generate`'e taşınmalı.
2. **Karbon ayak izi ve polar için ayrı EKRAN yok.** `sustainability.py` yalnızca
   2 parsel-bazlı uç sunuyor ve sadece `ParcelInsightCards` içinde bir kartla
   tüketiliyor. Menüde öne çıkarılacak bir sayfa YOK — yapılması gerekiyor.
3. **Hasat çizelgesi yığılması (backend algoritma kusuru).** Canlı testte 43.
   haftaya 117 parsel / 32.468 ton düştü ama günlük kapasite 12.000 ton —
   `harvest_logistics.py` kapasiteye göre haftalara YAYMIYOR gibi görünüyor.
4. **`ilce` lookup'ında 978 değer var, gerçek ilçe 971.** 7 tanesi eski
   oturumdan kalma test kaydı ("Han Mahallesi", "HanSokak"). Referans riski
   nedeniyle silinmedi.
5. **`pypdf` / `python-docx` kurulu değil.** RAG dosya yüklemede PDF/DOCX net
   bir 415 döner (txt/md/csv/json/yaml çalışıyor). İstenirse
   `requirements.txt`'e eklenir.
6. **`l is not a function`** hiçbir rotada tekrar üretilemedi — tekrarlarsa
   hangi sayfa + hangi tıklama bilgisi gerekiyor.

## ARŞİV — tamamlanan işlerin orijinal plan notları

### ~~11. Admin Prompt + RAG Yönetim Ekranı~~ — ✅ TAMAMLANDI (bkz. yukarısı)
<details><summary>Orijinal plan notu (arşiv)</summary>
Kullanıcı isteği: *"kendi LLM'imizi yönetecek bir prompt ekranı ve RAG ekranı.
Sadece adminlerin görebileceği, verilecek cevapların guardrail'lerinin
belirleneceği bir prompt + RAG ekranı. Bu ekran tüm AI için en üst düzey
yönetici olacak. Ayrıca dosya + döküman vb. eklenerek de eğitebileceğim."*

**Kullanıcı kararı: embedding = Ollama + Mongo** (yeni servis YOK, vektörler
Mongo'da, benzerlik Python'da hesaplanır).

Planlanan yapı (henüz KOD YAZILMADI):
- `backend/ai_governance.py`
  - Koleksiyonlar: `ai_system_prompts`, `ai_guardrails`, `ai_rag_documents`,
    `ai_rag_chunks` (embedding vektörü satır içinde), `ai_governance_logs`.
  - `AI_SCOPES` kod-seviyesi registry (`FEATURE_FLAG_LABELS` kalıbı):
    global / copilot / disease / agronomy / season_planner / report vb.
  - `governed_generate(db, scope, system_extra, user_text)` — TEK giriş noktası:
    (1) global + scope prompt'unu birleştir, (2) RAG bağlamını getir,
    (3) girdi guardrail'i, (4) `ai_router.get_ai_router()` ile üret,
    (5) çıktı guardrail'i + zorunlu uyarı metni, (6) logla.
  - Embedding: Ollama `/api/embeddings`, model config'ten
    (`ollama_embed_model`, varsayılan `nomic-embed-text`). **Model yüklü
    değilse** (404) sessizce anahtar-kelime skorlamasına düş — `extras.py`'nin
    "AI yoksa fallback" dürüstlük deseniyle AYNI, `rag_mode` alanıyla bildirilir.
  - Dosya alımı: mevcut `storage.py` `/uploads` KULLANILIR (yeni yükleme
    mekanizması İCAT EDİLMEZ, IT-29/LMS emsali). txt/md/csv/json doğrudan;
    pdf/docx için `requirements.txt` kontrol edilmeli (reportlab var, pypdf
    /python-docx VARSA kullan, YOKSA kullanıcıya onay sorulmadan bağımlılık
    EKLENMEZ — Karar Protokolü).
- `permissions.py`: yeni `ai_governance` modülü (`view`/`manage`), sadece
  admin-tier + `ilce_yoneticisi`'ne verilmesi tartışılmalı (kullanıcı
  "sadece adminler" dedi → `adminTierOnly`).
- `server.py`: `register_ai_governance_routes(...)` çağrısı (mevcut kalıp).
- `frontend/src/pages/AiGovernance.jsx`, route `/ai-yonetimi`, Layout.jsx
  SİSTEM grubu, `adminTierOnly`. Sekmeler: **Sistem Promptları / Guardrail'ler
  / Bilgi Bankası (RAG) / Test Konsolu**.
- Mevcut AI çağıranları (`extras.py` copilot+disease, `agronomy.py`,
  `season_planner.py`) kademeli olarak `governed_generate`'e taşınmalı.

**DİKKAT — yeniden icat etme:** `ai_engine.py` zaten dataset/knowledge-record/
model/validation-queue içeriyor; `agronomy.py`'de `agronomy_prompts` (ürün
bazlı düzenlenebilir prompt kütüphanesi) var. Yeni modül BUNLARIN ÜSTÜNE
kurulmalı, paralel bir sistem açılmamalı.

</details>

### ~~12. AI Bilgi Kütüphanesi — dataset düzenle/sil~~ — ✅ TAMAMLANDI
Backend `PUT`/`DELETE /ai/datasets/{id}` ZATEN VARDI (`ai_engine.py:471,485`);
eksik olan `AiKnowledgeLibrary.jsx`'teki satır içi düzenleme/silme UI'ıydı,
eklendi (ad/kaynak/durum düzenlenir, silme soft-delete). Roller yönünden:
`ai_knowledge:*` izinleri PERMISSION_CATALOG'da zaten tanımlıydı ve Özel
Roller ekranından atanabiliyor; yeni `ai_governance:view/manage` de eklendi
(`ALL_PERMISSIONS` üzerinden üst rollere otomatik geçer, `ilce_yoneticisi`'ne
BİLİNÇLİ verilmedi — kurumun AI sesini belirleyen ayar).

### 3. İdari Sınırlar — sadece Konya geliyor, ilçeler sıkıntılı
İki ayrı veri kaynağı karıştırılmamalı:
- `admin_areas` koleksiyonu (gerçek sınır geometrileri) — kullanıcının önceki
  başarısız toplu yüklemelerinden **662 kısmi kayıt** kalmış olabilir
  (83 il / 578 ilçe / 1 mahalle — CLAUDE.md 2026-07-25 notu). Toplu import
  **idempotent DEĞİL**, yeniden yüklemeden önce temizlenmeli.
- `lookup_groups`/`lookup_values` içindeki il/ilçe (form dropdown'ları) —
  `field_definitions.py` içindeki `seed_il_ilce_lookup` fonksiyonunun
  `TR_IL_ILCE` sözlüğü **sadece Konya + Ankara** içeriyor. 81 il için
  genişletilmeli, sonra `POST /field-definitions/seed-il-ilce-lookup`
  (idempotent) tekrar çağrılmalı.

### 5 + 7. Ekim/söküm tahminleri ve polar UI'da görünmüyor
`backend/polar_engine.py` + `backend/season_planner.py` var. Hangi endpoint'in
nerede tüketildiği tespit edilip Parsel Detay / Sezon Karar Takvimi / Hasat
ekranlarına eklenmeli; ayrıca "hangi ürün ekili" bilgisi parsel kartında
gösterilmeli.

### 6. Open-Meteo UI'a eklenmemiş
`register_weather_routes` (`server.py:559`) var; frontend'de karşılığı yok.
Parsel/sezon ekranına hava durumu paneli eklenmeli.

### 8. Hasat / Lojistik ayrımı
`pages/HasatLojistigi.jsx` + `backend/harvest_logistics.py`. İstenen: adı
**"Hasat"** olsun, **polar'a göre söküm** öne çıksın; lojistik AYRI bir modül
(kendi sayfası + nav girişi) olsun.

### 9. Sabitler/lookup'lar admin tarafından yönetilebilir olsun
Örnek verilen: "Tespit Edilen Organizmalar" (muhtemelen
`backend/soil_biology.py` içinde kod-seviyesi sabit). Geçmiş oturumlarda
eklenen TÜM kod-seviyesi katalog sabitleri taranıp `lookup_groups`/
`lookup_values` ya da kendi CRUD kataloğuna (support_types kalıbı) taşınmalı.

## Doğrulama araçları

- Frontend sözdizimi: `node scratchpad/check.js src/pages/X.jsx`
  (projenin kendi `node_modules/@babel/core` + `preset-react`'ini kullanır).
- Backend: `docker exec toprax-backend python -m py_compile /app/X.py`
- Testler: `pytest` (son bilinen durum 50/50 yeşil).
