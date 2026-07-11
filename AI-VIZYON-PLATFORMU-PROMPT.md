# PROMPT — TABSİS Agricultural Intelligence & AI Vision Platform (Admin Module)

> **Bunu Claude Code'a verirken önce şunu söyleyin:** "Önce CLAUDE.md, ROADMAP.md
> ve ROADMAP-DETAY-TAM.md'yi oku, sonra bu dosyayı uygula." Bu prompt tek
> başına yeterli değil — TABSİS'in mevcut mimari kurallarını (Config Service,
> RBAC, Query Engine, Event Bus, Integration Hub, Provider Pattern) bilmeden
> uygulanırsa paralel/kopuk bir sistem doğar.

## Rol Tanımı

Sen Chief AI Architect, Enterprise GIS Architect, Computer Vision Engineer,
Remote Sensing Scientist, Machine Learning Architect, Precision Agriculture
Expert, MLOps Engineer ve Enterprise Software Architect rollerini aynı anda
üstleniyorsun. TABSİS platformunun **Agricultural Intelligence Engine**'ini
tasarlayıp implemente edeceksin — bu, on yıl boyunca genişleyebilecek bir
çekirdek bileşen olarak düşünülmeli, MVP kısayolları alınmamalı.

**Kritik fark (orijinal isteğe göre eklendi):** Bu bağımsız bir sistem değil.
TABSİS'in içine, mevcut kurallarına uyarak entegre olacak bir **admin
modülü**. Aşağıdaki "TABSİS Entegrasyon Zorunlulukları" bölümü, geri kalan
her bölümden daha yüksek önceliklidir — herhangi bir çelişkide bu bölüm kazanır.

---

## Proje Hakkında

TABSİS (Tarımsal Bilgi Sistemi) sadece bir GIS uygulaması veya Çiftçi Kayıt
Sistemi değil; tam tarımsal yaşam döngüsünü yönetebilen, AI-native bir
Tarımsal Zeka Platformu vizyonundadır.

Mevcut modüller: Çiftçi, Parsel, GIS/Harita (IT-14..17), Sözleşme, Toprak
Analizi, Üretim Planlama (ProductionCycle — IT-05/06), Raporlar, Karar
Destek, Saha Operasyonları (IT-22..24), UFYD (IT-18..21), Comm Hub
(IT-25..28), LMS (IT-29..31).

Gelecek modüller (bu prompt'un kapsamı): Uydu Zekası, Drone Zekası, AI Karar
Destek, Hastalık Tespiti, Verim Tahmini, Akıllı Sulama, Hava Durumu Zekası,
Lojistik, Fabrika Entegrasyonu, Tarımsal Makine, IoT, Sensör Ağları.

---

## En Önemli Tasarım İlkesi: Maliyet Minimizasyonu

Her görüntünün GPT/Claude/Gemini gibi bulut modellerine gönderilmesi
istenmiyor. Katmanlı bir karar mimarisi kurulmalı — sistem önce **her zaman
yerelde** çözmeyi dener, bulut AI sadece yerel modeller yetersiz kaldığında
devreye girer.

Beklenen akış:
```
Uydu/Drone/Mobil/Lab Görüntüsü
  ↓
Görüntü Ön İşleme
  ↓
Spektral Analiz
  ↓
Kural Motoru (Rule Engine)
  ↓
Yerel AI Vision Modelleri
  ↓
Güven Değerlendirmesi (Confidence Engine)
  ↓
Yüksek güven → sonucu doğrudan döndür
Düşük güven → Bulut Vision AI'ya escalate et (GPT/Claude/Gemini)
  ↓
Uzman Doğrulaması (gerekirse)
  ↓
Bilgi Kütüphanesi'nin zenginleşmesi
  ↓
Model İyileştirme (Active Learning)
```
Mimari, minimum token tüketimi için optimize edilmeli.

**Eklenen alt ilke — Tenant Bazlı Maliyet İzolasyonu:** TABSİS çok kiracılı
bir sistemdir. Confidence Engine'in bulut escalation kararı, sadece görüntü
güvenine değil, **o tenant'ın kalan aylık AI bütçesine/kotasına** da bakmalı.
Kota aşıldığında sistem düşük güvenle de olsa yerel sonucu döndürür,
kullanıcıya "bu sonuç düşük güvenle üretildi, bütçe nedeniyle bulut
doğrulaması yapılmadı" uyarısıyla — asla sessizce sonuç vermez, asla tek bir
tenant'ın aşırı kullanımı diğer tenant'ların bütçesini etkilemez.

---

## Faz-1 Altyapı Kısıtı

Faz-1 tek sunucu üzerinde çalışacak (~3000-5000 parsel): PostgreSQL, PostGIS,
GeoServer, Backend API'ler, Web Uygulaması, Redis, RabbitMQ, AI Engine — hepsi
aynı sunucuda.

**AI Engine bağımsız bir mikroservis olarak tasarlanmalı** — başlangıçta aynı
sunucuda olsa da, uygulama mimarisinde değişiklik gerektirmeden ayrı bir AI
sunucusuna taşınabilmeli. Bu taşınabilirliğin nasıl çalışacağı açıkça
tanımlanmalı.

**Eklenen not — mevcut TABSİS altyapısıyla çelişki kontrolü:** ROADMAP.md'nin
B bölümünde "Redis/RabbitMQ/Elasticsearch/GeoServer → soyutlama arkasında
Mongo/in-process karşılık" kararı var (gerçek servis hesapları henüz yok) ve
TABSİS'in ana veritabanı **MongoDB**'dir (PostgreSQL/PostGIS değil). Bu
prompt'taki PostgreSQL/PostGIS/Redis/RabbitMQ talebi, TABSİS'in geri kalanıyla
**tutarsız** — Claude Code bu çelişkiyi görmezden gelmemeli. İki seçenek var,
Claude Code görevi başlamadan bunu kullanıcıya sormalı:
(a) AI Engine kendi ayrı veritabanı/kuyruk yığınını (Postgres+PostGIS+Redis+
RabbitMQ) kullanır, TABSİS ana sistemiyle sadece API/event üzerinden konuşur
(mikroservis izolasyonu argümanıyla savunulabilir — raster/vektör veri için
PostGIS gerçekten daha uygun olabilir), **veya**
(b) mevcut ROADMAP.md kararına sadık kalınıp Mongo + in-process soyutlama
kullanılır, PostGIS yerine Mongo'nun geospatial index'leri değerlendirilir.
Varsayılan öneri: **(a)** — çünkü raster/vektör-ağır bir AI Engine için
PostGIS gerçek bir teknik avantaj sağlar ve "bağımsız mikroservis" ilkesiyle
zaten örtüşüyor; ama bu sunucu sayısını/ops yükünü artırır, kullanıcı onayı
gerekir.

---

## Görüntü Kaynakları

Uydu, Drone, Mobil Telefon, Tablet, Laboratuvar, Mikroskop, gelecekteki
Sensör görüntüleri — hepsi aynı AI pipeline'ından geçmeli.

**Eklenen — mevcut kaynaklarla çakışmayı önleme:**
- **Uydu görüntüsü:** TABSİS'te zaten IT-17'de bir Uydu Provider Soyutlaması
  var (NASA/Sentinel/Planet/Maxar, demo/simüle katman). Bu AI platformu o
  soyutlamayı **kaynak** olarak kullanır, kendi uydu entegrasyonunu icat
  etmez — pipeline'ın girdisi IT-17'nin çıktısıdır.
- **Mobil görüntü:** TABSİS'in mobil rol matrisinde (IT-35) Saha Personeli
  zaten GPS+zaman damgalı fotoğraf/video çekiyor ve docx'te "AI Kamera"
  gelecek fazı zaten planlı. Bu platform o akışın **backend'i** olmalı —
  mobil taraf çekim/upload'u yapar, bu platform analiz eder. Offline çekilen
  fotoğraflar senkronize olduğunda otomatik pipeline'a girer (kuyruğa eklenir).
- **Drone/Lab/Sensör:** bu prompt kapsamında yeni entegrasyon noktaları,
  ama hepsi aynı Provider Pattern (IT-32 Integration Hub) ile soyutlanmalı.

---

## Çekirdek Bileşen: Agricultural Knowledge Library

Bu basit bir görüntü deposu değil — tüm tarımsal zeka sisteminin kurumsal
bilgi tabanı. Detaylı tasarlanmalı.

**Desteklenmesi gerekenler:** tekli/toplu/klasör/ZIP upload, drag&drop,
dataset import/export, versiyonlama, metadata düzenleme, görüntü inceleme,
etiket düzenleme, polygon/bounding box/segmentation mask annotation,
sınıflandırma etiketleri, çoklu etiket, yorumlar, uzman notları, kalite
skoru, onay iş akışı, versiyon geçmişi.

**Desteklenen bilgi nesneleri ve ilişkiler:** Ürün, Gelişim Evresi,
Hastalık, Zararlı, Besin Eksikliği, Su Stresi, Yabani Ot, Yangın, Sel, Hasat
Olgunluğu, Toprak Durumu, Hava Durumu, Spektral Özellikler, Drone
Gözlemleri, Uydu Gözlemleri, Laboratuvar Sonuçları. Her nesne birden fazla
kaynaktan birden fazla görüntüyü destekler.

**Eklenen — TABSİS varlıklarıyla ilişki (orijinalde eksikti):** Her
Knowledge Library kaydı, mümkün olduğunda TABSİS'in mevcut varlıklarına
bağlanmalı: `parcel_id`, `production_cycle_id`, `farmer_id` (opsiyonel
referanslar). Bu sayede bir hastalık tespiti doğrudan ilgili Parsel'in
Ziyaret Geçmişi'nde (IT-23), ProductionCycle'ın AI alanlarında (IT-02'de
zaten "AI Risk Skoru/AI Önerisi" placeholder alanları vardı, bunlar burada
gerçek veriyle dolar) görünebilir olmalı.

---

## Veri Modeli

Tam veritabanı modelini tasarla: tablolar, ilişkiler, metadata, versiyonlama,
dataset yönetimi, taksonomi, etiketler, ontoloji, knowledge graph
olasılıkları, tarihsel kayıtlar, audit log'lar.

**Eklenen kural:** Audit log kendi mekanizmasını icat etmez, TABSİS'in ortak
Audit Log altyapısını kullanır (CLAUDE.md Bölüm 6.2). RBAC/permission modeli
ayrı bir sistem değil, mevcut Permission yapısını (`AIKnowledge.Create`,
`AIKnowledge.Approve`, `AIModel.Deploy` gibi) IT-07'deki Permission
listesine ekler.

---

## Yerel AI Modelleri

En iyi açık kaynak modelleri öner (örn. YOLO, SAM2, U-Net, SegFormer,
Mask2Former, DeepLab, Vision Transformer, Prithvi, Clay Foundation Model,
tarımsal foundation modeller). Her biri için: amaç, avantaj, zayıflık, GPU
gereksinimi, CPU uyumluluğu, bellek kullanımı, inference hızı, eğitim
zorluğu, **lisanslama**. Object Detection, Segmentation, Classification,
Change Detection, Anomaly Detection, Disease Detection, Crop Recognition,
Parcel Analysis için hangi modeller kullanılmalı, ayrı ayrı belirt.

**Eklenen — lisans kontrolü ticari bağlama bağlanmalı:** TABSİS ticari bir
ürün olarak satılacak (bkz. ROADMAP-ÜRÜNLEŞTİRME.md PR-17). Önerilen her
model için **ticari on-premise dağıtıma uygunluk** açıkça belirtilmeli
(örn. bazı foundation modeller sadece araştırma lisanslı olabilir) —
"akademik kullanım serbest ama ticari on-premise dağıtımda dikkat" gibi
notlar mutlaka eklensin, bu PR-17'nin girdisi olacak.

---

## Active Learning ve Human-in-the-Loop

Uzman düzeltmeleri, reddedilen tahminler, onaylanan tahminler, yanlış
pozitif/negatifler otomatik olarak gelecekteki eğitim verisi haline
gelmeli — kurumsal bir Active Learning iş akışı tanımla.

Ziraat Mühendisleri için ayrı bir doğrulama arayüzü tasarla: düşük güvenli
tahminleri, bilinmeyen nesneleri, yeni hastalıkları, nadir durumları,
anomalileri otomatik önceliklendiren, renk kodlu, onay/düzeltme/yeniden
eğitim iş akışlı, performans istatistikli bir ekran.

**Eklenen — mevcut Uzman Desteği modülüyle çakışmayı önleme:** TABSİS'te
zaten LMS'in bir parçası olarak "Uzman Desteği" (IT-31) var — eğitim
içinden soru sorma, Case modeline (IT-28) bağlanan bir mesajlaşma sistemi.
Bu yeni doğrulama arayüzü **ayrı bir mesajlaşma sistemi icat etmemeli**; bir
tahmin uzman incelemesine düştüğünde bu, Case modelinin yeni bir türü
(`category: AI Doğrulama`) olarak açılabilir, böylece uzmanın "Onay
Bekleyenlerim" ekranında (IT-07b) diğer onaylarla birlikte görünür.

---

## Confidence Engine ve AI Orchestration

Güven eşikleri, otomatik onay, uzman incelemesi, bulut escalation, model
karşılaştırma, konsensüs mantığını tasarla — birden fazla yerel modelin
bulut AI'ya gitmeden önce nasıl işbirliği yapacağını açıkla.

Job Queue, RabbitMQ (veya Mongo tabanı seçilirse eşdeğeri), background
worker'lar, task scheduling, retry stratejisi, öncelik kuyruğu, batch
processing, dağıtık işleme, gelecekteki GPU sunucu entegrasyonunu tasarla.

**Eklenen — Event Bus entegrasyonu (orijinalde eksikti):** AI Orchestration
kendi bildirim/tetikleme mantığını yazmaz. Önemli sonuçlar (örn. hastalık
tespit edildi, risk oluştu) TABSİS'in `platform/events.py` event bus'ına
yayınlanır (örn. `AIHastalikTespitEdildi`, `AIRiskOlustu`). Bu olaylar zaten
planlı olan tüketicilere gider: Saha Operasyonları (IT-24, otomatik görev
oluşturma — docx'te zaten "AI hastalık tespit etti → görev" senaryosu
vardı), Comm Hub (IT-27, Communication Policy ile çiftçiye/mühendise
bildirim), Harita (IT-17, AI Harita Asistanı sorgularına girdi). AI
Orchestration kendi email/SMS/görev mantığını **asla** yazmaz.

---

## MLOps

Model Registry, versiyonlama, eğitim, doğrulama, test, deployment, rollback,
izleme, performans metrikleri, drift detection dahil kurumsal bir MLOps
stratejisi tanımla.

**Eklenen:** Model deployment/rollback, Health Center'ın (IT-33) bir
parçası olarak görünür olmalı — "AI Model Sağlığı" GodMode/Health Center
ekranında ayrı bir servis satırı olarak izlenebilmeli (drift/hata oranı
kırmızı/sarı/yeşil). Yeni bir model deploy edilmeden önce, **golden
dataset** üzerinde regresyon testi geçmeli (yanlışlıkla eski modelden daha
kötü bir model prod'a çıkmasın) — bu adım açıkça MLOps akışına eklenmeli.

---

## Performans, Güvenlik, Arayüzler, API

Tek sunucu + 3000-5000 parsel + CPU inference + gelecekteki GPU desteği için
optimize et; RBAC, dataset izinleri, audit log, versiyon geçmişi, görüntü
şifreleme, güvenli depolama, API güvenliğini tasarla. Gerekli tüm ekranları
(Knowledge Library, Dataset Manager, Image Browser, Annotation Screen,
Expert Validation Screen, Model Training Screen, Model Management,
Prediction Review, AI Monitoring Dashboard, Training History, Dataset
Statistics, Model Comparison, Inference History) ve REST API'leri (Dataset
Management, Prediction, Model Management, Training, Validation, Image
Upload, Bulk Upload, Expert Approval, Knowledge Search, Inference) tasarla.

**Eklenen — TABSİS kurallarıyla zorunlu uyum:**
- Görüntü/dosya depolama TABSİS'in `storage.py` soyutlamasını kullanır
  (IT-04), yeni bir depolama katmanı icat edilmez.
- Tüm API'ler TABSİS'in Standard API sözleşmesine (Create/Update/
  Delete-Soft/Get/GetById/Search/Filter/Bulk/Import/Export) ve response
  zarfı/hata formatı standardına (ROADMAP-ÜRÜNLEŞTİRME.md PR-22/23) uyar;
  ayrı bir API konvansiyonu yazılmaz. Otomatik Postman collection'a (PR-25)
  bu modül de dahil olur.
- Knowledge Search, kendi arama motorunu yazmaz — TABSİS Query Engine'in
  (IT-08) filter DSL'ini genişletir (yeni filtrelenebilir alanlar tanımlar).
- Görüntü verisi cloud AI'ya gönderilmeden önce **kimliklendirici metadata
  (çiftçi adı, tam adres, IBAN benzeri hiçbir şey) sadece görüntünün kendisi
  ve gerekli teknik metadata (GPS opsiyonel, tarih) gönderilir** — bu adım
  Confidence Engine'in bulut escalation basamağında zorunlu bir "redaksiyon"
  filtresi olarak koda geçmeli.
- **Menü yerleşimi kararı (Claude Code görevi başlamadan sormalı):**
  CLAUDE.md'deki Kural 3, 7 sabit menü grubunu (Operasyon/Harita/Finans/
  İletişim/Eğitim/Raporlar/Ayarlar) zorunlu kılıyor ve 8. bir grup
  açılmasını yasaklıyor. Bu modülün ekran sayısı (13 farklı ekran) göz
  önüne alındığında iki seçenek var: (a) "Ayarlar" menüsü altında "AI
  Bilgi Kütüphanesi" alt-grubu olarak sıkıştırılır, veya (b) GodMode'a
  (IT-36) benzer şekilde, gerekçeli bir istisna olarak ayrı bir üst menü
  maddesi açılır (bu modül sadece Admin/Super Admin'e açık olduğu için
  GodMode'daki "normal kullanıcıdan gizli" mantığına kısmen benziyor, ama
  GodMode'un aksine birden fazla kişi — tüm adminler — erişecek). Öneri:
  **(a)** — Kural 3'ün ruhuna sadık kalmak, ama bu bir tasarım kararı
  olduğu için Claude Code kullanıcıya sormalı, kendi başına 8. menü
  açmamalı.

---

## Sistem Mimarisi ve Gelecek Fazlar

Backend, Database, GeoServer, Raster Storage, MinIO, Redis, RabbitMQ, AI
Engine, Knowledge Library, Yerel AI Modelleri, Cloud AI, İzleme, Loglama,
gelecekteki GPU sunucusunu içeren tam mimariyi üret. Faz 1 (Tek Sunucu) →
Faz 2 (Ayrı AI Sunucusu) → Faz 3 (Çoklu AI Worker) → Faz 4 (Dağıtık AI
Cluster) evrimini iş mantığını değiştirmeden açıkla.

**Eklenen:** Faz 2+ geçişi (AI sunucusunun fiziksel adresinin değişmesi),
TABSİS'in zaten planlı **Service Registry** (IT-32/33) prensibiyle
çözülmeli — hiçbir modül AI Engine'in adresini hardcode etmez, Service
Registry'den bulur. Bu, dokümanın "mimari değişmeden taşınabilmeli" isteğini
TABSİS'in kendi diliyle karşılar.

---

## Beklenen Çıktı Formatı (Claude Code için zorunlu talimat)

Bu görevin çıktısı dağınık bir "rapor" olmamalı. Aşağıdaki iki parçayı üret:

1. **Mimari doküman** (`AI-VIZYON-PLATFORMU-MIMARI.md`): yukarıdaki tüm
   bölümlerin (diyagramlar dahil, ASCII yeterli) doldurulmuş hali —
   modül hiyerarşisi, bileşen sorumlulukları, veritabanı tasarımı, model
   önerileri, Knowledge Library mimarisi, Active Learning/Human-in-the-Loop
   akışı, MLOps stratejisi, performans/güvenlik stratejisi, API önerileri,
   deployment mimarisi, ölçeklenebilirlik yol haritası.
2. **Uygulama planı**: bu doküman `ROADMAP-DETAY-TAM.md` formatına uygun,
   **IT-38'den başlayan** numaralı iterasyonlara bölünmeli (IT-37 zaten
   "gelecek mobil özellikler" için ayrılmış — bkz. ROADMAP.md), her biri
   veri modeli + API + UI + Kabul Kriterleri ile. Öneri kırılımı: Knowledge
   Library çekirdeği, Local AI Pipeline + Confidence Engine, Cloud
   Escalation + Tenant Kota, Active Learning + Human-in-the-Loop arayüzü,
   MLOps/Model Registry, Mobil AI Kamera köprüsü. Bu IT'ler ROADMAP.md'nin
   yeni bir **FAZ 14 — Agricultural Intelligence** bloğuna eklenmek üzere
   önerilmeli (kullanıcı onayı sonrası ROADMAP.md'ye işlenir).

**Başlamadan önce Claude Code'un kullanıcıya sorması gereken 2 açık karar:**
(1) Veritabanı/kuyruk yığını — PostgreSQL+PostGIS+Redis+RabbitMQ (izole
mikroservis) mı, yoksa mevcut Mongo+in-process mi?
(2) Menü yerleşimi — "Ayarlar" altında mı, yoksa gerekçeli 8. istisna menü
maddesi mi?
