/**
 * Offline-First Kuyruk (IT-35 / FAZ 12 — Mobil PWA; Denetim Faz 8 —
 * idempotency anahtarı eklendi)
 *
 * ROADMAP'in "görev görüntüleme, form doldurma, fotoğraf çekme, konum
 * kaydı, not alma — internet geldiğinde otomatik senkron" senaryosu için.
 * BİLİNÇLİ OLARAK Service Worker Background Sync API KULLANILMADI —
 * o API'nin tarayıcı desteği tutarsız (Safari/Firefox'ta yok) ve HTTPS
 * gerektirir; bunun yerine Workbox'ın arka planda yaptığı ŞEYİN AYNISI
 * sayfa seviyesinde, dependency-free (yeni bir npm paketi YOK — Karar
 * Protokolü gereği) ham `indexedDB` API'siyle yapılıyor: istek başarısız
 * olursa (ağ hatası VEYA `navigator.onLine===false`) kuyruğa yazılır,
 * `window`'un `online` event'i VEYA sayfa açılışı bunu tekrar dener.
 *
 * Denetim Faz 8 — HER kuyruğa eklenen isteğe (`enqueue` çağrıldığı ANDA,
 * ilk deneme başarısız olduğunda) benzersiz bir `X-Idempotency-Key`
 * atanır ve `flush()`'ın HER tekrar denemesinde AYNI anahtar gönderilir.
 * İstek sunucuya ULAŞIP başarıyla işlendiği HALDE yanıt istemciye
 * dönmezse (bağlantı o anda koptuysa), backend (bkz. `backend/
 * idempotency.py`) aynı anahtarla gelen ikinci denemeye kaydedilmiş
 * yanıtı AYNEN döner — aynı ziyaret/numune/talep İKİ KEZ YAZILMAZ.
 *
 * Kullanım: enqueue({method, url, body}) → flush(apiClient) → getAll()
 */
export function makeIdempotencyKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  // Eski tarayıcı fallback'i (crypto.randomUUID her yerde yok) — rastgelelik
  // ihtiyacı sadece "aynı istek iki kez gönderilirse anahtarı aynı kalsın"
  // seviyesinde, kriptografik güç GEREKMEZ.
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
const DB_NAME = "toprax_offline";
const STORE = "queue";

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function enqueue(request) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).add({
      ...request, queued_at: new Date().toISOString(),
      idempotency_key: request.idempotency_key || makeIdempotencyKey(),
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAll() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function remove(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/**
 * Kuyruktaki HER isteği (sırayla, biri başarısız olsa da diğerlerini
 * dener) `apiClient` (axios instance) ile tekrar göndermeyi dener,
 * başarılı olanları kuyruktan siler. Kaç tanesinin gönderildiğini döner.
 */
export async function flush(apiClient) {
  const items = await getAll();
  let sent = 0;
  for (const item of items) {
    try {
      await apiClient({
        method: item.method, url: item.url, data: item.body,
        headers: item.idempotency_key ? { "X-Idempotency-Key": item.idempotency_key } : undefined,
      });
      await remove(item.id);
      sent += 1;
    } catch {
      // ağ hâlâ yok VEYA sunucu hatası — kuyrukta bırak, bir sonraki flush'ta tekrar denenir
    }
  }
  return { sent, remaining: items.length - sent };
}
