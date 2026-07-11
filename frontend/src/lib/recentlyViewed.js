/**
 * IT-12 — "Son Açılanlar" (Recently Opened). Sunucu tarafı gerektirmeyen,
 * saf istemci tarafı bir kolaylık — mevcut kod zaten auth token'ı
 * localStorage'da tutuyor (bkz. api.js), burada aynı deseni izliyoruz.
 * Cihazlar arası senkron OLMAZ (bilinçli — bu veri kritik değil, sadece
 * "az önce baktığım kayıtlara hızlı dönüş" kolaylığı).
 */
const KEY = "tabsis_recently_viewed";
const MAX_ITEMS = 10;

export function getRecentlyViewed() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

export function pushRecentlyViewed({ module, id, label, path }) {
  const list = getRecentlyViewed().filter((it) => !(it.module === module && it.id === id));
  list.unshift({ module, id, label, path, viewedAt: new Date().toISOString() });
  localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX_ITEMS)));
}
