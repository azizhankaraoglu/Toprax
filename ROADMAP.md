# ROADMAP.md — TABSİS Uzun Vadeli Geliştirme Planı

> Kaynak: `geliştirmeler.pdf` (109 sayfa, Global Kural + Sprint A1, A2, 3–12)
> Bu plan iş atama sözleşmemizdir: kullanıcı bir **IT-XX** kodu verir,
> Claude o iterasyonu tek oturumda tamamlar ve zip teslim eder.
> Durum işaretleri: ✅ tamam · 🔄 devam · ⬜ bekliyor · ⏸ ertelendi

---

## A. Yapılabilirlik Değerlendirmesi (özet)

| Kategori | Karar |
|---|---|
| A1 kalan, A2, S3 tamamlama, S5, S6, S7, S8, S9, S10, S11'in çoğu | **Tam yapılabilir** — mevcut FastAPI+Mongo+React yığını yeterli |
| S4 Spatial Ops | **Yapılabilir**, uydu görüntüsü *provider soyutlaması + demo katman* olarak (gerçek NASA/Sentinel/Planet hesabı yok) |
| S9 kanalları (SMS/WhatsApp/IVR) | **Provider pattern + simülasyon** — gerçek gateway hesabı bağlandığında sadece provider dosyası yazılır, mimari hazır olur |
| Redis/RabbitMQ/Elasticsearch/GeoServer | **Soyutlama arkasında Mongo/in-process karşılık** — arayüz korunur, ileride gerçek servis takılabilir |
| MERNİS/TAKBİS/e-Devlet | ⏸ **Ertelendi** — resmi erişim gerektirir; Integration Hub'da yuva (slot) bırakılır |
| S12 Flutter mobil | ⚠️ **Bu ortamda Flutter derlenemez.** İki seçenek: (a) **PWA** (önerilen — mevcut React'ten görev odaklı mobil deneyim, offline destekli, tek oturumda ilerletilebilir), (b) Flutter proje iskeleti üretilir ama test edilemez. Karar IT-35'te kullanıcıya soruldu, **PWA seçildi** |

## B. Uyarlama Kararları (doküman → mevcut stack)

1. Doküman .NET/SQL varsayan yerlerde kavram Mongo+FastAPI'ye çevrilir
   (ör. "gerçek kolon" = Pydantic modelde tipli alan; "tablo" = koleksiyon).
2. Event Driven mimari → önce **in-process event bus** (`platform/events.py`),
   ileride kuyruk sistemine geçilebilir arayüzle.
3. CQRS önerisi → ayrı read-model YOK; Query Engine'de projection +
   index + sayfalama ile "okuma yolu optimizasyonu" uygulanır.
4. Object Storage → dosyalar `uploads/` altında, erişim `storage.py`
   soyutlaması üzerinden (ileride S3/MinIO takılabilir).
5. God Mode/Super Admin → mevcut 8-rol hiyerarşisi + platform admin üstüne
   **sistem rolü katmanı** olarak eklenir, mevcut roller bozulmaz.

## C. Faz ve İterasyon Planı

Sıralama gerekçesi (dokümanın kendi omurga tanımı): **ProductionCycle (iş
modeli) → RBAC (güvenlik) → Query Engine (veri erişimi) → Spatial/UX (deneyim)**
önce kurulur; UFYD/Saha/İletişim/LMS bunların üstüne gelir. Config/Secrets
her şeyden önce, çünkü tüm sonraki modüller onu kullanır.

### FAZ 0 — Platform Temeli
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-01** ✅ | **Config Service + Secrets standardı:** `.env.example`, merkezi `config_service.py` (tüm modüller ayarları buradan okur), log'larda secret maskeleme, Integration Center'a health-check/son bağlantı zamanı + timeout/retry alanları | — |
| **IT-01.5** ✅ (İl-İlçe seed genişletmesi hariç) | **Lookup v2 (Kaskad Bağımlılık):** `lookup_groups`'a `parent_group_id`; Form Yönetimi'nde alan-alan bağımlılık tanımı (`depends_on_field`); toplu değer girişi ekranı (kopyala-yapıştır, satır başına bir değer); `DynamicFieldsSection`'da kaskad select davranışı (üst alan değişince alt liste filtrelenir ve temizlenir); İl-İlçe seed verisi | IT-01 |

### FAZ 1 — Sprint A1 kalanı (Veri Giriş Altyapısı)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-02** ✅ | Parsel + Toprak alan genişletme (PDF'teki listeler: ada/parsel, il/ilçe, rakım/eğim, sahiplik/kira, altyapı; toprak: tekstür/derinlik/taşlılık, tuzluluk/kireç, Zn/Fe/B, rapor no, AI alanları) + seed + DynamicFieldsSection entegrasyonu | A1-F1 ✅ |
| **IT-03** ✅ | Sözleşme + Ekim Planlama alan genişletme (tür/taraflar/prim/kesinti/fabrika-teslim; sezon/tohum çeşidi/takvim/kaynak planlama referansları) + seed | A1-F1 ✅ |
| **IT-04** ✅ | **Edit formları + dosya alan tipleri:** Çiftçi/Parsel düzenleme ekranları (DynamicFieldsSection ile), `storage.py` + basit dosya/resim upload (file/image/multifile alan tiplerinin UI karşılığı), doküman sekmesi | IT-02 |

### FAZ 2 — Sprint A2 (ProductionCycle omurgası)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-05** ✅ | ProductionCycle backend: model (year/season/status/farmer/parcel), CRUD + durum makinesi (Planning→Active→Harvesting→Completed/Cancelled), mevcut planting/contract/soil/kantar kayıtlarını sezona bağlayan **migration script** (production_cycle_id alanı, geriye uyumlu — eski parcel_id korunur) | IT-04 |
| **IT-06** ✅ | ProductionCycle UI: Parsel detayında "Üretim Sezonları" sekmesi, sezon çalışma ekranı (sezon altında toprak/ekim/sözleşme/hasat zinciri), yeni kayıtların sezon bağlamında açılması | IT-05 |

### FAZ 3 — Sprint 3 tamamlama (RBAC)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-07** ✅ | Sistem rolleri katmanı (God Mode / Super Admin / Admin / User) mevcut 8-rol + tenant yapısının üstüne; **Field-Level Security v1** (IBAN vb. hassas alanlar permission'a göre maskelenir — field_definitions'a `sensitive` bayrağı); ProductionCycle permission'ları | IT-05 |

### FAZ 4 — Sprint 5 (Universal Query & Filter Engine)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-08** ✅ | Query Engine çekirdeği: filter DSL (alan+operatör+değer, AND/OR), server-side pagination/sorting/projection, modül başına "filtrelenebilir alan" kaydı (field_definitions ile otomatik entegre), `/api/query/{module}` endpoint'i | IT-07 |
| **IT-09** ✅ | Saved Queries + Portföy (Favorilerim) + sorgu paylaşımı + liste ekranlarına genel filtre paneli bileşeni | IT-08 |
| **IT-10** ✅ | Global arama (çiftçi/parsel/sözleşme/sezon tek kutu) + AI doğal dil → Query Engine köprüsü (mevcut copilot'u gerçek sorguya bağlama) | IT-08 |

### FAZ 5 — Sprint 6 (UX / Workspace)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-11** ✅ | **SmartDataGrid** ortak bileşeni: kolon göster/gizle/sırala/sabitle, kolon bazlı filtre, çoklu sıralama, sayfalama, Excel/CSV export, satır çoklu seçim — Query Engine'e bağlı | IT-09 |
| **IT-12** ✅ | Drawer (yan panel) altyapısı + breadcrumb + Son Açılanlar + Favoriler + bildirim çekmecesi | IT-11 |
| **IT-13** ✅ | Workspace dönüşümü: Çiftçi ve Parsel kartları context-aware CRUD'a geçer (kart içinden yeni sözleşme/sezon/görev — bağlam otomatik dolar), Quick Actions | IT-12 |

### FAZ 5.5 — GIS Veri Altyapısı
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-13.5** ✅ | **Geo Dosya İçe Aktarma:** SHP (pyshp) + GeoJSON + KML + DXF (ezdxf) yükleme ve parse; koordinat sistemi dönüşüm katmanı (pyproj — ITRF96/ED50 3° dilimler → WGS84, EPSG kodu seçimli); geometri önizleme + onay akışı (kullanıcı haritada görüp onaylamadan kayıt yazılmaz); geometrinin parsele veya idari alana bağlanması; NCZ dosyaları doküman olarak arşivlenir (parse edilmez — tescilli format, kullanıcıya NetCAD'den SHP/DXF export yolu gösterilir) | IT-04 |
| **IT-13.6** ✅ | **İdari Alanlar + Demografi + Layer v1:** `admin_areas` koleksiyonu (il/ilçe/mahalle, parent_id hiyerarşi, GeoJSON MultiPolygon, 2dsphere index); IT-01.5 lookup'larıyla tek kaynak ilkesi; demografik alanlar field_definitions üzerinden dinamik yönetilir (modül: admin_areas); sınır geometrileri kullanıcı tarafından IT-13.5 import akışıyla yüklenir — sisteme hazır sınır verisi gömülmez, seed yapılmaz; toplu yükleme desteklenir (tek SHP'den çok sayıda idari alan, ad/tip alan eşleştirmesiyle); görüntüleme için geometri sadeleştirme; Parsel haritasında aç/kapa idari sınır katmanları (Layer v1); idari alan yönetim ekranı (liste + sınır önizleme + demografi düzenleme + o alandaki çiftçi/parsel özeti) | IT-13.5, IT-01.5 |

### FAZ 6 — Sprint 4 (Spatial Operations Center)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-14** ✅ | Widget tabanlı harita dashboard'u (8 temel widget) + harita↔dashboard senkron (zoom/filtre/seçim) + kişisel çalışma alanı kaydetme | IT-10, IT-13.6 |
| **IT-15** ✅ | Katman yönetimi + basemap değiştirici + çizim araçları (polygon/rect/circle → içindeki parseller otomatik seçilir) + çoklu parsel toplu işlemleri | IT-14, IT-13.6 |
| **IT-16** ✅ | TKGM GeoJSON import akışı + zenginleştirilmiş parsel popup (hızlı işlem merkezi) + navigasyon linki + **Harita Snapshot** (kaydet/paylaş) | IT-15, IT-13.6 |
| **IT-17** ✅ | **Mekânsal Zaman Makinesi** (tek time-slider → harita+dashboard+sezon senkron) + uydu görüntü provider soyutlaması (demo/simüle katman + tarihsel slider) + AI Harita Asistanı (NL → Query Engine → harita filtre/seçim) | IT-16, IT-13.6 |

### FAZ 7 — Sprint 7 (UFYD — Üretim Finans Yaşam Döngüsü)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-18** ✅ | Destek Kataloğu (yönetilebilir destek tipleri) + Destek Talep süreci (9 durumlu akış) + çiftçi portalına talep ekranı | IT-06, IT-07 |
| **IT-19** ✅ | **Financial Ledger** (silinemez hareket defteri, ters kayıt) + sezon bazlı Cari Hesap ekranı | IT-18 |
| **IT-20** ✅ | Hakediş motoru: tartım/tonaj/kalite/kota/fiyat → brüt hakediş → otomatik mahsup → net; prim/kesinti tanımları | IT-19 |
| **IT-21** ✅ | **İcmal/Mutabakat belgesi** (PDF üretimi + çiftçi dijital onayı + itiraz) + finansal simülasyon (what-if) + UFYD dashboard | IT-20 |

### FAZ 8 — Sprint 8 (Saha Operasyonları)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-22** ✅ | **İş Emri / Görev / Ziyaret** üçlü modeli + 11 durumlu görev yaşam döngüsü + yönetilebilir görev tipleri + checklist (tamamlanmadan kapanmaz) + M18 form bağlama | IT-06, IT-08 |
| **IT-23** ✅ | Kanban + takvim görünümleri + harita entegrasyonu (görevler haritada, haritadan görev oluşturma) + ziyaret geçmişi sekmesi | IT-22, IT-15 |
| **IT-24** ✅ | Kural tabanlı otomatik görev oluşturma (olay → görev) + saha raporları + modül dashboard'u | IT-23 |

### FAZ 9 — Sprint 9 (Communication Hub)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-25** | Kanal **Provider Pattern** (SMS/Email/WhatsApp/Push/IVR — simüle sağlayıcılar + Integration Center bağlantısı) + şablon yönetimi ({{FarmerName}} vb.) + kişi kartına İletişim sekmesi + iletişim timeline | IT-01, IT-07 |
| **IT-26** | Segment yönetimi (Query Engine tabanlı) + kampanya yaşam döngüsü + planlı gönderim + yönetici onayı + retry/fallback zinciri | IT-25, IT-09 |
| **IT-27** | **Event bus v1** (`platform/events.py`) + olay bazlı iletişim kuralları (Communication Policy) + tercih merkezi + kara liste (KVKK) | IT-26 |
| **IT-28** | **Inbound Case yönetimi** (Konu/Case: talep+şikayet+ihbar tek modelde) + iki yönlü mesajlaşma + atama/devir + kategoriler + Saha Operasyonlarına otomatik görev köprüsü | IT-27, IT-24 |

### FAZ 9.5 — Akıllı Tarım Motoru (AI + Uydu/Drone)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-28.1** 🔄 | **Uydu Veri Boru Hattı + Provider Soyutlaması:** `SatelliteProvider` arayüzü (`get_imagery`, `get_index_series`, `request_tasking`); ilk sağlayıcılar: Sentinel-2 (Copernicus, ücretsiz, varsayılan) + Planet + yüksek çözünürlük tasking yuvası (Integration Center'a bağlı, anahtar girilince aktif); parsel geometrisine göre periyodik NDVI/NDMI hesaplama ve zaman serisi saklama (`parcel_index_series` koleksiyonu); görüntü metadata etiketi (kaynak/tarih/çözünürlük/bulut oranı); bulutlu kare eleme; `extras.py`'deki simüle NDVI bu gerçek boru hattına geçer, demo modu fallback kalır | IT-17, IT-32 (önerilir) |
| **IT-28.2** | **Parsel Analitiği:** Parsel Sağlık Skoru (haftalık, trendli); anomali alt-bölge tespiti (koordinatlı poligon + haritada kırmızı alert); ekili/boş tespiti + kooperatif "beyan-gerçek" listesi; fenoloji kütüphanesi (ürün bazlı NDVI eğri şablonları, admin yönetir) ile ürün doğrulama + ekim/çıkış tarihi tespiti; NDMI su stresi uyarısı; komşu kıyas (aynı köy + aynı ürün benchmark); hasat zamanı + verim tahmini (NDVI eğrisi + geçmiş kantar regresyonu, kota-gerçekleşme öngörüsü); parsel detayında zaman makinesi slider gerçek seriye bağlanır | IT-28.1 |
| **IT-28.3** | **Vision AI + Bilgi Kütüphaneleri:** Yönetilebilir hastalık/zararlı kütüphanesi (belirti, foto örnekleri, öneri; admin günceller); foto teşhis akışı: drone ortofoto importu (parsele bağlama + anomali bölgesinde yüksek çözünürlük inceleme) ve çiftçi portalı/mobil foto-teşhis kanalı (AI ön teşhis + güven skoru, kritikse mühendise eskalasyon); görüntü destekli gübre önerisi (VRA): toprak analizi + NDVI/NDMI zon haritası birleşimi → parsel içi 2-3 uygulama zonu + zon bazlı doz önerisi + yazdırılabilir reçete; su stresi zonunda "önce sulama" kuralı. AI çağrıları Integration Hub AI provider'ı üzerinden | IT-28.2, IT-04 |
| **IT-28.4** | **Alert→Aksiyon Zinciri + Sezon Karnesi:** Anomali/stres/hastalık tespitlerinde otomatik zincir: çiftçiye + sorumlu personele bildirim (Comm Hub) ve otomatik saha görevi (Sprint 8 kural motoru); alert yaşam döngüsü (yeni→incelemede→doğrulandı/yanlış alarm→kapandı, yanlış alarm geri bildirimi eşik ayarına döner); Sezon Karnesi (parsel bazlı otomatik PDF: sağlık eğrisi, olaylar, müdahaleler, verim vs. tahmin; kooperatife karşılaştırmalı tablo); AI Copilot'a parsel bağlamı (gerçek NDVI/alert verisiyle soru-cevap) | IT-28.3, IT-27, IT-24 |

> Not: Uydu sağlayıcı hesap açılışları (Copernicus/Planet) kullanıcının
> sorumluluğunda — anahtarlar Integration Center'dan girilecek, kod
> anahtar yokken demo moduyla çalışacak.

### FAZ 10 — Sprint 10 (Farmer LMS)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-29** | Eğitim kataloğu + içerik yönetimi (video/pdf/link, sıralı) + atama (kullanıcı/rol/segment/bölge) + durum takibi + zorunlu eğitim | IT-07, IT-09 |
| **IT-30** | Quiz (3 soru tipi) + otomatik **PDF sertifika** (doğrulama kodlu) + **Learning Path** + kişi kartı Eğitimler sekmesi | IT-29 |
| **IT-31** | **Uzman Desteği** (eğitim içinden soru→uzman ataması→mesajlaşma, Comm Hub üstünde) + FAQ havuzu + eğitim analitiği + LMS dashboard | IT-30, IT-28 |

### FAZ 11 — Sprint 11 kalanı (Platform Core)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-32** | **Integration Hub formalizasyonu:** tüm dış çağrılar tek modülden (extras'taki simüle servisler provider pattern'e taşınır) + Webhook Engine (event→dış URL) | IT-27 |
| **IT-33** | Feature Flags (tenant bazlı) + Module Manifest (menü/yetki/API tanımı) + Licensing iskeleti + **Health Center** ekranı + cache soyutlaması | IT-32 |

### FAZ 12 — Sprint 12 (Mobil)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-34** | **Experience Profile** modeli (backend: profil tanımı, widget/menü/hızlı işlem atamaları, kullanıcıya profil bağlama) | IT-33 |
| **IT-35** | Karar + uygulama: **PWA yolu** (önerilen) → görev odaklı mobil dashboard, offline temel (service worker + kuyruk), kamera/GPS web API'leri; **veya** Flutter iskeleti (test edilemez, kullanıcı derler) | IT-34 |

> Not: IT-35 sonrası kalan mobil özellikler (dijital imza, barkod, derin
> offline senkron) ihtiyaca göre IT-36+ olarak açılır — bkz. FAZ 13.

### FAZ 13 — Mobil Rol Tabanlı Görev & Self-Servis Ekosistemi (2026-07-11 eklendi)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-36** ✅ | Saha personeli görev yaşam döngüsü tam mobil ekranı (kabul/red/yolda/ulaştı/çalışıyor/tamamlandı + checklist+medya, offline kuyruk) | IT-22/23, IT-35 |
| **IT-37** ✅ | Ziraat mühendisi saha formları (M18) mobilden doldurma, görev bağlamından otomatik parsel/çiftçi | forms_module.py, IT-36 |
| **IT-38** ✅ (4/7 akış) | Çiftçi mobil self-servis genişletmesi: sulama girişi, uydu görüntüsü, finansal özet, ziyaret onaylama YAPILDI — sözleşme onaylama/ekim planlama/randevu alma veri modeli kararı gerektirdiği için ERTELENDİ | IT-34, IT-35 |
| **IT-39** ✅ | QR kod tabanlı teslim-tesellüm (support.py'nin eksik `qr_kod` onay yöntemini tamamlar — gerçek barkod yerine 6 haneli kod) | IT-18 |

### FAZ 14 — UX Tutarlılık Kuralları + Menü/Rapor Konsolidasyonu (2026-07-11 eklendi)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-40** | Genel tasarım kuralları (convention #11-14: serbest metin yasağı, filtre satırı genişlik sınırı, overlay kontrol paneli, kalıp uyumu) + FilterPanel/Zaman Makinesi somut düzeltmesi | — |
| **IT-41** | "Raporlar" menü konsolidasyonu (tüm SmartDataGrid/rapor ekranları tek sidebar grubunda, kendi filtreleri korunur) | IT-11 |

### FAZ 15 — Organizasyon Hiyerarşisi + Onay Zincirleri (2026-07-11 eklendi)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-42** ✅ | Organizasyon birimi (OrgUnit) + yönetici ağacı (`manager_id`) veri modeli, manager-chain sorgusu, OrganizationChart.jsx — `organization.py` + `OrganizationChart.jsx` (2026-07-11) | IT-07 |
| **IT-43** ✅ | Onay zincirleri/approval routing — mevcut durum makinelerine opsiyonel yönetici-onayı adımı (`approval.py` ortak yardımcı) — support.py + campaigns.py'ye entegre, `PendingApprovals.jsx` (2026-07-11) | IT-42 |

### FAZ 16 — GodMode + Platform Operasyon Konsolu (2026-07-11 eklendi)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-44** | GodMode kimlik doğrulama — sabit e-posta + gerçek TOTP (RFC 6238), ayrı `godmode_token`, rate limiting | IT-01 |
| **IT-45** | GodMode operasyon ekranı — sunucu sağlığı/kaynak izleme/restart, entegrasyon ekleme, tenant modül yönetimi, süper admin atama, tema/menü override, global audit/feature-flag, impersonation | IT-44, IT-33 |

### FAZ 17 — Bize Ulaşın (2026-07-11 eklendi — IT-28'i gerçekleştirir)
| ID | Kapsam | Bağımlılık |
|---|---|---|
| **IT-46** ✅ | IT-28'in Case modelini gerçekleştirir + web/mobil "Bize Ulaşın" yönlendirilmiş giriş noktası + otomatik platform_admin atamalı "Hata Bildirimi" kategorisi — `case_management.py` + `CaseManagement.jsx` (2026-07-11, platform_admin otomatik atama HENÜZ eklenmedi — bkz. bilinen borç) | IT-28 |

## D. Oturum Çalışma Sözleşmesi

1. Kullanıcı iş atar: örn. **"IT-05'i yap"**. Kapsam belirsizse Claude
   oturum başında en fazla 1-2 soru sorar, sonra uygulamaya geçer.
2. Her iterasyon tek oturumda biter; bitmezse kalan kısım aynı ID ile
   "devam" olarak işaretlenir ve bir sonraki oturumda tamamlanır.
3. Her oturum sonunda: syntax doğrulaması → tam proje zip'i
   (`dijital-tarim-ITxx.zip`) → değişen dosya raporu → CLAUDE.md ve
   ROADMAP.md durum güncellemesi.
4. Sıra esnek: kullanıcı bağımlılığı sağlanmış herhangi bir IT'yi öne
   çekebilir; bağımlılığı eksikse Claude uyarır.
5. Mevcut mimari korunur; gereksiz refactoring yapılmaz; her modül
   RBAC + Audit + (kurulduktan sonra) Query Engine ve Event Bus'a bağlanır.

## E. Durum Panosu

| Faz | İterasyonlar | Durum |
|---|---|---|
| Sprint 1–4d (miras) | — | ✅ |
| Sprint A1 Faz 1–2 | — | ✅ (Çiftçi pilotu) |
| FAZ 0 | IT-01 ✅ · IT-01.5 ✅ | ✅ |
| FAZ 1 | IT-02 ✅ · IT-03 ✅ · IT-04 ✅ | ✅ |
| FAZ 2 | IT-05 ✅ · IT-06 ✅ | ✅ |
| FAZ 3 | IT-07 ✅ | ✅ |
| FAZ 4 | IT-08 ✅ · IT-09 ✅ · IT-10 ✅ | ✅ |
| FAZ 5 | IT-11 ✅ · IT-12 ✅ · IT-13 ✅ | ✅ |
| FAZ 5.5 | IT-13.5 ✅ · IT-13.6 ✅ | ✅ |
| FAZ 6 | IT-14 ✅ · IT-15 ✅ · IT-16 ✅ · IT-17 ✅ | ✅ |
| FAZ 7 | IT-18 ✅ · IT-19 ✅ · IT-20 ✅ · IT-21 ✅ | ✅ |
| FAZ 8 | IT-22 ✅ · IT-23 ✅ · IT-24 ✅ | ✅ |
| FAZ 9 | IT-25 · IT-26 · IT-27 · IT-28 | ⬜ |
| FAZ 9.5 | IT-28.1 🔄 (provider katmanı — Sentinel Hub/NASA FIRMS/UP42 — 2026-07-11'de kuruldu; periyodik ingestion + `parcel_index_series` HENÜZ yok) · IT-28.2 · IT-28.3 · IT-28.4 | 🔄 |
| FAZ 10 | IT-29 · IT-30 · IT-31 | ⬜ |
| FAZ 11 | IT-32 · IT-33 | ⬜ |
| FAZ 12 | IT-34 · IT-35 | ⬜ |
| FAZ 13 | IT-36 ✅ · IT-37 ✅ · IT-38 ✅ (4/7 akış) · IT-39 ✅ | ✅ |
| FAZ 14 | IT-40 · IT-41 | ⬜ |
| FAZ 15 | IT-42 ✅ · IT-43 ✅ | ✅ (IT-07b — organization.py + approval.py olarak uygulandı) |
| FAZ 16 | IT-44 · IT-45 | ⬜ |
| FAZ 17 | IT-46 ✅ | ✅ (IT-28 — case_management.py, "Bize Ulaşın") |
| FAZ 18 | IT-47 · IT-48 · IT-49 · IT-50 · IT-51 · IT-52 · IT-53 | ⬜ (Agricultural Intelligence Engine — plan hazır, `AI-VIZYON-PLATFORMU-MIMARI.md` + ROADMAP-DETAY-TAM.md'ye eklendi 2026-07-11; DB/kuyruk kararı: Mongo+in-process, menü kararı: Ayarlar altı alt-grup — henüz KOD YAZILMADI) |
