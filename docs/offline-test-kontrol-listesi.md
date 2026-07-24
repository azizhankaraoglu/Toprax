# Rol Bazlı Offline — Manuel Test Kontrol Listesi

Denetim raporu #2 (Faz 8). `/m` (Mobil PWA) üzerinde, DevTools "Offline"
simülasyonuyla test edilir: aksiyon çevrimdışıyken yapılır → kuyruğa
düştüğü doğrulanır → "Çevrimiçi"ye geçilir → otomatik senkron beklenir →
backend'de TEK kayıt oluştuğu doğrulanır (idempotency, bkz.
`backend/idempotency.py`).

Her satır: Rol → Aksiyon → Uç → Beklenen.

| Rol | Aksiyon | Uç | Offline kuyruklanır mı |
|---|---|---|---|
| ziraat_muhendisi / saha_personeli | Ziyaret kaydı (görev tamamlama) | `POST /visits` | ✅ |
| ziraat_muhendisi / saha_personeli | Checklist işaretleme | `PUT /tasks/{id}/checklist` | ✅ |
| ziraat_muhendisi / saha_personeli | Görev durum geçişi | `PUT /tasks/{id}/transition` | ✅ (idempotent) |
| ziraat_muhendisi / saha_personeli | Saha formu doldurma | `POST /forms/{id}/submit` | ✅ |
| ziraat_muhendisi / toprak_personeli | Saha toprak örneği (GPS izli) | `POST /soil-samples/field` | ✅ |
| kantar_personeli | Kantar tartımı | `POST /kantar/records` | ✅ |
| ciftci | Sulama kaydı | `POST /farmer/irrigation` | ✅ |
| ciftci | Destek talebi oluşturma | `POST /portal/support-requests` | ✅ |

## Test adımları (her satır için tekrarlanır)

1. `/m`'e ilgili rolle giriş yapın.
2. Chrome DevTools → Network → "Offline" işaretleyin (veya `navigator.
   onLine`'ı false yapan bir throttling profili).
3. İlgili formu doldurup gönderin — ekranda "Bağlantı yok — ... cihazda
   saklandı" mesajı VE üstte "N kayıt senkron bekliyor" bandı görünmeli.
4. DevTools'ta "Offline" işaretini kaldırın (çevrimiçi).
5. Sayfa otomatik `online` event'iyle senkronu tetikler (veya "Şimdi
   Dene" butonuna basın) — banttaki sayı 0'a inmeli, "N kayıt senkron
   edildi" mesajı görünmeli.
6. Backend'de ilgili koleksiyonda (`db.visits`/`db.kantar_records`/...)
   TAM OLARAK BİR kayıt oluştuğunu doğrulayın (iki değil — idempotency
   anahtarı olmasaydı bağlantı kesintisi anında oluşan bir "sessiz
   başarı"nın kuyruğa da düşüp tekrar gönderilmesi durumunda İKİ kayıt
   oluşurdu, bkz. `backend/idempotency.py` docstring'i).

## Bilinen sınırlamalar (bilinçli kapsam, v1)

- Okuma tarafı (görev/form listesi gibi "günün verisi") offline'a
  düşmeden ÖNCE bir kez yüklenmiş olmalı — sayfa hiç yüklenmeden
  doğrudan offline açılırsa boş görünür (`lib/offlineStore.js` gibi
  ayrı bir okuma-önbelleği bu iterasyonun kapsamı DIŞINDA bırakıldı;
  yazma tarafının [asıl "veri kaybetmeme" riski] kuyruklanması
  önceliklendirildi).
- Fotoğraflar offline'da base64 olarak `visits`/form yanıtlarına
  GÖMÜLÜR (IT-35'ten beri) — ayrı bir dosya yükleme kuyruğu yok,
  bilinçli (offlineQueue.js sadece JSON gövdeli istekleri kuyruklayabilir).
