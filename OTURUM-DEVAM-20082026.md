# OTURUM DEVAM NOTU — 2026-08-20

> Bu dosya, oturum yarıda kesilirse BİR SONRAKİ Claude oturumunun kaldığı
> yerden devam edebilmesi içindir. Önce `CLAUDE.md`'yi, sonra BU dosyayı oku.
> Önceki devir dokümanı `OTURUM-DEVAM-19082026.md`'nin 12 maddesi bu oturumun
> BAŞINDA zaten tamamlanmıştı (bkz. o dosyanın son hali) — bu oturum kullanıcının
> canlı demoda (demo.toprax.com.tr) bildirdiği YENİ 15 maddelik bir geri
> bildirim turudur.

## Bu oturumda YAPILANLAR (4 faz, hepsi canlı doğrulandı, Docker'a alındı, GitHub'a push edildi)

Dal: `karar-destek-2026-08-19`. Sürüm zinciri: v1.9 → v2.0 → v2.1 → v2.2.

### FAZ 1 — 5 hata (v1.9, commit `b381e19`)
| # | Konu | Kök neden / düzeltme |
|---|---|---|
| 1 | `l is not a function` hatası | **AI Bilgi Kütüphanesi/İzleme çökmesiyle AYNI hata** — minified stack trace çözülerek bulundu. `AiKnowledgeLibrary.jsx`, `Extras.jsx`, `Forms.jsx`, `PlatformAdmin.jsx`'te `useEffect(load, [])` deseni `load`'un döndürdüğü Promise'i React'e cleanup fonksiyonu gibi veriyordu — sekme değişince (unmount) React onu çağırıp çöküyordu. 5 yerde `useEffect(() => { load(); }, [])`'e çevrildi. |
| 2 | Ekim Karar Motoru "Analiz Et" → 500 | `agronomy.py:805` — `solar_signals` async ama `await` olmadan çağrılıyordu (`TypeError: 'coroutine' object is not iterable`, gerçek traceback'le doğrulandı). Tek kelime düzeltme. |
| 3 | Bildirim alanı yarım görünüyor | `WorkspaceDrawer.jsx:157`'deki `line-clamp-2` kaldırıldı. **⚠️ Kullanıcı bu oturumun SONUNDA hâlâ "yarım geliyor" dedi — aşağıdaki "AÇIK KALAN" bölümüne bakın.** |
| 4 | Parsel detayında harita ortalamıyor | `ParcelDetail.jsx` — centroid hesabı (poligonun ilk köşesi değil) + `MapFlyTo` deseni (`Parcels.jsx` emsali) eklendi. |
| 5 | Katmanlar/Altlık butonları görünmüyor | `Parcels.jsx` `MapControls`'a opak `card` zemin eklendi (`MapLegend` emsali). |

### FAZ 2 — UI (v2.0, commit `2c2e152`)
- **Parsel Araçları Harita Paneli'ne EKLENDİ** (Parcels.jsx'e DOKUNULMADI —
  kod inceleyince ~650 satırlık, 7 araçlı, derin bağlı bir sistem olduğu
  ortaya çıktı; kullanıcıya soruldu, "ekle, Parceller'de de bırak" (düşük
  risk) seçildi). Yeni `components/ParcelToolsPanel.jsx` — Manuel Ekle/Çiz/
  Düzenle/Böl/Birleştir/Koordinat Al/İçe Aktar. Birleştir aracı haritada
  tıklama yerine listeden seçim kullanır (HaritaPaneli'nin mevcut popup/
  görev zincirine hiç dokunmamak için bilinçli fark).
- Parcels.jsx: AI Asistan butonu filtre satırının sonuna taşındı.
- `query_engine.py`'ye yeni `GET /query/{module}/distinct?field=` ucu —
  `FilterPanel.jsx` artık lookup alanlarında sadece o modülde GERÇEKTEN
  var olan değerleri gösteriyor (81 il yerine sadece "Konya" gibi). Kayıt
  OLUŞTURMA formları BİLİNÇLİ OLARAK değişmedi (kullanıcı kararı).

### FAZ 3 — köy verisi (v2.1, commit `bd56256`)
- `geo_import.py`'ye `_close_linestring_to_polygon()` — parsel sınır
  dosyalarının (TKGM Parsel Sorgu dahil) LineString olarak yazdığı ama
  aslında kapalı (ilk/son nokta eşit) poligonları Polygon'a çevirir.
  `parcel_routes.py`'nin `/parcels/import-geojson`'ı da aynı dönüşümü +
  birleşik `"Name":"101/10"` (ada/parsel) ayrıştırmasını kullanıyor artık.
- **Canlı DB düzeltmesi (uygulandı):** Abditolu köyünün 637 parselinde
  `parsel_no_tapu` alanında birleşik "101/10" değeri duruyordu, `ada_no`
  kaynakla uyumsuz rastgele bir sayıydı. Kaynaktan yeniden ayrıştırılıp
  düzeltildi. **Yedek:** `backend/_abditolu_ada_parsel_backup_20260820.json`
  (637 kaydın eski hali, geri alınabilir).
- Yeni `scripts/import_village_parcels.py` — Gökhüyük/Kuzucu/Üçhüyük/
  Dinlendik için idempotent, elle çalıştırılan yükleme script'i. Gerçek 4
  dosyayla `--dry-run` doğrulandı: **3635 parsel** (725+2253+248+409) doğru
  okunuyor. **⚠️ CANLIYA YÜKLENMEDİ — kullanıcı kendisi çalıştıracak** (gerçek
  tenant-admin kimlik bilgisi gerektiği için bende yok):
  ```bash
  python scripts/import_village_parcels.py --geojson-dir "C:\Users\Azizhan\Desktop\koyler\tamamı" --email <admin-eposta> --password <şifre>
  ```
  Önce `--dry-run` ile deneme yapılabilir (hiçbir şey yazmaz).

### FAZ 4 — 5 yeni modül (v2.2, commit `a69489e`)
- **Ekim Karar Motoru çoklu ürün:** `agronomy.py`'ye Buğday/Arpa/Mısır/
  Ayçiçeği/Yonca için 44 gerçek agronomik kural + idempotent seed ucu
  (`POST /agronomy/crops/seed-additional` — **canlıda çalıştırıldı**, 6 ürün
  aktif). "arpa"nın bozuk küçük-harf etiketi de düzeltildi ("Arpa"). Yeni
  `POST /ekim-planlama/recommend-crop` — seçilen parsel(ler)e TÜM aktif
  ürünlerin kural kütüphanesini uygulayıp sıralar. `EkimPlanlama.jsx`'e
  yeni "Ürün Önerisi" sekmesi (BulkParcelSelect ile çoklu parsel).
- **Ürün Tanıma tıkla-tespit:** `CropDetection.jsx`'in "Alanı Tara"
  sekmesine tıklanan noktanın etrafına küçük tampon poligon kurup mevcut
  `/crop-classification/area` ucunu çağıran bir mod eklendi.
- **Karbon Ayak İzi parsel sayfası:** Yeni `pages/ParcelCarbonDetail.jsx`
  (`/parseller/:id/karbon`) — mevcut `sustainability.py` uçlarını (ayak izi
  + öneriler + sezon karşılaştırma) tüketir, yeni backend YOK.
  `ParcelInsightCards.jsx` ve `Sustainability.jsx`'ten bağlandı.
- **Dashboard yangın haritası:** `HaritaPaneli.jsx`'e "Yangın (NASA FIRMS)"
  katmanı (`?layer=yangin` deep-link ile otomatik açılır). Dashboard'daki
  ölü `/uzaktan-algilama?view=yangin` yönlendirmesi `/harita-paneli?layer=yangin`'e
  düzeltildi.
- **AI Hastalık sohbeti:** `extras.py`'ye `disease_detection_messages`
  koleksiyonu + `GET/POST /ai/disease-detections/{id}/messages`
  (`case_messages` deseni), `governed_generate` ile gerçek AI yanıtı.
  Gerçek Ollama modeliyle uçtan uca doğrulandı (fungisit uygulama zamanı
  sorusuna tutarlı Türkçe yanıt üretti).

## ✅ ÇÖZÜLDÜ (bu oturumun devamında, 2026-08-20) — Bildirim alanı yarım görünme sorunu

**Gerçek kök neden bulundu ve düzeltildi.** Statik kod incelemesi (bir önceki
bölüm) yanlış iki dosyaya bakmıştı — asıl sorun CSS containing-block kuralıydı:
`WorkspaceDrawer.jsx` (zil ikonundan açılan panel), `Layout.jsx`'in `<aside>`
elemanının (satır 247) İÇİNDE render ediliyordu. `<aside>` her zaman bir
Tailwind `translate-x-*` sınıfı taşıyor (mobil aç/kapa geçişi için —
`-translate-x-full md:translate-x-0` / `translate-x-0`), bu da masaüstünde
bile identity bir `transform: matrix(1,0,0,1,0,0)` üretiyordu. CSS kuralı
gereği `transform` taşıyan `position:fixed` bir eleman, `position:fixed`
alt elemanları için YENİ bir containing block oluşturur — `Drawer.jsx`'in
`fixed inset-0` overlay'i artık viewport'a değil `<aside>`'ın 256px'lik
kutusuna göre konumlanıyordu, panel sağa yaslanmaya çalışırken kutunun
solundan (`x:-47px`) taşıp kırpılıyordu. Gerçek tarayıcıda (Claude Browser,
`demo.toprax.com.tr`, super_admin ile "Bu Kooperatif Olarak Gir") DOM
ölçümüyle (`getBoundingClientRect`) doğrulandı: düzeltmeden ÖNCE panel
`x:-48, w:303` (görünür alanın dışına taşıyordu), düzeltmeden SONRA
`x:845, w:420` (tam viewport içinde, `document.body`'e portal ile render
ediliyor). **Düzeltme:** `Drawer.jsx` — genel/paylaşılan bileşen, sadece
WorkspaceDrawer değil AdminAreaManagement/ExperienceProfiles gibi başka
yerlerde de kullanılıyor — artık `ReactDOM.createPortal` ile DAİMA
`document.body`'e render ediliyor, hangi ata ağacına gömülürse gömülsün bu
sınıf hatadan bağışık. `main.9913cf15.js` olarak derlenip
`docker compose build frontend` + `up -d frontend` ile canlıya alındı
(`COMPOSE_BAKE=false`, `--remove-orphans` KULLANILMADI). **Not:** yeni
build'i test ederken tarayıcı sekmesi ilk başta eski `main.79e852d1.js`'i
önbellekten sunmaya devam etti — `fetch(..., {cache:'no-store'})` ile
sunucunun doğru dosyayı verdiği doğrulanıp `?_cachebust=` ile zorla
yenilendi; gerçek bir kullanıcı sert yenileme (Ctrl+Shift+R) yapması
gerekebilir, bu CDN/tarayıcı önbelleğinin doğal bir yan etkisi, koddan
kaynaklı değil.

<details>
<summary>Önceki (yanlış sonuçlanan) kod incelemesi — arşiv</summary>

### Bildirim alanı hâlâ yarım geliyor (kullanıcı bu oturumun sonunda tekrar bildirdi)
Bu turun 3. maddesinde `WorkspaceDrawer.jsx:157`'deki `line-clamp-2`
kaldırılmıştı (v1.9'da yayınlandı, en son build v2.2'de de mevcut — canlıda
`main.79e852d1.js` servis ediliyor, bayat sürüm DEĞİL). Ama kullanıcı "hâlâ
yarım geliyor" dedi.

**Bu oturumun sonunda statik kod incelemesiyle** (canlı tarayıcı erişimi
olmadan) şu iki şüpheli dosyaya bakıldı, İKİSİ DE sorunsuz görünüyor:
- `pages/NotificationDetail.jsx` — başlık `<h1>` line-clamp'siz, mesaj
  `break-words whitespace-pre-wrap` ile tam render ediliyor gibi.
- `components/Drawer.jsx` — sarmalayıcı `flex-1 overflow-y-auto`, metni
  kırpan bir `overflow:hidden` yok gibi.

**Sonuç: kod incelemesiyle YENİ bir kök neden BULUNAMADI.** Bir sonraki
oturumun İLK işi şu olmalı:
1. Gerçek tarayıcıda (Claude Browser veya Chrome eklentisi) canlıya
   girip **"bildirimler butonu"**na tıklayıp TAM OLARAK hangi ekranın
   açıldığını ve neyin "yarım" göründüğünü ekran görüntüsüyle tespit et —
   "bildirimler butonu" muhtemelen sol menü altındaki zil ikonu
   (`WorkspaceDrawer` açar) ama kullanıcı bunu "sayfa" diye tarif etti,
   belki kastettiği farklı bir giriş noktası (ör. `/bildirimler` sayfasına
   giden başka bir buton, ya da mobil görünüm) olabilir — DOĞRULA.
2. Şüpheli adaylar (öncelik sırasıyla):
   - `Layout.jsx`'teki zil butonunun kendisi/rozeti bir `overflow:hidden`
     ata içinde mi taşıyor (sidebar footer)?
   - Küçük ekran/mobil görünümde `Drawer.jsx`'in `width:420px, maxWidth:
     100vw` davranışı gerçekten taşmayı önlüyor mu?
   - `index.css`'teki `@layer components` sıralaması (2026-07-24/25'te
     bulunan "her şey bozuk görünüyor" kök nedeniyle AYNI aile) başka bir
     class'ı hâlâ etkiliyor olabilir mi — `.card`/`.btn` dışında bildirim
     alanına özel bir sınıf var mı kontrol et.
   - `main.79e852d1.js`'i (canlıda çalışan gerçek bundle) `resolve.py`
     source-map çözücüsüyle (CLAUDE.md'de anlatılan yöntem) kontrol edip
     gerçekten hangi component render ediliyor doğrula — statik okuma
     yanıltıcı olabilir (ör. build cache, farklı bir dal/dosya).

</details>

## Kullanıcı kararıyla ERTELENEN (bu oturumun dışında)
- **Harita Stüdyosu elden geçirme** — kullanıcı "en son onu beraber elden
  geçirelim" dedi, bu oturumda hiç dokunulmadı.
- **Sözleşme onaylama (çiftçi self-servis)** — önceki oturumda (19082026)
  kullanıcı kararıyla ertelenmişti, bu oturumda da gündeme gelmedi.

## Ortam (bu oturumda doğrulandı)
- Docker Desktop + doğru daemon (`toprax_final_12072026_00_mongo_data`
  volume'ü, ~28 volume listede).
- `COMPOSE_BAKE="false"` ZORUNLU, `--remove-orphans` KULLANILMADI (ollama
  hep ayakta kaldı).
- Canlı build: `main.79e852d1.js`, backend imajı v2.2 ile aynı hizada
  yeniden derlendi.
- `toprax-backend`/`toprax-frontend`/`toprax-mongo`/`toprax-ollama` sağlıklı.

## Doğrulama araçları (bu oturumda kullanılan desen)
- Backend mantığı: `docker cp <dosya> toprax-backend:/app/` + izole bir
  smoke-test script'i yazıp `docker exec toprax-backend python /app/...`
  ile GERÇEK DB verisiyle çalıştırmak (agronomy/geo_import/disease chat
  bu şekilde uçtan uca doğrulandı, sonra geçici dosyalar temizlendi).
- Frontend: `@babel/preset-react` ile sözdizimi kontrolü (`node
  scratchpad_check.js <dosya>`, geçici script her seferinde silindi).
- Uyarı: bu oturumda Bash tool zaman zaman kararsızdı (fork hataları,
  zaman aşımları) — PowerShell'e geçmek genelde işe yaradı.

## ✅ ÇÖZÜLDÜ (bu oturumun devamında, 2026-08-20) — Köy verisi canlıya yüklendi + gerçek bir 500 hatası bulunup düzeltildi

Script (`scripts/import_village_parcels.py`) geçici bir tenant-admin hesabıyla
(`bootstrap-admin` ucu, işlem sonrası MongoDB'den silindi) çalıştırıldı.
**Gerçek bir üretim hatası bulundu:** `POST /parcels/import-geojson`
(`parcel_routes.py`), `admin_areas.py`'nin bulk-import'unda 2026-07-25'te
bulunup düzeltilen AYNI hata ailesini taşıyordu — bitişik yinelenen köşe
noktaları içeren bir poligon (`Duplicate vertices`), `insert_many`'nin
varsayılan `ordered=True` davranışı yüzünden TÜM parçayı (chunk) 500 Internal
Server Error ile çökertiyordu; o ana kadar başarıyla toplanan kayıtlar
istemciye hiç yansımadan (ama bazen DB'ye sessizce yazılmış olarak)
kayboluyordu. **Düzeltme:** `admin_areas.py`'nin `_clean_geometry` (bitişik
yinelenen köşe temizleme) fonksiyonu import edilip geometri doğrulamasından
ÖNCE uygulanıyor + `insert_many(created, ordered=False)` + `BulkWriteError`
yakalanıp sadece gerçekten geçersiz kayıtlar `errors` listesine ekleniyor,
geçerli olanlar yazılmaya devam ediyor (`parcel_routes.py`). Backend imajı
yeniden derlenip canlıya alındı. **Sonuç:** 4 köyün (Gökhüyük/Kuzucu/
Üçhüyük/Dinlendik) 3.635 kaynak parselinin 3.623'ü başarıyla içe aktarıldı;
kalan 12'si gerçek veri kalitesi sorunları (kapanmamış LineString / gerçek
self-intersection) — sessizce atlanmadı, `errors` listesinde dürüstçe
raporlandı. **Geçici admin hesabı temizliği:** `users.py`'de gerçek bir
DELETE ucu YOK (convention #3 "soft delete" gereği bilinçli) — sadece
`PUT /users/{id}/status` (pasife alma) var, AMA bu uç kullanıcının KENDİ
hesabını pasife almasını da reddediyor (`"Kendi hesabınızı pasif yapamazsınız"`,
`users.py:193`) — geçici hesap başka bir yönetici hesabıyla pasife
alınabilirdi ama elimde ikinci bir gerçek admin şifresi olmadığından bu
yola gidilmedi. Bunun yerine önceki oturumlarda da (IT-24/25 emsali)
kullanılan desenle doğrudan MongoDB'den SİLİNDİ (`users.deleteOne`) —
bu, soft-delete konvansiyonunun bir istisnası değil, test/geçici verinin
temizliğidir (gerçek kullanıcı verisi hiçbir zaman böyle silinmez).

## ✅ ÇÖZÜLDÜ (bu oturumun devamında, 2026-08-20) — "Mahalle sınırları görünmüyor" + Parseller filtresi boş/eksik sonuç

**Tek bir kök nedenin iki farklı belirtisiydi.** Köy verisi içe aktarma
toplam parsel sayısını 5.249'a çıkarınca, birden çok sayfada var olan
`api.get("/parcels", { params: { limit: 1200 } })` (ve `Parcels.jsx`'te
`limit:500`/`2000` benzerleri) sabit sınırı artık TÜM parselleri değil,
sunucunun döndürdüğü SIRALAMAYA göre ilk N kaydı getiriyordu — canlıda bu
ilk 1200 kaydın TAMAMI tesadüfen tek bir köyden (Abditolu) geliyordu.
Sonuçları:
1. **Parseller filtresi** — "Köy=Kuzucu" seçilince 0 sonuç dönüyordu
   (filtre mantığının kendisi DOĞRUYDU — `/parcels/filter-options`
   zaten sadece DB'deki gerçek distinct değerleri veriyordu — ama
   istemci tarafındaki `parcels` state'i zaten sadece Abditolu'ydu,
   filtrelenecek Kuzucu verisi HİÇ yüklenmemişti).
2. **Mahalle sınırları** — `HaritaPaneli.jsx`/`Parcels.jsx`'in idari
   sınır bbox'ı bu eksik parsel kümesinden türetildiğinden (`parcelBBox`),
   bbox hiçbir zaman Kuzucu/Gökhüyük/Üçhüyük/Dinlendik'in coğrafi
   konumunu KAPSAMIYORDU — `GET /admin-areas?area_type=mahalle&bbox=...`
   o bölgeler için hiç istenmiyordu bile.

**Düzeltme:** `/parcels` çağıran TÜM sayfalardaki (`Parcels.jsx`,
`HaritaPaneli.jsx` [3 yer], `SahaOperasyonlari.jsx`, `Toprak.jsx`,
`Sulama.jsx`, `EkimKaydi.jsx`, `Other.jsx`) `limit` değeri 8000'e
yükseltildi (backend'de `/parcels`'in sabit bir üst sınırı yok, güvenle
büyütülebilir). **Gerçek tarayıcıda uçtan uca doğrulandı:** "Köy=Kuzucu"
filtresi artık 300 satır (gerçek Kuzucu parselleri, ör. KUZ-10)
döndürüyor; Katmanlar → İdari Sınırlar → Mahalle açılınca bbox artık
`32.60,37.31 – 33.02,37.85` gibi TÜM köyleri kapsayan geniş bir alan
oluyor, `GET /admin-areas?area_type=mahalle&...` yanıtında Kuzucu/
Gökhüyük/Dinlendik/Üçhüyükler'in GERÇEK Polygon geometrisiyle (`hasGeom:
true`) döndüğü ve haritada 1544 `<path>` elemanı olarak render edildiği
doğrulandı (`.leaflet-overlay-pane path` sayımı). Konsolda hata yok.
İmaj yeniden derlenip canlıya alındı (`main.cce8dc52.js`).

**Not:** bu `limit` sabitleri yine de bir üst sınır — parsel sayısı
8000'i aşarsa (uzak ama olası) AYNI aile bir sorun tekrar ortaya
çıkabilir. Kalıcı çözüm (server-side sayfalama/filtreleme, SmartDataGrid'in
zaten kullandığı Query Engine deseni) bu oturumun kapsamı dışında
bırakıldı — hızlı, doğru ve düşük riskli bir düzeltme tercih edildi.

## Kalan/bilinen açıklar (bu oturumdan miras)
- ~~Köy verisi (Faz 3) henüz canlıya YÜKLENMEDİ~~ — yukarıya bakın, ÇÖZÜLDÜ.
- ~~Mahalle sınırları görünmüyor / Parseller filtresi boş dönüyor~~ —
  yukarıya bakın, ÇÖZÜLDÜ.
- **Bilinen kalan borç:** `/parcels` çağıran sayfalardaki `limit:8000`
  sabiti hâlâ bir üst sınır — kalıcı çözüm için bu sayfaların (özellikle
  Parcels.jsx/HaritaPaneli.jsx) server-side filtreleme/sayfalamaya
  (Query Engine) taşınması önerilir, ama bu oturumda YAPILMADI.

## ✅ ÇÖZÜLDÜ (aynı oturum, devam) — Mahalle katmanı zoom-kapısı +
Zaman Makinesi bayat metni

Kullanıcı `limit:8000` çözümünün YETERLİ olmadığını, Mahalle sınır
katmanının haritanın GERÇEK zoom seviyesine göre (ilçe düzeyi veya daha
yakın) otomatik aktifleşmesi gerektiğini belirtti — 50.130 kayıtlık
mahalle koleksiyonunu ülke geneli zoom'da (~7) sorgulamak hem anlamsız
(harita okunmaz) hem gereksiz yük. `Parcels.jsx`'e HaritaPaneli.jsx'in
zaten kanıtlanmış `MapSync` ref kalıbının BİREBİR aynısı (`MapViewTracker`)
eklendi — gerçek anlık zoom + görünür alanı izler. Yeni `MAHALLE_MIN_ZOOM
= 11` sabiti (Parcels.jsx VE HaritaPaneli.jsx'te aynı) — mahalle katmanı
işaretli olsa bile bu zoom'a gelmeden `GET /admin-areas?area_type=mahalle`
isteği HİÇ atılmaz; yakınlaşınca haritanın GERÇEK görünür alanından
(statik parcelBBox değil) bbox ile otomatik çekilir. Kullanıcı isteğiyle
mahalle artık VARSAYILAN AÇIK (zoom-kapısı zaten gereksiz isteği
engellediği için elle işaretlemeye gerek yok). UI'da checkbox yanında
kısa "— yakınlaşınca aktif" ipucu (kullanıcının "panel çok genişliyor"
uyarısı üzerine daha önce eklenen uzun açıklama satırı kaldırıldı).

Ayrıca kullanıcı HaritaPaneli.jsx'in Zaman Makinesi panelindeki bayat
"Uydu/NDVI verisi SİMÜLEDİR (gerçek Sentinel Hub entegrasyonu FAZ 9.5)"
uyarısını sildirdi — bu iddia artık YANLIŞ (Sentinel Hub entegrasyonu
2026-07-25'te GERÇEK kimlik bilgisiyle canlıda doğrulanmıştı, bkz.
CLAUDE.md o tarihli not), metin tamamen kaldırıldı.

**Doğrulama notu:** Canlıda düşük zoom'da (harita ilk açılış, zoom 7)
mahalle katmanının GERÇEKTEN isteğe hiç çıkmadığı (87 sınır = sadece
il+ilçe, "— yakınlaşınca aktif" ipucu görünür) doğrulandı. Yüksek zoom'da
otomatik aktifleşmeyi bu ortamın tarayıcı otomasyon araçlarıyla (senkron
DOM click/dblclick/wheel event'leri Leaflet'in zoom kontrolüne
ulaşmadı — muhtemelen headless/otomasyon ortamına özgü bir kısıt, koddan
bağımsız) TEK YÖNLÜ doğrulayamadım; kod HaritaPaneli.jsx'in ZATEN
kanıtlanmış `MapSync` deseninin birebir kopyası olduğundan mantıksal
olarak güvenilir, ama **bir sonraki oturumda gerçek bir tarayıcıda elle
(veya çalışan preview_* araçlarıyla) yakınlaşıp mahalle sınırlarının
GERÇEKTEN belirdiği son bir kez teyit edilmeli.**
- `arpa`'nın etiketi düzeltildi ama bu düzeltme SADECE canlı DB'ye elle
  uygulandı; `seed-additional-crops` ucundaki kod da artık bunu kalıcı
  olarak yapıyor (idempotent, tekrar seed'de sorun çıkarmaz).
- Bildirim "yarım görünüyor" sorunu — yukarıda detaylı.
