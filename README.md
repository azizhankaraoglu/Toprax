# Toprax — Tarımsal Operasyon ve Karar Destek Platformu
## Yerel Kurulum Kılavuzu (Windows · macOS · Linux)

> **Kurumsal / on-premise satış kurulumu:** IT ekibiniz için adım adım,
> kurulum sihirbazı + TLS + air-gapped + sürüm yükseltme dahil kapsamlı
> kılavuz için bkz. [`docs/KURULUM-KILAVUZU.md`](docs/KURULUM-KILAVUZU.md).
> Aşağıdaki bölüm geliştirici/yerel kurulum içindir.

> **Sürüm 2.0 notları:** Bu sürümde bcrypt şifreleme, refresh token,
> rol hiyerarşisi, merkezi audit log ve
> **Ayarlar > Entegrasyonlar** modülü (SMS/Email/Planet Labs/AI servisi,
> gerçek "Bağlantıyı Test Et" butonlu) eklendi. Kurulumdan sonra `.env`
> dosyalarını `.env.example`'lardan oluşturmayı unutmayın (`JWT_SECRET`
> mutlaka değiştirilmeli).
>
> **Sprint 4 notları:** Harita üzerinde parsel çizme/düzenleme/böl/birleştir
> ve GeoJSON toplu import araçları eklendi (`leaflet-draw`, `@turf/turf`
> paketleri gerekli — `yarn install` bunları otomatik kuracaktır, ek bir
> işlem gerekmiyor ama ilk kurulumda internet bağlantısı gerekir).
>
> **Tenant (çoklu kurum) mimarisi:** Her kooperatif ayrı bir tenant —
> verileri birbirinden tamamen izole. İlk açılışta bir "platform admin"
> hesabı otomatik oluşturulur (`.env`'deki `PLATFORM_ADMIN_EMAIL` /
> `PLATFORM_ADMIN_PASSWORD`, tanımlı değilse varsayılan kullanılır —
> **üretimde mutlaka değiştirin**). Bu hesapla `/platform` adresinden
> giriş yapıp yeni kooperatif (tenant) oluşturabilir ve o kooperatifin
> ilk süper admin kullanıcısını atayabilirsiniz. Var olan demo giriş
> bilgileri (`admin@turkseker.com.tr` vb.) otomatik olarak "default"
> adlı bir tenant'a bağlanır, hiçbir şey değişmeden çalışmaya devam eder.
>
> **Granüler yetkilendirme:** Artık modül × fonksiyon bazında (örn.
> "kantar:create", "parcels:split_merge") ince ayarlı bir izin sistemi
> var. Ayarlar > Kullanıcılar'dan personel ekleyip built-in bir role
> (Kantar Personeli, Toprak/Numune Personeli dahil) veya kendi
> tanımladığınız özel bir role atayabilir, gerekirse role ek/eksik tekil
> izin de tanımlayabilirsiniz (Ayarlar > Özel Roller).


> Bu kılavuz, projeyi kendi bilgisayarında sıfırdan çalıştırmak için adım adım anlatımdır.  
> İki yöntem var: **YÖNTEM A — Docker (en kolay, önerilen)** veya **YÖNTEM B — Manuel kurulum**.

---

## 📦 PROJE NEDİR?
Türk Şeker benzeri büyük tarım kooperatifleri için **kooperatifin kendi sunucusunda çalışan** uçtan uca dijital yönetim platformu.

**Tech Stack:**
- **Backend:** Python 3.11 + FastAPI
- **Frontend:** React 19 + Tailwind + Leaflet + Recharts
- **Veritabanı:** MongoDB 7
- **Süreç yöneticisi:** Supervisor (üretimde) / yarn & uvicorn (yerelde)

---

## ⚙️ ORTAM DEĞİŞKENLERİ (.env)

**UYARI:** Aşağıdaki değişkenler üretim ortamında zorunludur ve güvenlikle ilgilidir.

### Docker Kurulumu İçin

`.env` dosyasını kökünde (docker-compose.yml ile aynı klasörde) oluşturun (`.env.example`'ı kopyalayın):

```bash
cp .env.example .env
```

Dosyayı açıp DEGISTIR ile marked alanları güncelleyin:
- `MONGO_ROOT_PASSWORD` — Güçlü, rastgele bir şifre (örn. `python -c "import secrets; print(secrets.token_hex(16))"`)
- `JWT_SECRET` — Güçlü, rastgele bir token (örn. `python -c "import secrets; print(secrets.token_hex(32))"`)
- `PLATFORM_ADMIN_PASSWORD` — Yönetici hesap şifresi

**Güvenlik notu:** `.env` dosyası **asla repo'ya commit'lenmez** (`.gitignore`'a ekli). Sadece `.env.example` paylaşılır; üretime deploy etmeden önce gerçek değerler doldurulur.

### Manuel Kurulumu İçin

Backend ve frontend **ayrı** `.env` dosyasına ihtiyaç duymaz. Sadece backend'de basit bir local config oluşturursunuz (üretimde Docker ile tek bir root `.env` yeterlidir).

---

## 🟢 YÖNTEM A — DOCKER İLE TEK KOMUTLA (ÖNERİLEN)

### Ön Koşullar
Sadece bunu kur, başka şeye gerek yok:
- **Docker Desktop** → https://www.docker.com/products/docker-desktop/
  - Windows için: WSL 2 etkin olmalı (Docker Desktop otomatik kurar)
  - macOS için: Apple Silicon veya Intel sürümünü indir
  - Linux için: `sudo apt install docker.io docker-compose-plugin`

### Adımlar

**1. Projeyi indir/aç ve .env hazırla**
```bash
# Bu klasöre projeyi indir (Save to Github ile veya manuel ZIP indir)
cd ~/Desktop/dijital-tarim

# .env dosyasını oluştur (.env.example'ı kopyala ve değerleri doldur)
cp .env.example .env
# Editör ile .env aç ve DEGISTIR ile marked alanları güncelle
```

**2. Tek komutla başlat**
```bash
docker compose up -d
```
İlk çalıştırmada 5-10 dakika sürer (image'ları indirir, build eder).

**3. Veriyi yükle (sadece ilk seferde)**
```bash
# Ana seed
curl -X POST http://localhost:8001/api/admin/seed

# Ek demo verileri (e-fatura, irsaliye, kantar, audit, saha ziyaret)
curl -X POST http://localhost:8001/api/admin/seed-extras
```

**4. Tarayıcıdan aç**
- Frontend: **http://localhost:3000**
- Backend API: **http://localhost:8001/api**
- MongoDB: **localhost:27017**

**5. Giriş yap**
- `admin@turkseker.com.tr` / `admin123` — Süper Admin
- `ahmet.yilmaz@turkseker.com.tr` / `ahmet123` — Fabrika Müdürü
- `mehmet.demir@turkseker.com.tr` / `mehmet123` — Ziraat Mühendisi
- `ayse.kaya@turkseker.com.tr` / `ayse123` — Saha Personeli
- `kantar@turkseker.com.tr` / `kantar123` — Kantar Personeli (sadece kantar/lojistik/e-belge yetkisi)
- `toprak@turkseker.com.tr` / `toprak123` — Toprak/Numune Personeli (sadece toprak/sulama girişi yetkisi)

### Yararlı Komutlar
```bash
docker compose ps              # Çalışan servisleri gör
docker compose logs -f         # Anlık logları izle
docker compose logs -f backend # Sadece backend logu
docker compose stop            # Durdur
docker compose down            # Tamamen kaldır (veriyi siler!)
docker compose down -v         # Volume'ları da sil
docker compose restart backend # Sadece backend yeniden başlat
```

---

## 🔵 YÖNTEM B — MANUEL KURULUM (Docker olmadan)

### Ön Koşullar
Aşağıdakileri sırayla kur:

#### 1. Python 3.11+
- **Windows:** https://www.python.org/downloads/ → İndir & kur ("Add Python to PATH" işaretle)
- **macOS:** `brew install python@3.11`
- **Linux:** `sudo apt install python3.11 python3.11-venv python3-pip`

Kontrol: `python --version` → `Python 3.11.x` çıkmalı

#### 2. Node.js 18+ & Yarn
- **Windows / macOS / Linux:** https://nodejs.org/ → LTS indir & kur
- Yarn yükle: `npm install -g yarn`

Kontrol: `node -v` ve `yarn -v`

#### 3. MongoDB 7+
- **Windows:** https://www.mongodb.com/try/download/community → "msi" indir & kur (servis olarak çalışsın seç)
- **macOS:** 
  ```bash
  brew tap mongodb/brew
  brew install mongodb-community@7.0
  brew services start mongodb-community
  ```
- **Linux (Ubuntu):**
  ```bash
  curl -fsSL https://pgp.mongodb.com/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
  echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
  sudo apt update && sudo apt install -y mongodb-org
  sudo systemctl start mongod
  ```

Kontrol: `mongosh` (bağlanmalı, `exit` ile çık)

---

### Adımlar

**1. Projeyi klasöre kopyala**

**2. Backend kurulumu**
```bash
cd backend

# Sanal ortam oluştur
python -m venv venv

# Aktif et:
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# Bağımlılıkları kur
pip install -r requirements.txt

# .env dosyasını oluştur (mevcut değilse) — veya backend/.env.example'ı kopyala
cat > .env <<EOF
MONGO_URL=mongodb://localhost:27017
DB_NAME=tarim_kooperatif
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
EOF

# Backend'i başlat
uvicorn server:app --reload --host 0.0.0.0 --port 8001
```
Bu terminali açık bırak.

**3. Frontend kurulumu (YENİ TERMİNAL aç)**
```bash
cd frontend

# .env dosyasını oluştur (mevcut değilse)
cat > .env <<EOF
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=3000
EOF

# Bağımlılıkları kur
yarn install

# Geliştirme sunucusu
yarn start
```
Tarayıcıda otomatik açılır: http://localhost:3000

**4. Veri yükle (YENİ TERMİNAL aç, sadece ilk seferde)**
```bash
curl -X POST http://localhost:8001/api/admin/seed
```
Beklenen çıktı: `{"status":"seeded","counts":{...}}` — 200 çiftçi, 300 parsel vs. yüklendi.

**5. Giriş yap → http://localhost:3000**
- Demo hesaplar yukarıdaki aynı.

---

## 🛠️ SORUN GİDERME

### "Port already in use" hatası
Başka bir program 8001 veya 3000 portunu kullanıyor.
```bash
# Windows:
netstat -ano | findstr :8001
taskkill /PID <PID> /F

# macOS / Linux:
lsof -i :8001
kill -9 <PID>
```

### MongoDB bağlanmıyor
- MongoDB servisi çalışıyor mu kontrol et:
  - Windows: `services.msc` → "MongoDB Server" çalışıyor mu?
  - macOS: `brew services list`
  - Linux: `sudo systemctl status mongod`

### "Module not found" hatası (Python)
Sanal ortam aktif değil. Tekrar `venv\Scripts\activate` (Windows) ya da `source venv/bin/activate` (macOS/Linux).

### Frontend boş sayfa açıyor
- `.env` dosyasında `REACT_APP_BACKEND_URL` doğru mu?
- Backend gerçekten çalışıyor mu? Tarayıcıda `http://localhost:8001/api/` aç, JSON dönmeli.

### Veri yüklenmemiş (giriş yapılamıyor)
```bash
curl -X POST http://localhost:8001/api/admin/seed
```

### Tüm veriyi sıfırlamak istiyorum
```bash
# Force flag ile yeniden seed (mevcut veriyi siler + yeniden yükler)
curl -X POST "http://localhost:8001/api/admin/seed?force=true"
```

veya MongoDB üzerinden manuel:
```bash
mongosh
> use tarim_kooperatif
> db.dropDatabase()
> exit

# Tekrar seed
curl -X POST http://localhost:8001/api/admin/seed
```

---

## 📁 PROJE YAPISI

```
dijital-tarim/
├── backend/                  # FastAPI backend
│   ├── server.py            # Ana API endpoint'leri, auth, seed
│   ├── config.py            # Rol hiyerarşisi, JWT/CORS ayarları
│   ├── security.py          # bcrypt hash, access/refresh token
│   ├── audit.py             # Audit log kayıt + listeleme
│   ├── integrations.py      # Ayarlar: SMS/Email/Planet Labs/AI servisi + test
│   ├── extras.py            # AI hastalık tespiti, e-fatura, kantar, NDVI mock
│   ├── forms_module.py      # Saha veri toplama form builder
│   ├── requirements.txt     # Python bağımlılıkları
│   ├── .env.example         # Örnek ortam değişkenleri (kopyalayıp .env yapın)
│   └── .env                 # MONGO_URL, DB_NAME, JWT_SECRET, CORS_ORIGINS
│
├── frontend/                # React PWA
│   ├── src/
│   │   ├── App.js          # Router
│   │   ├── api.js          # Axios + auth + otomatik refresh token
│   │   ├── components/
│   │   │   └── Layout.jsx  # Sidebar + nav (rol bazlı görünürlük)
│   │   └── pages/
│   │       ├── Login.jsx
│   │       ├── Dashboard.jsx
│   │       ├── Farmers.jsx
│   │       ├── Parcels.jsx     # Harita ile
│   │       ├── Sulama.jsx
│   │       ├── Operasyon.jsx
│   │       ├── Verimlilik.jsx
│   │       ├── Extras.jsx      # Ayarlar/Entegrasyonlar, Audit Log, AI, e-fatura...
│   │       └── Other.jsx       # Sözleşme, Ekim, Lojistik, Karne, Bildirim
│   ├── package.json
│   ├── .env.example         # Örnek ortam değişkenleri
│   └── .env                 # REACT_APP_BACKEND_URL
│
├── memory/
│   └── PRD.md               # Ürün gereksinim dokümanı (17 modül)
│
├── docker-compose.yml       # Docker tek komut kurulum
├── Dockerfile.backend
├── Dockerfile.frontend
└── README.md                # Bu dosya
```

---

## 🚀 ÜRETİME ALMA (Kooperatif Sunucusuna)

Kooperatifin kendi sunucusuna kurmak için:

1. **Sunucu hazırla:**
   - Ubuntu 22.04 LTS
   - 8 vCPU, 16 GB RAM, 500 GB SSD (≤20.000 çiftçi için)
   - Docker + Docker Compose kur

2. **Projeyi kopyala:**
   ```bash
   scp -r dijital-tarim/ root@<sunucu-ip>:/opt/
   ```

3. **`.env` dosyalarını düzenle:**
   - `REACT_APP_BACKEND_URL` → kooperatifin domain'i (örn. `https://tarim.turkseker.com.tr`)
   - Güçlü JWT secret değiştir (`backend/.env` içindeki `JWT_SECRET`)
   - `CORS_ORIGINS` → sadece kooperatif domain'i

4. **HTTPS için Nginx + Let's Encrypt** (ayrı kılavuz)

5. **Yedekleme:** Cron job ile günlük MongoDB dump:
   ```bash
   0 2 * * * docker exec mongo mongodump --out /backup/$(date +\%F)
   ```

---

## 📞 DESTEK

- **Demo:** Demo hesaplarla deneyebilirsin
- **PRD:** Tüm 17 modülün detayı `memory/PRD.md` içinde
- **Issues:** Sorunları kaydet, devam ettiğimizde çözelim

> Bu MVP prototipi. Üretim (production) sürümü için: KVKK uyum, audit log, e-fatura entegrasyonu, kantar cihaz entegrasyonu, SMS/WhatsApp gerçek aktivasyon ve detaylı eğitim sürümleri sonraki fazlarda gelir.
