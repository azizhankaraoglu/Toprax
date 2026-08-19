/**
 * Toprax PWA — Service Worker (IT-35 / FAZ 12)
 *
 * BİLİNÇLİ OLARAK basit: sadece app-shell'i (statik build çıktısı)
 * cache'ler, offline'ken navigasyonun boş bir tarayıcı hatası yerine
 * son yüklenen uygulamayı göstermesini sağlar. Gerçek veri senkronu
 * (`/api/*` istekleri) BURADA YAPILMAZ — `src/lib/offlineQueue.js`
 * (IndexedDB, sayfa seviyesi) o işi görür; Background Sync API
 * BİLİNÇLİ OLARAK kullanılmadı (tarayıcı desteği tutarsız + HTTPS
 * gerektirir, bkz. offlineQueue.js docstring'i).
 */
// ⚠️ Sürüm numarası HER YENİ BUILD'de artırılır. Eski cache'i etkisiz
// kılmanın tek güvenli yolu budur; aksi halde yeni index.html eski
// (artık var olmayan) chunk dosyalarını isteyebilir.
const CACHE_NAME = "toprax-shell-v2";

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

  // ⚠️ 2026-08-19 — GERÇEK HATA DÜZELTMESİ.
  //
  // Eski hâlde her başarısız istek `caches.match("/")` ile index.html'e
  // düşüyordu. Bu, NAVİGASYON için doğru (offline'da uygulamayı göster),
  // ama bir JS/CSS parçası (chunk) istendiğinde FELAKET: tarayıcıya
  // "script" beklerken HTML dönüyor, konsolda "An unknown error occurred
  // when fetching the script" çıkıyor ve uygulama YARIM yükleniyor —
  // ekranda "l is not a function" gibi anlamsız hatalar olarak görünüyor
  // (canlıda Dashboard/AI ekranlarında bildirildi; sayfa yenileyince
  // düzelmesinin sebebi de buydu).
  //
  // Yeni davranış: HTML yedeği YALNIZCA navigasyon isteklerinde verilir;
  // diğerleri ya kendi cache kopyasını alır ya da dürüstçe başarısız olur.
  const isNavigation = request.mode === "navigate";

  event.respondWith(
    fetch(request)
      .then((resp) => {
        // Yalnızca başarılı ve aynı-köken yanıtlar cache'lenir; hatalı bir
        // yanıtı (404/500) cache'lemek hatayı kalıcı hale getirirdi.
        if (resp && resp.ok && new URL(request.url).origin === self.location.origin) {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
        }
        return resp;
      })
      .catch(() =>
        caches.match(request).then((cached) => {
          if (cached) return cached;
          if (isNavigation) return caches.match("/");
          // Chunk/asset isteğinde HTML DÖNDÜRME — gerçek hata daha iyidir.
          return Response.error();
        })
      )
  );
});
