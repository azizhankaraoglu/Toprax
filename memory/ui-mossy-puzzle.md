# TOPRAX UI/UX Tasarım Transformasyon Planı

## Context

TOPRAX tarımsal operasyon platformu şu anda koyu bir tema ile çalışıyor (dark mode, yeşil primary rengi #4ade80). Kullanıcı, gösterilen Toprax dashboard örneğinde gördüğü canlı, veri-yoğun tasarım dilini uygulamak istiyor.

**Hedef:** Mevcut tüm renk ve UI tasarımlarını yeni, canlı bir palettle (turuncu primary, yeşil success, kırmızı danger, mavi info) dönüştürmek. Tüm bileşenler, sayfalar ve bileşen kütüphaneleri tutarlı bir şekilde yeniden biçimlendirilecek.

**Kapsam:** Sadece planlama — kod yazılmayacak. Implementasyon adımlarını, kritik dosyaları, zamanlamayı ve testy stratejisini detaylandırıyoruz.

---

## 1. Renk Şeması Transformasyonu

### Mevcut Tema (Dark Mode)
```
--bg: #0a0f0d               (Çok koyu, neredeyse siyah)
--surface: #11181a          (Kartlar için hafif açık)
--border: #243038           (Kenarlar)
--primary: #4ade80          (Yeşil)
--accent: #fbbf24           (Sarı)
--danger: #ef4444           (Kırmızı)
```

### Hedef Tema (Canlı & Veri-Yoğun)
```
Temel Renkler:
  --primary: #FF8C00        (Turuncu — Enerji & Aksyon)
  --success: #10B981        (Yeşil — Başarı & Durum)
  --danger: #EF4444         (Kırmızı — Riskler)
  --warning: #F59E0B        (Sarı — Dikkat Gerektiren)
  --info: #3B82F6           (Mavi — Bilgi & Bağlantılar)
  --secondary: #8B5CF6      (Mor — Ek Vurgu)

Arka Plan Renkler:
  --bg: #0F172A             (Biraz daha mavi-gri, ama yine koyu)
  --surface: #1E293B        (Kartlar, biraz daha aydınlık)
  --surface-2: #334155      (Input'lar ve derinlik)
  --border: #475569         (Daha görünür sınırlar)

Metin:
  --text: #F1F5F9           (Daha açık, okunabilir)
  --text-dim: #CBD5E1       (Orta gri)
  --text-muted: #94A3B8     (Daha koyu gri)

Gradients (Vurgu için):
  linear-gradient(135deg, #FF8C00 0%, #FB923C 100%)  (Primary)
  linear-gradient(135deg, #10B981 0%, #34D399 100%)  (Success)
  linear-gradient(135deg, #EF4444 0%, #F87171 100%)  (Danger)
```

### Uygulama Dosyaları
- **`src/index.css`** — CSS variables güncellemesi (75 satır)
- **`tailwind.config.js`** — Yeni color palette eklenmesi (50 satır)
- **`src/constants/colors.js`** (YENİ) — Paylaşılan color constants (80 satır)

---

## 2. Bileşen Tasarımı Güncellemeleri

### 2.1 KPI Kartları
- Renk kodlu sol border (kategori bazlı)
- Gradient background (hafif turuncu)
- İkon + label + value (hiyerarşik)
- Trend göstergesi eklenmesi
- **Dosya:** `src/components/KPI.jsx` (refactor)

### 2.2 Badge Tasarımları (Renk Palet Genişletmesi)
- Mevcut: `badge-a/b/c/d`
- Hedef: 6 renk (turuncu, yeşil, kırmızı, sarı, mavi, mor)
- **Dosya:** `src/components/ui/badge.jsx` (update)

### 2.3 Button Varyasyonları
- Gradient active state
- Hover effects
- Ghost/outline variants
- **Dosya:** `src/components/ui/button.jsx` (update)

### 2.4 Input & Form Elements
- Focus state turuncu border + glow
- Placeholder renk ve visibility
- **Dosya:** `src/index.css` (update)

### 2.5 Card Varyasyonları
- Base card (surface background)
- Highlight card (turuncu border)
- Success card (yeşil sol border)
- Danger card (kırmızı sol border)
- **Dosya:** `src/index.css` (update)

---

## 3. Layout Refaktörü

### 3.1 Dashboard Yeni Yapısı
```
┌─────────────────────────────────────────┐
│ Header: Başlık + Tarih/Sezon            │
├─────────────────────────────────────────┤
│ [Weather] | [Critical Alerts]           │
├─────────────────────────────────────────┤
│ [KPI Grid — 4 kolon, renk kodlu]       │
├─────────────────────────────────────────┤
│ [Map + Overlays] (NDVI/Risk/Layer)     │
├─────────────────────────────────────────┤
│ [Trends] | [Risk] | [Transactions]     │
└─────────────────────────────────────────┘
```

### 3.2 Sidebar Güncellemeleri
- Turuncu active border + gradient bg
- Hover: daha parlak background
- Grup bazlı vurgu rengi
- **Dosya:** `src/components/Layout.jsx` (update)

---

## 4. Grafik & Harita Güncellemeleri

### 4.1 Recharts Renk Şeması
- LineChart: 3 trend (warning/success/info)
- BarChart: Kategori başına gradient
- PieChart: Yeni 5 renk rotasyonu
- **Dosya:** `src/constants/colors.js` → Recharts bileşenleri

### 4.2 Leaflet Harita Renklendirmesi
- Parsel renkleri: Risk seviyesine göre (kırmızı/sarı/yeşil/mavi)
- Marker colors: Status'a göre (turuncu/yeşil/sarı/kırmızı)
- **Dosya:** `src/components/MapStyles.js` (YENİ)

### 4.3 Tooltip & Legend
- Turuncu border + primary gradient bg
- Contrast doğrulanmış text
- **Dosya:** `src/index.css` (update)

---

## 5. İkon & Tipografi

### 5.1 İkon Renklendirmesi
- KPI kartları: Kategori başına renk
- Butonlar: Primary turuncu
- Widget'lar: Status-matched renk
- **Uygulama:** `components/` tüm JSX dosyaları (text-primary/text-success/etc)

### 5.2 Tipografi (Sabit — değişim YOK)
- Font stack: IBM Plex Sans (body), Fraunces (display)
- Size ve weight mevcut kalıbı takip ediyor
- Letter-spacing: Başlıklarda -0.02em tutulur

---

## 6. Responsive Design

### 6.1 Breakpoint Stratejisi
```
Mobile:   320px–640px   → 1 kolon (KPI stack)
Tablet:   640px–1024px  → 2 kolon
Desktop:  1024px+       → 4 kolon (full grid)
```

### 6.2 Mobil Adaptasyonlar
- Chart containers kompakt
- Harita full-width (sidebar overlay)
- Typography alanı korunur
- **Dosya:** Tüm CSS (media queries @media (max-width: ...))

---

## 7. Animasyonlar & Transitions

### 7.1 Mevcut Animasyonlar (Koruyunuz)
- Fade-in / pulse-dot
- Component mount/unmount transitions

### 7.2 Yeni Animasyonlar (Ekle)
- Card hover: `translateY(-4px)` + shadow
- Button press: `scale(0.96)`
- Alert slide-in: X'den sağa
- **Timing:** 150ms (hızlı), 300ms (normal), 500ms (yavaş)

---

## 8. Sayfa-Spesifik Tasarımlar

| Sayfa | Primary | Accent | Risk | Success |
|-------|---------|--------|------|---------|
| Dashboard | Turuncu | Mavi | Kırmızı | Yeşil |
| Farmers | Yeşil | Turuncu | Kırmızı | Mavi |
| Parcels | Mavi | Turuncu | Kırmızı | Yeşil |
| Finance | Turuncu | Sarı | Kırmızı | Yeşil |
| Operations | Mor | Turuncu | Kırmızı | Yeşil |

---

## 9. Testing Stratejisi

### 9.1 Görsel Regresyon
- **Tool:** Percy.io veya Chromatic
- **Scope:** Dashboard, Farmers, Parcels (P1)
- **Viewports:** 375px (mobile), 768px (tablet), 1440px (desktop)
- **Themes:** Dark mode + Light mode (future-proof)

### 9.2 Responsive Testing
- Mobil stacking ✓
- Text overflow yok ✓
- Touch-friendly (min 44px) ✓
- Harita interaktif ✓

### 9.3 Color Contrast Testing
- WCAG AA minimum (4.5:1 text, 3:1 graphics)
- **Tool:** WCAG Color Contrast Checker
- **Scope:** TÜM text + icon combinations

### 9.4 Chart & Map Testing
- Empty data gracefully
- Real-time updates
- Zoom/Pan operations
- Colorblind mode validation

---

## 10. Implementasyon Sırası & Zamanlamalar

### Phase 1: Foundation (1-2 gün) — CRITICAL
1. CSS variables güncellemesi (`src/index.css`)
2. Tailwind config genişletmesi
3. Global color constants dosyası oluştur
4. Badge/Button base styles update
- **Files:** `index.css`, `tailwind.config.js`, `constants/colors.js` (new)

### Phase 2: Component Updates (2-3 gün)
1. KPI Card refactor
2. Badge renkleri
3. Button varyasyonları
4. Input/Form field styling
- **Files:** `components/KPI.jsx`, `components/ui/badge.jsx`, `components/ui/button.jsx`

### Phase 3: Dashboard Overhaul (2 gün) — HIGH VISIBILITY
1. Layout restructuring
2. Header + Weather + Alerts
3. KPI grid renk kodlaması
4. Chart color updates (Recharts)
- **Files:** `pages/Dashboard.jsx`

### Phase 4: Map Pages (1-2 gün)
1. HaritaPaneli.jsx layout
2. Parcel color encoding (risk/NDVI)
3. Leaflet styles
- **Files:** `pages/HaritaPaneli.jsx`, `components/MapStyles.js` (new)

### Phase 5: Detail Pages (1-2 gün)
1. FarmerDetail.jsx
2. ParcelDetail.jsx
3. ProductionCycleDetail.jsx
- **Files:** Detail sayfaları

### Phase 6: Tables & Lists (1 gün)
1. SmartDataGrid color updates
2. Status badges
3. Row hover effects
- **Files:** `components/SmartDataGrid.jsx`

### Phase 7: Other Pages & Modals (1 gün)
1. Remaining pages
2. Modal dialogs
3. Drawer panels
- **Files:** `pages/`, `components/ui/`

### Phase 8: Polish (1 gün)
1. Mobile breakpoint tuning
2. Animation timing tweaks
3. Interaction polish
- **Files:** CSS files (media queries)

### Phase 9: Testing & QA (1-2 gün)
1. Visual regression tests
2. Responsive verification
3. Contrast audit
4. Performance check
- **Tools:** Percy, DevTools, Lighthouse

### Phase 10: Documentation (0.5 gün)
1. Color guide document
2. Component storybook comments
3. CSS naming conventions
4. Responsive breakpoint guide
- **Files:** `DESIGN_TOKENS.md` (new), `RESPONSIVE_GUIDE.md` (new)

**Total:** ~64 saatlik iş (~2 hafta, 1 kişi | ~1 hafta, 2 kişi | ~3-4 gün, 3 kişi)

---

## 11. Kritik Dosyalar (Priority Order)

### Foundation Files (Önce Bunları Yapın)
- `src/index.css` — CSS variables + base classes
- `tailwind.config.js` — Extended colors
- `src/constants/colors.js` (YENİ) — Constants

### Component Files (Hemen Sonra)
- `src/components/ui/badge.jsx`
- `src/components/ui/button.jsx`
- `src/components/KPI.jsx`

### Page Files (Sonra)
- `src/pages/Dashboard.jsx` (en görünür)
- `src/pages/HaritaPaneli.jsx` (karmaşık)
- `src/pages/FarmerDetail.jsx`
- `src/pages/ParcelDetail.jsx`

### Supporting Files
- `src/components/Layout.jsx` (nav colors)
- `src/components/SmartDataGrid.jsx` (table styling)
- `src/components/MapStyles.js` (YENİ)

---

## 12. Verification & Sign-Off

### Başarılı Uygulamanın Kontrol Listesi
- [ ] Renk paleti tüm sayfalarda tutarlı
- [ ] Tüm badges doğru renk gösteriyor
- [ ] Butonlar yeni gradients ile responsive
- [ ] KPI kartları drill-down functionality ile çalışıyor
- [ ] Dashboard layout hedef tasarımla eşleşiyor
- [ ] Haritalar doğru renk kodlaması ile render ediyor
- [ ] Grafikler güncellenmiş renk şemasını kullanıyor
- [ ] Mobil responsive 3+ cihazda test edildi
- [ ] Color contrast ≥4.5:1 tüm text'te
- [ ] Hiç görsel regression yoktur
- [ ] Tüm animasyonlar smooth ve performant
- [ ] Light mode desteği future-ready
- [ ] Tüm team belgeleri tamamlandı

---

## 13. Bilinçli Kapsam Dışında Bırakılanlar

1. **Backend değişiklikleri** — UI-only transformation
2. **Veri yapısı değişiklikleri** — Tasarım-only update
3. **Accessibility complete audit** — WCAG AA test edilecek ama kapsamlı reklassification yok
4. **Font değişimi** — Mevcut font stack korunur
5. **Yeni UI kütüphanesi** — Mevcut Radix UI + Tailwind devam eder

---

## Sonraki Adımlar (Onay Sonrası)

1. ✅ **Kullanıcı onayı** — Plan doğru mu?
2. 📝 **Sorular & Açıklamalar** — Herhangi bir netleştirme gerekli mi?
3. 🎨 **Implementasyon Başlangıcı** — Phase 1'den başla (Foundation)
4. 🧪 **Parallel Testing** — Her phase'den sonra visual regression test
5. 📊 **Weekly Check-in** — Progress & blockers review

---
