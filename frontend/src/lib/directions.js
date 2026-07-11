/**
 * IT-16 — "Navigasyon linki": bir [lat, lng] noktasına Google Maps yol
 * tarifi bağlantısı üretir. Anahtarsız/genel bir URL şeması (api=1) —
 * yeni bir bağımlılık veya entegrasyon GEREKMEZ, tarayıcı/telefonda
 * yüklüyse Google Maps uygulamasını, yoksa web haritasını açar.
 */
export function directionsUrl([lat, lng]) {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
}
