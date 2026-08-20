/**
 * ORTAK BASEMAP (harita altlığı) KATALOĞU — 2026-08-19.
 *
 * Bu katalog önceden SADECE `pages/HaritaPaneli.jsx` içinde bir modül-içi
 * sabit olarak duruyordu; Parseller ekranı altlık seçemiyor, `lib/theme.js`'in
 * `getBasemapUrl()`'i ile temaya bağlı TEK bir koyu/açık altlığa mahkûm
 * kalıyordu. Kullanıcı Parseller haritasında da altlık seçimi isteyince
 * kataloğu KOPYALAMAK yerine buraya taşıdık (lib/moduleRoutes.js'in
 * GlobalSearch + WorkspaceDrawer arasında paylaşılmasıyla AYNI kalıp).
 *
 * Hepsi anahtarsız/ücretsiz genel XYZ servisleridir. "Uydu" burada gerçek
 * NDVI/Sentinel verisi DEĞİL, yalnızca Esri'nin genel ortofoto altlığıdır —
 * Uzaktan Algılama modülüyle KARIŞTIRILMAMALI.
 */
export const BASEMAPS = {
  dark: {
    label: "Koyu",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap &copy; CARTO",
  },
  light: {
    label: "Açık",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap &copy; CARTO",
  },
  streets: {
    label: "Sokak",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap katkıcıları",
  },
  satellite: {
    label: "Uydu",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri",
  },
  // Hibrit = uydu ortofoto + yer adı/sınır etiket overlay'i (ikinci TileLayer).
  hibrit: {
    label: "Hibrit",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    overlay: "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri",
  },
  topografik: {
    label: "Topografik",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenTopoMap (CC-BY-SA)",
  },
};

export const DEFAULT_BASEMAP = "hibrit";

/** Ekran başına altlık tercihi (cihaz yerel). Harita paneli kendi tercihini
 *  sunucudaki kişisel çalışma alanında tutar; diğer ekranlar için bu yeterli. */
export function getStoredBasemap(screenKey, fallback = DEFAULT_BASEMAP) {
  try {
    const v = localStorage.getItem(`toprax_basemap_${screenKey}`);
    return v && BASEMAPS[v] ? v : fallback;
  } catch {
    return fallback;
  }
}

export function storeBasemap(screenKey, key) {
  try { localStorage.setItem(`toprax_basemap_${screenKey}`, key); } catch { /* yoksay */ }
}
