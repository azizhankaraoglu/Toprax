/**
 * TabSIS PWA — Service Worker (IT-35 / FAZ 12)
 *
 * BİLİNÇLİ OLARAK basit: sadece app-shell'i (statik build çıktısı)
 * cache'ler, offline'ken navigasyonun boş bir tarayıcı hatası yerine
 * son yüklenen uygulamayı göstermesini sağlar. Gerçek veri senkronu
 * (`/api/*` istekleri) BURADA YAPILMAZ — `src/lib/offlineQueue.js`
 * (IndexedDB, sayfa seviyesi) o işi görür; Background Sync API
 * BİLİNÇLİ OLARAK kullanılmadı (tarayıcı desteği tutarsız + HTTPS
 * gerektirir, bkz. offlineQueue.js docstring'i).
 */
const CACHE_NAME = "tabsis-shell-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(["/", "/manifest.json", "/icon.svg"]).catch(() => {}))
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  // API çağrılarına ASLA müdahale etme — offlineQueue.js kendi mantığını yönetir.
  if (request.url.includes("/api/")) return;
  if (request.method !== "GET") return;

  event.respondWith(
    fetch(request)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
        return resp;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match("/")))
  );
});
