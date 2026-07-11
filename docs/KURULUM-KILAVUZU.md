# TabSIS — On-Premise Kurulum Kılavuzu (IT Yöneticisi Seviyesi)

> Bu kılavuz, TabSIS'i kendi sunucunuzda (on-premise) sıfırdan kurmak için
> yazılmıştır. Hedef okuyucu: kurumunuzun IT ekibi. Yazılımcı olmanıza
> gerek yok, ama Linux/Windows sunucu yönetimi ve terminal kullanımına
> aşina olmanız beklenir. Sorularınız için satıcı firmayla iletişime
> geçebilirsiniz (bkz. sayfa sonu "Destek").

---

## 1. Ne Kuruyorsunuz?

TabSIS üç ana bileşenden oluşur, hepsi Docker container'ları olarak paketlenmiştir:

| Bileşen | Ne işe yarar | Varsayılan port |
|---|---|---|
| **mongo** | Veritabanı (MongoDB 7) | (dışarı açık değil — güvenlik) |
| **backend** | API sunucusu (FastAPI/Python) | 8001 |
| **frontend** | Web arayüzü (React, Nginx üzerinden sunulur) | 3000 |

İnternete açık kurulumlarda isteğe bağlı bir dördüncü bileşen daha vardır:

| Bileşen | Ne işe yarar |
|---|---|
| **reverse-proxy + certbot** | HTTPS (TLS) — domain üzerinden tek noktadan 80/443 |

---

## 2. Gereksinimler

### 2.1 Donanım (başlangıç için makul tahmin)

- En az **2 CPU çekirdeği**, **4 GB RAM**, **20 GB boş disk**.
- Kaç tenant/kullanıcı için ne kadar kapasite gerektiği kurumunuzun
  büyüklüğüne bağlıdır — bu bir kapasite planlaması kararıdır, yük testi
  sonuçlarına göre (bkz. ROADMAP-URUNLESTIRME.md PR-14) netleştirilmelidir.

### 2.2 Yazılım

- **Docker 24+** ve **Docker Compose plugin** (Docker Desktop bunları
  otomatik kurar): https://www.docker.com/products/docker-desktop/
- İnternete açık kurulumda: bir **domain adı** (TLS/HTTPS için, opsiyonel
  ama önerilir).

### 2.3 Otomatik Kontrol

Kuruluma başlamadan önce şu scripti çalıştırın — eksik bir şey varsa net
şekilde söyler:

```bash
bash scripts/check-requirements.sh
```

`[HATA]` satırı yoksa devam edebilirsiniz.

---

## 3. Kurulum Paketini Alma

İki yol vardır:

- **A) İnternete açık sunucu:** proje deposunu indirin/kopyalayın (git clone
  veya sağlanan .zip).
- **B) İnternetsiz (air-gapped) sunucu:** internete açık ayrı bir makinede
  `bash scripts/build-offline-bundle.sh` çalıştırıp üretilen
  `tabsis-offline-bundle-*.tar.gz` dosyasını USB/harici diskle taşıyın,
  hedef sunucuda açıp `bash scripts/install-from-bundle.sh` ile devam edin
  (bu script Bölüm 4-6'daki adımların hepsini otomatik yapar — sadece
  `.env` dosyasını düzenlemeniz istenecektir).

Kalan bölümler **A) İnternete açık** senaryosunu anlatır.

---

## 4. Ortam Değişkenlerini (.env) Hazırlama

```bash
cp .env.example .env
```

`.env` dosyasını bir metin editörüyle açıp **mutlaka değiştirin**:

- `MONGO_ROOT_PASSWORD` — güçlü, rastgele bir şifre.
- `JWT_SECRET` — şu komutla üretebilirsiniz: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `PLATFORM_ADMIN_EMAIL` / `PLATFORM_ADMIN_PASSWORD` — kurulum sihirbazında
  gireceğiniz platform yöneticisi hesabı.
- `CORS_ORIGINS` — kurumunuzun gerçek domain'i (örn. `https://tabsis.kurumunuz.com.tr`).

Varsayılan/zayıf değerlerle `ENVIRONMENT=production` iken sistem **açılmayı
reddeder** (fail-fast) — bu kasıtlı bir güvenlik önlemidir.

---

## 5. Servisleri Ayağa Kaldırma

```bash
docker compose up -d
```

Birkaç dakika içinde üç servis de `healthy` durumuna geçer. Kontrol etmek için:

```bash
docker compose ps
```

`STATUS` sütununda `healthy` görmelisiniz. Görmüyorsanız Bölüm 9 (Sorun
Giderme) bölümüne bakın.

---

## 6. Kurulum Sihirbazı

Tarayıcıdan `http://<sunucu-ip>:3000/kurulum` adresine gidin.

> [Ekran görüntüsü: Sihirbaz Adım 1 — Platform Girişi]

**Adım 1 — Platform Girişi:** `.env` dosyasındaki `PLATFORM_ADMIN_EMAIL` /
`PLATFORM_ADMIN_PASSWORD` ile giriş yapın.

> [Ekran görüntüsü: Sihirbaz Adım 2 — Kurum Oluştur]

**Adım 2 — Kurum Oluştur:** kooperatifinizin/kurumunuzun adı, iletişim
e-postası, plan tipi.

> [Ekran görüntüsü: Sihirbaz Adım 3 — Süper Admin]

**Adım 3 — İlk Süper Admin:** kurumunuzun ilk yöneticisinin hesabı — bundan
sonra günlük kullanım bu hesapla yapılır.

> [Ekran görüntüsü: Sihirbaz Adım 4 — SMTP]

**Adım 4 — E-Posta (SMTP), opsiyonel:** bildirim e-postaları için. Şimdi
atlayıp sonra **Ayarlar &gt; Entegrasyonlar**'dan da yapabilirsiniz.

> [Ekran görüntüsü: Sihirbaz Adım 5 — Lisans]

**Adım 5 — Lisans:** plan tipi (deneme/standart/premium) ve varsa bitiş tarihi.

**Adım 6 — Bitir:** "Kurulumu Bitir" butonuna bastığınızda sihirbaz
**kalıcı olarak kilitlenir** — güvenlik nedeniyle bir daha çalıştırılamaz.
Ardından normal giriş sayfasına yönlendirilirsiniz.

---

## 7. HTTPS (TLS) Kurulumu — internete açık kurulumlar için

Domain'inizin DNS kaydı sunucunuzun IP'sine işaret ediyorsa:

```bash
bash scripts/setup-tls.sh tabsis.kurumunuz.com.tr admin@kurumunuz.com.tr
```

Bu script Let's Encrypt sertifikasını otomatik alır ve **12 saatte bir**
otomatik yeniler (sertifika süresi dolmadan). Tamamen kapalı (air-gapped)
kurulumlarda bu adımı **atlayın** — kendi sertifikanızı `nginx/certs/`
altına `fullchain.pem` ve `privkey.pem` adlarıyla yerleştirip
`docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d
reverse-proxy` ile devam edin.

---

## 8. Kurulumu Doğrulama

```bash
bash scripts/smoke-test.sh
```

`=== Kurulum başarılı ===` mesajını görmelisiniz. Görmüyorsanız Bölüm 9'a bakın.

---

## 9. Sorun Giderme (SSS)

**S: `docker compose up` "MONGO_ROOT_USERNAME .env dosyasında tanımlanmalı" hatası veriyor.**
C: `.env` dosyasını oluşturmadınız veya boş bıraktınız — Bölüm 4'e bakın.

**S: Backend container sürekli yeniden başlıyor (`Restarting`).**
C: `docker compose logs backend` ile hatayı görün. En sık neden: `.env`
içindeki `JWT_SECRET`/`PLATFORM_ADMIN_PASSWORD` zayıf/varsayılan bırakılmış
(production modunda fail-fast reddedilir).

**S: `/kurulum` sayfası "zaten tamamlanmış" diyor ama hiç kurulum yapmadım.**
C: Muhtemelen daha önce biri (test amaçlı) sihirbazı çalıştırdı. Yeni bir
kurum eklemek için normal girişten sonra **Platform Admin &gt; Kurumlar**
ekranını kullanın — sihirbaz sadece İLK kurulum içindir.

**S: Bir port zaten kullanımda hatası alıyorum.**
C: `bash scripts/check-requirements.sh` bu portları (80/443/3000/8001)
kontrol eder ve hangisinin dolu olduğunu söyler. Çakışan servisi durdurun
veya `docker-compose.yml`'de port eşlemesini değiştirin.

**S: Air-gapped (internetsiz) sunucuda "image not found" hatası alıyorum.**
C: `docker load` adımının başarıyla tamamlandığından emin olun
(`scripts/install-from-bundle.sh` çıktısını kontrol edin) — imaj adları
tam olarak `tabsis-backend:latest` / `tabsis-frontend:latest` /
`mongo:7` olmalı.

**S: Sürüm yükseltmesi (`./upgrade.sh`) migration hatası veriyor.**
C: Script otomatik olarak eski sürüme (imaj + veritabanı) geri döner —
veri kaybı olmaz. Hatanın detayı için `docker compose logs backend`'e
bakıp satıcı firmayla paylaşın.

---

## 10. Sürüm Yükseltme

Yeni bir sürüm geldiğinde:

```bash
./upgrade.sh
```

Bu script yeni imajları çeker, migration'ları otomatik çalıştırır, hata
olursa otomatik geri döner, ve son olarak smoke test'i otomatik çalıştırır.

---

## 11. Destek

Bu kılavuzun kapsamadığı bir sorunla karşılaşırsanız satıcı firmayla
iletişime geçin. Lütfen şu bilgileri hazır bulundurun:

- `docker compose logs` çıktısı (ilgili servis için)
- `bash scripts/check-requirements.sh` ve `bash scripts/smoke-test.sh` çıktıları
- `.env` dosyanızdaki **hassas olmayan** kısımlar (ENVIRONMENT, CORS_ORIGINS vb. — şifreleri PAYLAŞMAYIN)
