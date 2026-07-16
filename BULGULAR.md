# BULGULAR.md — TOPRAX Stabilizasyon Test Sonuçları

**Başlangıç Tarihi:** 2026-07-16
**Planlanan:** STAB-00..23 (FAZ S0..S4)
**Mevcut Durum:** STAB-00 ✅ | STAB-01 ✅ | STAB-02 🔄 (code scan) | STAB-B1..B3 ⏳

---

## STAB-00: Tek Kaynak Konsolidasyonu

**Durum:** ✅ TAMAMLANDI

### Bulgular
- Git status temiz (147 dosya commit'lendi)
- `.gitignore` güncellemesi: `*.txt`, `*.docx` temp files hariç tutuluyor
- Master branch'inde, commit history net

---

## STAB-01: Docker/Ortam Sabitleme

**Durum:** ✅ TAMAMLANDI

### Bulgular
| Kontrol | Sonuç | Not |
|---------|-------|-----|
| docker-compose.yml | ✅ | mongo_data volume tutarlı, named volume |
| Root `.env` | ✅ | Production values set, .gitignore'da exclude |
| backend/.env | ✅ | Yok (gerek yok, root .env yeterli) |
| frontend/.env | ✅ | Yok (gerek yok, root .env yeterli) |
| README.md | ✅ | .env setup section eklendi |

**Accepted:** docker compose up -d AYNI volume'a bağlanıyor, .env kullanımı documented.

---

## STAB-02: Memory↔Kod Tutarlılık Denetimi

**Durum:** 🔄 DEVAM EDIYOR (partial — code existence verified)

### Tarama Yöntemi
- CLAUDE.md IT-01..53 listelenmiş
- Backend/Frontend modules code existence check
- 3 kritik bug module'lerinde yapı kontrol edilmiş

### Bulgular (İlk Tarama)

#### ✅ Kod Var — Yapı Doğru
| IT | Modul | Endpoint/Component | Durum |
|----|----- |------------------|-------|
| IT-13.6 | admin_areas.py | `/admin-areas/bulk-import` | ✅ POST endpoint exists |
| IT-15/16 | MapDrawTools.jsx | Polygon/Rectangle/Circle | ✅ Drawing modes implemented |
| IT-16 | geo_import.py | Properties extraction | ✅ All formats (GeoJSON/KML/SHP/DXF) extract properties |
| IT-16 | GeoFileImport.jsx | Properties preview | ✅ UI shows properties with TKGM mapping |

#### ⚠️ Fonksiyonellik Doğrulanmadı (Test Gerekli)
3 kritik bug şüphesi:
1. **STAB-B1:** `/admin-areas/bulk-import` gerçekten çalışıyor mu? (real SHP/GeoJSON ile test lazım)
2. **STAB-B2:** Properties extraction complete mi? (All attributes returned mi?)
3. **STAB-B3:** MapDrawTools polygon select gerçekten intersection mi yapıyor? (Not bounding-box)

### Sonraki Adım
STAB-B1/B2/B3 ile **real testing** yapılacak (user-provided data gerekli).

---

## STAB-B1: İdari Alan (İlçe) Sınır Verisi Yükleme Hatası

**Durum:** ⏳ Beklemede — User data gerekli

**Test Planı:**
1. `POST /admin-areas/bulk-import` ile real SHP/GeoJSON upload
2. Hata varsa: error message + stack trace
3. Sonuç: dosya haritada görünüyor mu?

**Gerekli Verilar:** Real SHP (.shp+.shx+.dbf) veya GeoJSON, il/ilçe sınırı

---

## STAB-B2: Geo Dosya İçe Aktarımında Öznitelik Eksikliği

**Durum:** ⏳ Beklemede — User data gerekli

**Test Planı:**
1. `POST /geo-import/parse` ile parsel GeoJSON test
2. Response'ta tüm properties included mi?
3. Frontend preview'de attributes visible mi?
4. Auto-match TKGM fields working mi?

**Gerekli Verilar:** Real parsel GeoJSON (TKGM'den)

---

## STAB-B3: Çoklu Parsel Seçimi ("Şekille Seç") Çalışmıyor

**Durum:** ⏳ Beklemede — User data + browser test gerekli

**Test Planı:**
1. HaritaPaneli.jsx + MapDrawTools ile polygon draw
2. Bounding-box mı, yoksa real intersection mi?
3. Bilinen 3 parsel alanında tam 3 parsel seçiliyor mu?

**Gerekli Verilar:** 3 test parsel coordinate

---

## STAB-03: MD Dosyaları Konsolidasyonu

**Durum:** ⏳ Beklemede

---

## Özet Durum

| STAB | Tema | Durum |
|------|------|-------|
| STAB-00 | Tek Kaynak Konsolidasyonu | ✅ |
| STAB-01 | Docker/Ortam Sabitleme | ✅ |
| STAB-02 | Memory↔Kod Doğrulama | 🟡 (partial — real test beklemede) |
| STAB-03 | MD Konsolidasyonu | ⏳ |
| STAB-B1 | Admin Areas Upload Bug | ⏳ (user data) |
| STAB-B2 | Geo Properties Bug | ⏳ (user data) |
| STAB-B3 | Multi-Parcel Select Bug | ⏳ (user data) |

---

## Sonraki Adımlar

1. **User'dan veri iste:**
   - Real SHP/GeoJSON (il/ilçe sınırı)
   - Real parsel GeoJSON
   - 3 test parsel coordinate

2. **STAB-B1/B2/B3 test et** (real data ile)

3. **Bulguları dokümante et** — bu dosyaya ek

4. **STAB-03 (MD Konsolidasyonu) başla**

---

**Oluşturan:** Claude Code  
**Son Güncelleme:** 2026-07-16
