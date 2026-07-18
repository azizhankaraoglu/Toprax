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
