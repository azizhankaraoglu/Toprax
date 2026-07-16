// Global Color Constants - Kullanıcı tüm projede tutarlı renkler için
export const COLORS = {
  // Primary - Turuncu (Ana marka rengi)
  primary: '#FF8C00',
  primaryDark: '#E67E00',
  primaryLight: '#FFB84D',

  // Semantic Colors
  success: '#10B981',    // Yeşil - başarı, pozitif durumlar
  danger: '#EF4444',     // Kırmızı - uyarı, hata, riskli
  warning: '#F59E0B',    // Sarı - dikkat, uyarı
  info: '#3B82F6',       // Mavi - bilgi, nötr durumlar

  // Neutral/Background
  bg: '#0f0f0f',         // Koyu arka plan
  surface: '#1a1a1a',    // Card/panel arka plan
  surface2: '#242424',   // Input/nested surface
  border: '#363636',     // Border renkler

  // Text
  text: '#f0f0f0',       // Primer metin
  textDim: '#a8a8a8',    // İkincil metin

  // Orange palette (Tailwind uyumlu)
  orange: {
    50: '#FFF7ED',
    100: '#FFEDD5',
    200: '#FED7AA',
    300: '#FDBA74',
    400: '#FB923C',
    500: '#FF8C00',
    600: '#EA580C',
    700: '#C2410C',
    800: '#9A3412',
    900: '#7C2D12',
  },

  // Success palette
  successPalette: {
    50: '#F0FDF4',
    100: '#DCFCE7',
    200: '#BBF7D0',
    300: '#86EFAC',
    400: '#4ADE80',
    500: '#10B981',
    600: '#059669',
    700: '#047857',
    800: '#065F46',
    900: '#064E3B',
  },

  // Warning palette
  warningPalette: {
    50: '#FFFBEB',
    100: '#FEF3C7',
    200: '#FDE68A',
    300: '#FCD34D',
    400: '#FBBF24',
    500: '#F59E0B',
    600: '#D97706',
    700: '#B45309',
    800: '#92400E',
    900: '#78350F',
  },

  // Info palette
  infoPalette: {
    50: '#EFF6FF',
    100: '#DBEAFE',
    200: '#BFDBFE',
    300: '#93C5FD',
    400: '#60A5FA',
    500: '#3B82F6',
    600: '#2563EB',
    700: '#1D4ED8',
    800: '#1E40AF',
    900: '#1E3A8A',
  },

  // Danger palette
  dangerPalette: {
    50: '#FEF2F2',
    100: '#FEE2E2',
    200: '#FECACA',
    300: '#FCA5A5',
    400: '#F87171',
    500: '#EF4444',
    600: '#DC2626',
    700: '#B91C1C',
    800: '#991B1B',
    900: '#7F1D1D',
  },
};

// Status-to-Color mapping
export const STATUS_COLORS = {
  // Support Request statuses
  taslak: { bg: 'rgba(255, 140, 0, 0.15)', color: '#FF8C00', label: 'Taslak' },
  gonderildi: { bg: 'rgba(59, 130, 246, 0.15)', color: '#3B82F6', label: 'Gönderildi' },
  inceleniyor: { bg: 'rgba(59, 130, 246, 0.15)', color: '#3B82F6', label: 'İnceleniyor' },
  onaylandi: { bg: 'rgba(16, 185, 129, 0.15)', color: '#10B981', label: 'Onaylandı' },
  hazirlaniyor: { bg: 'rgba(255, 140, 0, 0.15)', color: '#FF8C00', label: 'Hazırlanıyor' },
  teslim_edildi: { bg: 'rgba(245, 158, 11, 0.15)', color: '#F59E0B', label: 'Teslim Edildi' },
  ciftci_onayladi: { bg: 'rgba(16, 185, 129, 0.15)', color: '#10B981', label: 'Çiftçi Onayladı' },
  muhasebelesti: { bg: 'rgba(16, 185, 129, 0.15)', color: '#10B981', label: 'Muhasebeleşti' },
  tamamlandi: { bg: 'rgba(16, 185, 129, 0.15)', color: '#10B981', label: 'Tamamlandı' },
  reddedildi: { bg: 'rgba(239, 68, 68, 0.15)', color: '#EF4444', label: 'Reddedildi' },
  iptal_edildi: { bg: 'rgba(239, 68, 68, 0.15)', color: '#EF4444', label: 'İptal Edildi' },

  // Field Task statuses
  planlandi: { bg: 'rgba(255, 140, 0, 0.15)', color: '#FF8C00', label: 'Planlandı' },
  atandi: { bg: 'rgba(59, 130, 246, 0.15)', color: '#3B82F6', label: 'Atandı' },
  kabul_edildi: { bg: 'rgba(16, 185, 129, 0.15)', color: '#10B981', label: 'Kabul Edildi' },
  yola_cikildi: { bg: 'rgba(59, 130, 246, 0.15)', color: '#3B82F6', label: 'Yola Çıkıldı' },
  yerine_ulasildi: { bg: 'rgba(245, 158, 11, 0.15)', color: '#F59E0B', label: 'Yerine Ulaşıldı' },
  calisiliyor: { bg: 'rgba(245, 158, 11, 0.15)', color: '#F59E0B', label: 'Çalışılıyor' },
  onay_bekliyor: { bg: 'rgba(245, 158, 11, 0.15)', color: '#F59E0B', label: 'Onay Bekliyor' },
  kapandi: { bg: 'rgba(16, 185, 129, 0.15)', color: '#10B981', label: 'Kapalı' },
};

// Badge type to Color mapping
export const BADGE_COLORS = {
  a: { bg: 'rgba(255, 140, 0, 0.15)', color: '#FF8C00' },   // Turuncu
  b: { bg: 'rgba(16, 185, 129, 0.15)', color: '#10B981' },   // Yeşil
  c: { bg: 'rgba(245, 158, 11, 0.15)', color: '#F59E0B' },   // Sarı
  d: { bg: 'rgba(239, 68, 68, 0.15)', color: '#EF4444' },    // Kırmızı
  neutral: { bg: 'rgba(151, 168, 160, 0.15)', color: '#a8a8a8' },
};

// Risk level colors
export const RISK_COLORS = {
  dusuk: { color: '#10B981', label: 'Düşük Risk', intensity: 1 },
  orta: { color: '#F59E0B', label: 'Orta Risk', intensity: 2 },
  yuksek: { color: '#EF4444', label: 'Yüksek Risk', intensity: 3 },
  kritik: { color: '#7C2D12', label: 'Kritik Risk', intensity: 4 },
};

// Health status colors
export const HEALTH_COLORS = {
  excellent: { color: '#10B981', label: 'Mükemmel', intensity: 5 },
  good: { color: '#86EFAC', label: 'İyi', intensity: 4 },
  fair: { color: '#F59E0B', label: 'Orta', intensity: 3 },
  poor: { color: '#FB923C', label: 'Zayıf', intensity: 2 },
  critical: { color: '#EF4444', label: 'Kritik', intensity: 1 },
};
