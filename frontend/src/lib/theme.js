/**
 * SON HAL — Tema yönetimi (aydınlık/koyu). VARSAYILAN: AYDINLIK.
 *
 * CSS değişkenleri index.css'te `:root` (koyu) ve `:root[data-theme="light"]`
 * (aydınlık) olarak tanımlı; burada sadece <html> elemanına data-theme
 * attribute'u basılır. Tercih localStorage("toprax_theme")'de saklanır
 * (mevcut token/nav-open desenleriyle aynı).
 *
 * Harita tile'ları CSS değişkeni OKUYAMAZ — sayfalar `getBasemapUrl()` ile
 * temaya uygun tile URL'i alır. Tile'lar sadece harita mount olurken
 * yüklendiği için tema değişimi `setTheme()` içinde tam sayfa yenilemeyle
 * uygulanır (HaritaPaneli'nin ?snapshot= tam-yenileme emsali).
 */
const KEY = "toprax_theme";

export function getTheme() {
  try {
    const t = localStorage.getItem(KEY);
    return t === "dark" ? "dark" : "light";          // varsayılan: AYDINLIK
  } catch {
    return "light";
  }
}

export function applyTheme() {
  document.documentElement.dataset.theme = getTheme();
}

export function setTheme(theme, { reload = true } = {}) {
  try { localStorage.setItem(KEY, theme === "dark" ? "dark" : "light"); } catch {}
  applyTheme();
  // Harita tile'ları + recharts renkleri mount'ta okunur — tutarlılık için
  // tam yenileme (birkaç yüz ms, tercih değişikliği nadir bir işlem).
  if (reload) window.location.reload();
}

export function getBasemapUrl() {
  return getTheme() === "dark"
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
}

/**
 * SON HAL #10 — Kullanıcı renk bloğu (accent) seçimi.
 *
 * "Kendi renk tasarımını seçsin, tüm yapı o renk bloğuna göre ayarlansın,
 * her girişinde kendi seçtiği renk bloğu gelsin" isteği. Aydınlık/koyu
 * tema (yukarısı) ZEMİN'i değiştirir; bu ise MARKA rengini (--primary/
 * --primary-dark/--primary-light/--accent) değiştirir — ikisi bağımsızdır,
 * her ikisi de aynı anda uygulanır.
 *
 * Uygulama: index.css'teki :root / :root[data-theme] kuralları CSS
 * seviyesinde tanımlı; burada sadece <html> elemanına aynı adlı CSS
 * DEĞİŞKENLERİ inline `style` ile EZİLEREK basılır (Tailwind sınıfları
 * hep var(--primary) okuduğu için kaynak dosyalarda hiçbir değişiklik
 * gerekmez). Varsayılan "turuncu" seçiliyken inline override temizlenir,
 * yani CSS'teki orijinal turuncu marka rengine geri dönülür.
 *
 * Kalıcılık: localStorage("toprax_accent") tema ile AYNI desen — anlık/
 * flaşsız açılış için. Sunucu tarafı: backend/users.py MyProfileUpdate.
 * accent_color alanı + GET /me/profile — böylece başka bir cihazda/
 * tarayıcıda giriş yapıldığında da (sadece bu tarayıcıya özel localStorage
 * değil) kullanıcının seçtiği blok otomatik uygulanır (bkz. Login.jsx).
 */
const ACCENT_KEY = "toprax_accent";

export const ACCENT_PRESETS = {
  turuncu: { label: "Turuncu (Varsayılan)", swatch: "#FF8C00" },
  mavi: {
    label: "Mavi", swatch: "#2563EB",
    light: { primary: "#2563EB", primaryDark: "#1D4ED8", primaryLight: "#60A5FA", accent: "#60A5FA" },
    dark: { primary: "#3B82F6", primaryDark: "#2563EB", primaryLight: "#93C5FD", accent: "#93C5FD" },
  },
  yesil: {
    label: "Yeşil", swatch: "#16A34A",
    light: { primary: "#16A34A", primaryDark: "#15803D", primaryLight: "#4ADE80", accent: "#4ADE80" },
    dark: { primary: "#22C55E", primaryDark: "#16A34A", primaryLight: "#86EFAC", accent: "#86EFAC" },
  },
  mor: {
    label: "Mor", swatch: "#7C3AED",
    light: { primary: "#7C3AED", primaryDark: "#6D28D9", primaryLight: "#A78BFA", accent: "#A78BFA" },
    dark: { primary: "#8B5CF6", primaryDark: "#7C3AED", primaryLight: "#C4B5FD", accent: "#C4B5FD" },
  },
  kirmizi: {
    label: "Kırmızı", swatch: "#DC2626",
    light: { primary: "#DC2626", primaryDark: "#B91C1C", primaryLight: "#F87171", accent: "#F87171" },
    dark: { primary: "#EF4444", primaryDark: "#DC2626", primaryLight: "#FCA5A5", accent: "#FCA5A5" },
  },
  lacivert: {
    label: "Lacivert", swatch: "#1E3A8A",
    light: { primary: "#1E3A8A", primaryDark: "#172554", primaryLight: "#3B82F6", accent: "#3B82F6" },
    dark: { primary: "#1E40AF", primaryDark: "#1E3A8A", primaryLight: "#60A5FA", accent: "#60A5FA" },
  },
};

export function getAccent() {
  try {
    const a = localStorage.getItem(ACCENT_KEY);
    return a && ACCENT_PRESETS[a] ? a : "turuncu";
  } catch {
    return "turuncu";
  }
}

export function applyAccent(accentKey) {
  const key = accentKey && ACCENT_PRESETS[accentKey] ? accentKey : getAccent();
  const preset = ACCENT_PRESETS[key];
  const mode = getTheme();
  const root = document.documentElement;
  if (key === "turuncu" || !preset[mode]) {
    root.style.removeProperty("--primary");
    root.style.removeProperty("--primary-dark");
    root.style.removeProperty("--primary-light");
    root.style.removeProperty("--accent");
    return;
  }
  const c = preset[mode];
  root.style.setProperty("--primary", c.primary);
  root.style.setProperty("--primary-dark", c.primaryDark);
  root.style.setProperty("--primary-light", c.primaryLight);
  root.style.setProperty("--accent", c.accent);
}

// key: null/"turuncu" verilirse varsayılana döner. persist=false ise sadece
// bu oturumda anlık uygulanır, localStorage'a yazılmaz (ör. sunucudan gelen
// değeri cihaza senkronlarken zaten setAccent kullanılıyor olur).
export function setAccent(accentKey) {
  const key = accentKey && ACCENT_PRESETS[accentKey] ? accentKey : "turuncu";
  try { localStorage.setItem(ACCENT_KEY, key); } catch {}
  applyAccent(key);
}
