"""
=====================================================================
Toprax — Demo Seed + Sistem uçları (/admin/seed, /, /health, /roles)
=====================================================================
Denetim A6 (2026-07-24): server.py (~2900 satır) modülerleştirmesi —
bu dosyadaki endpoint'ler server.py'den BİREBİR taşındı, davranış
değişikliği YOK. Route kayıt SIRASI korunur: register çağrısı server.py
içinde bloğun orijinal konumundan yapılır (Starlette route-order tuzağı,
bkz. CLAUDE.md /parcels/bulk-update notu).
"""
import uuid
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
from tenant_context import current_tenant_id
from config_service import (ALLOW_DATA_SEEDING, ADMIN_TIER_ROLES, APP_NAME,
                            APP_FULL_NAME, APP_VERSION, ROLE_HIERARCHY, ROLE_LABELS)


def register_seed_routes(api_router, db, raw_db, current_user, hash_pw):
    def _require_seed_authority(user: dict):
        """Seed uçları sadece platform_admin / super_admin / kurumsal admin
        katmanı (ADMIN_TIER_ROLES) tarafından çağrılabilir — bkz. ROADMAP P0
        bulgusu: kimlik doğrulaması olmayan çağrılar demo verisini silip
        yeniden oluşturabiliyordu. platform_admin uygulama açılışında zaten
        otomatik bootstrap edildiği için (bkz. startup event) bu kontrol
        "ilk kurulum" akışını KIRMAZ — operatör önce platform_admin ile giriş
        yapıp aldığı token'la bu uca çağrı yapar."""
        role = user.get("role")
        if role != "platform_admin" and role not in ADMIN_TIER_ROLES and role != "super_admin":
            raise HTTPException(403, "Bu işlem için yönetici yetkisi gerekir")


    @api_router.post("/admin/seed")
    async def seed_data(force: bool = False, user=Depends(current_user)):
        """
        Idempotent seed işlemi.

        `force=true` parametresi geçilirse mevcut veriyi temizleyip yeniden yükler.
        Aksi halde sadece veri yoksa yükler.

        Tenant davranışı: bu çağrı zaten giriş yapmış bir tenant admin'i
        tarafından (Authorization header ile) yapılıyorsa, seed verisi O
        tenant'a yazılır (kendi kooperatifinin demo verisini oluşturur/sıfırlar).
        Platform admin tenant_id taşımadığı için (current_tenant_id None kalır),
        "default" adlı bir tenant otomatik bulunur/oluşturulur ve veri oraya
        yazılır — mevcut demo giriş bilgileri (admin@kooperatif.com vb.)
        böylece değişmeden çalışmaya devam eder.

        Kimlik doğrulaması ve yönetici yetkisi ZORUNLUDUR (P0 güvenlik
        düzeltmesi — daha önce anonim çağrılar mevcut tenant'ın verisini
        silip yeniden oluşturabiliyordu). Ayrıca ALLOW_DATA_SEEDING=false
        (üretimde varsayılan) iken bu uç tamamen kapalıdır.
        """
        if not ALLOW_DATA_SEEDING:
            raise HTTPException(403, "Demo veri yükleme bu ortamda kapalı (ALLOW_DATA_SEEDING=false)")
        _require_seed_authority(user)

        reset_token = None
        if current_tenant_id.get() is None:
            default_tenant = await raw_db.tenants.find_one({"slug": "default"}, {"_id": 0})
            if not default_tenant:
                default_tenant = {
                    "id": str(uuid.uuid4()),
                    "name": "Toprax Demo Kooperatifi",
                    "slug": "default",
                    "contact_email": "demo@toprax.local",
                    "plan": "deneme",
                    "status": "aktif",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "system-bootstrap",
                }
                await raw_db.tenants.insert_one(dict(default_tenant))
            reset_token = current_tenant_id.set(default_tenant["id"])

        try:
            return await _run_seed(force)
        finally:
            if reset_token is not None:
                current_tenant_id.reset(reset_token)


    async def _run_seed(force: bool = False):
        if not force and await db.users.count_documents({}) > 0:
            return {"status": "already_seeded", "hint": "Sıfırlamak için ?force=true ekleyin"}
    
        # Force ise tüm koleksiyonları temizle (SADECE mevcut tenant'ınkiler —
        # db zaten tenant-scoped olduğu için delete_many otomatik filtrelenir)
        if force:
            collections = ["users", "regions", "farmers", "parcels", "contracts",
                           "plantings", "yields", "soil_samples", "water_sources",
                           "irrigation_plans", "irrigation_events", "machines",
                           "workers", "tasks", "appointments", "finance", "notifications",
                           "iot_sensors", "drone_missions"]
            for c in collections:
                await db[c].delete_many({})
    
        now = datetime.now(timezone.utc).isoformat()
        random.seed(42)  # Tekrarlanabilir veri için sabit seed
    
        # ============ ADMİN KULLANICILARI ============
        admin_users = [
            {"id": str(uuid.uuid4()), "email": "admin@turkseker.com.tr", "password": hash_pw("admin123"),
             "full_name": "Sistem Yöneticisi", "role": "super_admin", "created_at": now},
            {"id": str(uuid.uuid4()), "email": "ahmet.yilmaz@turkseker.com.tr", "password": hash_pw("ahmet123"),
             "full_name": "Ahmet Yılmaz", "role": "fabrika_muduru", "region": "Konya", "created_at": now},
            {"id": str(uuid.uuid4()), "email": "mehmet.demir@turkseker.com.tr", "password": hash_pw("mehmet123"),
             "full_name": "Mehmet Demir", "role": "ziraat_muhendisi", "region": "Konya", "created_at": now},
            {"id": str(uuid.uuid4()), "email": "ayse.kaya@turkseker.com.tr", "password": hash_pw("ayse123"),
             "full_name": "Ayşe Kaya", "role": "saha_personeli", "region": "Konya", "created_at": now},
            {"id": str(uuid.uuid4()), "email": "kantar@turkseker.com.tr", "password": hash_pw("kantar123"),
             "full_name": "Hasan Kantarcı", "role": "kantar_personeli", "region": "Konya", "created_at": now},
            {"id": str(uuid.uuid4()), "email": "toprak@turkseker.com.tr", "password": hash_pw("toprak123"),
             "full_name": "Fatma Toprakçı", "role": "toprak_personeli", "region": "Konya", "created_at": now},
        ]
        await db.users.insert_many(admin_users)
    
        # ============ BÖLGELER ============
        region_names = [
            ("Konya", "Konya / İç Anadolu"), ("Eskişehir", "Eskişehir Bölgesi"),
            ("Kayseri", "Kayseri / Boğazlıyan"), ("Erzurum", "Erzurum / Doğu Anadolu"),
            ("Afyon", "Afyonkarahisar"), ("Çorum", "Çorum / Karadeniz"),
            ("Ankara", "Ankara / Polatlı"), ("Yozgat", "Yozgat / Boğazlıyan")
        ]
        regions = [{"id": str(uuid.uuid4()), "name": n, "description": d, "active": True} for n, d in region_names]
        await db.regions.insert_many(regions)
    
        # ============ ÇİFTÇİLER ============
        first_names = ["Ahmet", "Mehmet", "Mustafa", "Ali", "Hasan", "Hüseyin", "İbrahim", "Osman",
                       "Yusuf", "Ramazan", "Recep", "Süleyman", "Kadir", "Mahmut", "Bekir", "Cemal",
                       "Halil", "İsmail", "Ömer", "Ekrem", "Sabri", "Veli", "Murat", "Salih", "Adem"]
        last_names = ["Yılmaz", "Kaya", "Demir", "Çelik", "Şahin", "Yıldız", "Yıldırım", "Öztürk",
                      "Aydın", "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara",
                      "Koç", "Kurt", "Özkan", "Şimşek", "Tekin", "Polat", "Bulut", "Acar", "Erdoğan"]
        villages = ["Hacıveli", "Kuzucu", "Yenidoğan", "Aşağıçiğil", "Sarıkamış", "Karaköy", "Çamlıdere",
                    "Pınarbaşı", "Akpınar", "Yeşilköy", "Doğanca", "Gümüşpınar", "Boyalıca", "Ovacık",
                    "Beyköy", "Karaağaç"]
    
        farmers = []
        farmer_user_records = []                                # Her çiftçi için bir login hesabı
    
        for i in range(200):
            farmer_id = str(uuid.uuid4())
            rid = random.choice(regions)["id"]
            karne_pt = random.randint(35, 98)
            karne = "A" if karne_pt >= 85 else "B" if karne_pt >= 70 else "C" if karne_pt >= 55 else "D"
            member_no = f"TS-{(i+1):05d}"
            full_name = f"{random.choice(first_names)} {random.choice(last_names)}"
        
            farmer = {
                "id": farmer_id,
                "member_no": member_no,
                "full_name": full_name,
                "tc_no": f"{random.randint(10000000000, 99999999999)}",
                "phone": f"05{random.randint(30, 59)}{random.randint(1000000, 9999999)}",
                "email": f"{member_no.lower()}@ciftci.tr",      # Çiftçi giriş email'i
                "village": random.choice(villages),
                "region_id": rid,
                "iban": f"TR{random.randint(10**23, 10**24 - 1)}",
                "karne_score": karne,
                "karne_points": karne_pt,
                "status": "aktif" if random.random() > 0.05 else "pasif",
                "membership_year": random.choice([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]),
                "created_at": now
            }
            farmers.append(farmer)
        
            # Her çiftçi için login kullanıcısı oluştur (ÖNEMLİ — self-servis için)
            # Email: ts-00001@ciftci.tr / Şifre: ciftci123
            farmer_user_records.append({
                "id": str(uuid.uuid4()),
                "email": f"{member_no.lower()}@ciftci.tr",
                "password": hash_pw("ciftci123"),
                "full_name": full_name,
                "role": "ciftci",
                "farmer_id": farmer_id,                         # Hangi çiftçi profiline bağlı
                "created_at": now
            })
    
        await db.farmers.insert_many(farmers)
        await db.users.insert_many(farmer_user_records)
    
        # ============ PARSELLER ============
        soil_types = ["Killi", "Kumlu", "Tınlı", "Kireçli", "Killi-Tınlı"]
        irrigation_types = ["Damla", "Yağmurlama", "Karık", "Yok"]
        parcels = []

        # Her bölge için gerçekçi bir merkez koordinat (Türkiye şeker pancarı
        # kuşağı — Konya/Çumra ağırlıklı, roadmap'te belirtildiği gibi).
        # Böylece parseller "Türkiye'nin her yerine rastgele saçılmış" değil,
        # köy/bölge bazında gerçekçi kümeler halinde oluşur.
        region_centers = {
            "Konya": (37.51, 32.77),        # Çumra/Konya
            "Eskişehir": (39.78, 30.52),
            "Kayseri": (38.73, 35.49),
            "Erzurum": (39.90, 41.27),
            "Afyon": (38.76, 30.54),
            "Çorum": (40.55, 34.95),
            "Ankara": (39.58, 32.13),       # Polatlı
            "Yozgat": (39.82, 34.80),
        }
        # Köy başına küçük bir ofset — aynı köydeki parseller birbirine yakın olsun
        village_offsets = {v: (random.uniform(-0.06, 0.06), random.uniform(-0.06, 0.06)) for v in villages}

        # ÖNEMLİ: Her çiftçiye en az 1 parsel ver (ilk 200 parsel sırayla)
        # Kalan parseller rastgele çiftçilere ek olarak dağıtılır (bazı
        # çiftçiler 2-6 parselli olur — gerçek kooperatif dağılımına benzer).
        TOTAL_PARCELS = 1000
        for i in range(TOTAL_PARCELS):
            if i < len(farmers):
                farmer = farmers[i]                              # İlk 200'ü sırayla → herkese 1 parsel
            else:
                farmer = random.choice(farmers)                  # Kalanlar random (bazı çiftçiler çok parselli olur)

            region = next(r for r in regions if r["id"] == farmer["region_id"])
            center_lat, center_lng = region_centers.get(region["name"], (39.0, 33.0))
            voff_lat, voff_lng = village_offsets[farmer["village"]]

            # Gerçek bir tarla ölçeğinde konum: bölge merkezi + köy ofseti +
            # küçük rastgele sapma (birkaç km içinde, GERÇEKÇİ tarla kümesi)
            base_lat = center_lat + voff_lat + random.uniform(-0.015, 0.015)
            base_lng = center_lng + voff_lng + random.uniform(-0.015, 0.015)

            area_dekar = round(random.uniform(15, 350), 1)
            # Polygon boyutunu alana göre orantıla (100 dekar ≈ 0.001° kare civarı)
            d = 0.0008 + (area_dekar / 350) * 0.0025
            geometry = {
                "type": "Polygon",
                "coordinates": [[
                    [base_lng, base_lat],
                    [base_lng + d, base_lat],
                    [base_lng + d, base_lat + d],
                    [base_lng, base_lat + d],
                    [base_lng, base_lat]                        # İlk noktaya geri dön (kapalı polygon)
                ]]
            }

            # NDVI ve risk skoru — birbirleriyle TUTARLI üretiliyor (düşük NDVI
            # → yüksek risk), rastgele bağımsız değerler değil.
            ndvi_latest = round(random.uniform(0.35, 0.92), 3)
            if ndvi_latest > 0.72:
                risk_level, risk_label = "yesil", "Düşük Risk"
            elif ndvi_latest > 0.55:
                risk_level, risk_label = "sari", "İzlemeye Değer"
            elif ndvi_latest > 0.42:
                risk_level, risk_label = "turuncu", "Riskli"
            else:
                risk_level, risk_label = "kirmizi", "Acil Müdahale"

            parcels.append({
                "id": str(uuid.uuid4()),
                "parcel_code": f"KNY-{(i+1):04d}" if region["name"] == "Konya" else f"PRS-{(i+1):05d}",
                "name": f"{farmer['village']} Tarlası {i+1}",
                "farmer_id": farmer["id"],
                "village": farmer["village"],
                "region_id": farmer["region_id"],
                "area_dekar": area_dekar,
                "soil_type": random.choice(soil_types),
                "irrigation": random.choice(irrigation_types),
                "geometry": geometry,
                "current_crop": "Şeker Pancarı",
                "active_season": 2025,
                "ndvi_latest": ndvi_latest,
                "risk_level": risk_level,          # yesil | sari | turuncu | kirmizi
                "risk_label": risk_label,
                "expected_yield_ton": round(area_dekar * random.uniform(4.5, 7.2) * (0.7 + ndvi_latest * 0.5), 1),
                "last_satellite_scan": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 12))).isoformat(),
                "created_at": now
            })
        await db.parcels.insert_many(parcels)
    
        # ============ SÖZLEŞMELER ============
        contracts = []
        for p in parcels:
            for season in [2024, 2025]:
                contracts.append({
                    "id": str(uuid.uuid4()),
                    "contract_no": f"SZ-{season}-{p['parcel_code'][-5:]}",
                    "season": season,
                    "farmer_id": p["farmer_id"],
                    "parcel_id": p["id"],
                    "region_id": p["region_id"],
                    "crop": "Şeker Pancarı",
                    "variety": random.choice(["Lider", "Adrianna KWS", "Marbella", "Vivianna"]),
                    "kota_dekar": p["area_dekar"],
                    "kota_ton": round(p["area_dekar"] * random.uniform(5, 7), 1),
                    "advance_seed_kg": round(p["area_dekar"] * 0.18, 1),
                    "advance_fertilizer_kg": round(p["area_dekar"] * 35, 1),
                    "status": "imzalı" if random.random() > 0.08 else random.choice(["taslak", "imzalı", "imzalı"]),
                    "created_at": now
                })
        await db.contracts.insert_many(contracts)
    
        # ============ EKİM + VERİM ============
        plantings = []
        yields_list = []
        for c in contracts:
            plantings.append({
                "id": str(uuid.uuid4()),
                "contract_id": c["id"],
                "parcel_id": c["parcel_id"],
                "farmer_id": c["farmer_id"],
                "region_id": c["region_id"],
                "season": c["season"],
                "crop": c["crop"],
                "variety": c["variety"],
                "planting_date": f"{c['season']}-03-{random.randint(10, 28):02d}",
                "expected_harvest_date": f"{c['season']}-10-{random.randint(1, 30):02d}",
                "actual_harvest_date": f"{c['season']}-10-{random.randint(5, 30):02d}" if c["season"] < 2026 else None,
                "stage": "hasat" if c["season"] < 2025 else random.choice(["ekim", "gelişim", "olgunlaşma", "hasat"])
            })
            if c["season"] <= 2025:
                actual_ton = c["kota_ton"] * random.uniform(0.65, 1.15)
                yields_list.append({
                    "id": str(uuid.uuid4()), "parcel_id": c["parcel_id"], "farmer_id": c["farmer_id"],
                    "region_id": c["region_id"], "season": c["season"], "crop": c["crop"],
                    "area_dekar": c["kota_dekar"], "expected_ton": c["kota_ton"],
                    "actual_ton": round(actual_ton, 2), "polar_oran": round(random.uniform(14.5, 18.5), 2)
                })
        # Geçmiş yıl verim
        for yr in [2021, 2022, 2023]:
            for p in random.sample(parcels, 500):
                actual_ton = p["area_dekar"] * random.uniform(4.8, 6.8)
                yields_list.append({
                    "id": str(uuid.uuid4()), "parcel_id": p["id"], "farmer_id": p["farmer_id"],
                    "region_id": p["region_id"], "season": yr, "crop": "Şeker Pancarı",
                    "area_dekar": p["area_dekar"], "expected_ton": round(p["area_dekar"] * 6, 1),
                    "actual_ton": round(actual_ton, 2), "polar_oran": round(random.uniform(14, 18), 2)
                })
        await db.plantings.insert_many(plantings)
        await db.yields.insert_many(yields_list)
    
        # ============ TOPRAK ANALİZLERİ ============
        soil_samples = []
        for p in random.sample(parcels, 400):
            ph = round(random.uniform(6.5, 8.2), 2)
            n = random.randint(15, 80)
            # Akıllı öneri: pH ve N seviyesine göre
            if n < 30:
                rec = "Acil azot uygulaması — Üre 40 kg/dekar"
            elif ph > 7.8:
                rec = "Alkalin toprak — Asit içerikli DAP tercih et, 25 kg/dekar"
            else:
                rec = "Standart DAP 25 kg/dekar + Üre 30 kg/dekar"
        
            soil_samples.append({
                "id": str(uuid.uuid4()),
                "parcel_id": p["id"],
                "date": f"2025-{random.randint(1, 6):02d}-{random.randint(1, 28):02d}",
                "lab_name": random.choice(["Konya Tarım Lab", "Eskişehir Toprak Analiz", "TÜBİTAK MAM"]),
                "ph": ph,
                "ec": round(random.uniform(0.3, 1.8), 2),
                "organic_matter_pct": round(random.uniform(1.2, 4.5), 2),
                "n_ppm": n,
                "p_ppm": random.randint(8, 45),
                "k_ppm": random.randint(120, 380),
                "recommendation": rec
            })
        await db.soil_samples.insert_many(soil_samples)
    
        # ============ SU KAYNAKLARI ============
        water_sources = []
        for r in regions:
            for i in range(random.randint(2, 5)):
                water_sources.append({
                    "id": str(uuid.uuid4()),
                    "name": f"{r['name']} {random.choice(['Artezyen', 'Kanal', 'Göl', 'Yer Altı'])} {i+1}",
                    "type": random.choice(["artezyen", "kanal", "göl", "yer altı"]),
                    "region_id": r["id"],
                    "capacity_m3_per_day": random.randint(500, 5000),
                    "current_level_pct": random.randint(30, 95),
                    "status": "aktif"
                })
        await db.water_sources.insert_many(water_sources)
    
        # ============ SULAMA PLANLARI + OLAYLARI ============
        irrigation_plans = []
        irrigation_events = []
        methods = ["damla", "yağmurlama", "karık"]
        for p in random.sample(parcels, 450):
            method = random.choice(methods)
            irrigation_plans.append({
                "id": str(uuid.uuid4()), "parcel_id": p["id"], "farmer_id": p["farmer_id"],
                "region_id": p["region_id"], "season": 2025, "method": method,
                "planned_turns": random.randint(4, 12),
                "planned_m3": round(p["area_dekar"] * random.uniform(35, 65), 1),
                "start_date": "2025-05-15", "end_date": "2025-09-15"
            })
            for ev in range(random.randint(2, 8)):
                irrigation_events.append({
                    "id": str(uuid.uuid4()), "parcel_id": p["id"], "farmer_id": p["farmer_id"],
                    "region_id": p["region_id"],
                    "date": f"2025-{random.randint(5, 9):02d}-{random.randint(1, 28):02d}",
                    "method": method,
                    "water_m3": round(p["area_dekar"] * random.uniform(4, 8), 1),
                    "moisture_before": random.randint(15, 35), "moisture_after": random.randint(55, 85)
                })
        await db.irrigation_plans.insert_many(irrigation_plans)
        await db.irrigation_events.insert_many(irrigation_events)
    
        # ============ MAKİNELER ============
        machine_types = [
            ("Traktör", ["John Deere 6120M", "Case IH Maxxum 130", "New Holland T6.140", "Massey Ferguson 5713 S"]),
            ("Pulluk", ["Lemken Juwel 8", "Kverneland LB 100", "Özkardeşler 4'lü Pulluk"]),
            ("Biçerdöver", ["Claas Lexion 5500", "John Deere S780", "New Holland CR8.90"]),
            ("Pülverizatör", ["Tezel 600 lt", "Hardi 1000 lt", "Berthoud 800 lt"]),
            ("Ekim Makinası", ["Monosem NG Plus", "Kverneland Optima", "Mater Macc MS 8000"])
        ]
        machines = []
        for r in regions:
            for cat, models in machine_types:
                for _ in range(random.randint(1, 3)):
                    machines.append({
                        "id": str(uuid.uuid4()), "type": cat, "model": random.choice(models),
                        "serial_no": f"MK-{random.randint(10000, 99999)}",
                        "region_id": r["id"],
                        "status": random.choices(["aktif", "bakım", "boşta"], weights=[0.65, 0.15, 0.2])[0],
                        "owner": random.choice(["kooperatif", "çiftçi"]),
                        "total_hours": random.randint(500, 8000),
                        "last_maintenance": f"2025-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
                    })
        await db.machines.insert_many(machines)
    
        # ============ İŞÇİLER ============
        workers = []
        for r in regions:
            for _ in range(random.randint(8, 20)):
                workers.append({
                    "id": str(uuid.uuid4()),
                    "full_name": f"{random.choice(first_names)} {random.choice(last_names)}",
                    "phone": f"05{random.randint(30, 59)}{random.randint(1000000, 9999999)}",
                    "region_id": r["id"],
                    "skill": random.choice(["traktör sürücüsü", "saha işçisi", "biçerdöver operatörü", "ekipman uzmanı"]),
                    "daily_wage": random.choice([800, 900, 1000, 1100, 1200]),
                    "status": "aktif"
                })
        await db.workers.insert_many(workers)
    
        # ============ GÖREVLER ============
        task_types = ["toprak işleme", "ekim", "gübreleme", "ilaçlama", "sulama", "hasat", "nakliye"]
        statuses = ["planlı", "devam ediyor", "tamamlandı", "iptal"]
        tasks = []
        for _ in range(150):
            p = random.choice(parcels)
            task_date = datetime.now(timezone.utc) + timedelta(days=random.randint(-30, 30))
            tasks.append({
                "id": str(uuid.uuid4()), "task_type": random.choice(task_types),
                "parcel_id": p["id"], "farmer_id": p["farmer_id"], "region_id": p["region_id"],
                "scheduled_date": task_date.isoformat(),
                "status": random.choices(statuses, weights=[0.35, 0.15, 0.45, 0.05])[0],
                "machine_id": random.choice(machines)["id"] if random.random() > 0.3 else None,
                "worker_id": random.choice(workers)["id"] if random.random() > 0.3 else None,
                "notes": "", "created_at": now
            })
        await db.tasks.insert_many(tasks)
    
        # ============ KANTAR RANDEVU ============
        appts = []
        for _ in range(80):
            f = random.choice(farmers)
            appt_date = datetime.now(timezone.utc) + timedelta(days=random.randint(-10, 30))
            appts.append({
                "id": str(uuid.uuid4()), "farmer_id": f["id"], "region_id": f["region_id"],
                "scheduled_at": appt_date.isoformat(),
                "truck_plate": f"{random.choice(['06', '34', '35', '42', '38'])} {random.choice(['ABC', 'XYZ', 'KMN'])} {random.randint(100, 999)}",
                "estimated_ton": round(random.uniform(8, 28), 1),
                "actual_ton": round(random.uniform(7, 30), 1) if random.random() > 0.5 else None,
                "polar_oran": round(random.uniform(14.5, 18), 2) if random.random() > 0.5 else None,
                "status": random.choice(["planlı", "geldi", "tartıldı", "tamamlandı"])
            })
        await db.appointments.insert_many(appts)
    
        # ============ FİNANS HAREKETLERİ ============
        finance = []
        for f in farmers:
            finance.append({
                "id": str(uuid.uuid4()), "farmer_id": f["id"], "date": "2025-03-15",
                "type": "avans", "amount": -round(random.uniform(5000, 45000), 2),
                "description": "Tohum + gübre avansı"
            })
            if random.random() > 0.3:
                finance.append({
                    "id": str(uuid.uuid4()), "farmer_id": f["id"], "date": "2025-11-15",
                    "type": "hakediş", "amount": round(random.uniform(40000, 280000), 2),
                    "description": "Hasat hakediş"
                })
        await db.finance.insert_many(finance)

        # ============ IoT SENSÖRLER ============
        # Roadmap: "150 sensör IoT — Her sensörde Nem, Sıcaklık, Pil, Sinyal"
        iot_sensors = []
        sensor_parcels = random.sample(parcels, min(150, len(parcels)))
        for idx, p in enumerate(sensor_parcels):
            battery = random.randint(8, 100)
            signal = random.randint(1, 5)
            is_active = battery > 15 and random.random() > 0.05   # ~%5'i arızalı/offline
            iot_sensors.append({
                "id": str(uuid.uuid4()),
                "sensor_code": f"IOT-{idx+1:04d}",
                "parcel_id": p["id"],
                "parcel_code": p["parcel_code"],
                "farmer_id": p["farmer_id"],
                "region_id": p["region_id"],
                "type": random.choice(["nem_sicaklik", "toprak_nemi", "hava_istasyonu"]),
                "nem_pct": round(random.uniform(15, 85), 1),
                "sicaklik_c": round(random.uniform(8, 38), 1),
                "battery_pct": battery,
                "signal_strength": signal,               # 1-5 çubuk
                "status": "aktif" if is_active else random.choice(["offline", "bakım_gerekli"]),
                "last_reading_at": (datetime.now(timezone.utc) - timedelta(minutes=random.randint(1, 720))).isoformat(),
                "installed_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(30, 400))).isoformat(),
            })
        await db.iot_sensors.insert_many(iot_sensors)

        # ============ DRONE GÖREVLERİ ============
        # Roadmap: "45 Drone Görevi — Hastalık, Yabancı Ot, Su Stresi, Hava Durumu"
        drone_missions = []
        drone_finding_types = ["hastalık_tespiti", "yabancı_ot", "su_stresi", "genel_tarama"]
        mission_parcels = random.sample(parcels, min(45, len(parcels)))
        for idx, p in enumerate(mission_parcels):
            finding = random.choice(drone_finding_types)
            severity = random.choice(["düşük", "orta", "yüksek"]) if finding != "genel_tarama" else "yok"
            drone_missions.append({
                "id": str(uuid.uuid4()),
                "mission_code": f"DRN-{idx+1:03d}",
                "parcel_id": p["id"],
                "parcel_code": p["parcel_code"],
                "farmer_id": p["farmer_id"],
                "region_id": p["region_id"],
                "flight_date": (datetime.now(timezone.utc) - timedelta(days=random.randint(0, 45))).isoformat(),
                "pilot": random.choice(["Ahmet Yıldız (Saha)", "Otonom Uçuş", "Kemal Aydın (Saha)"]),
                "altitude_m": random.choice([50, 80, 100, 120]),
                "coverage_dekar": p["area_dekar"],
                "finding_type": finding,
                "severity": severity,
                "notes": {
                    "hastalık_tespiti": "Yaprak lekesi belirtileri tespit edildi, ziraat mühendisi kontrolü önerilir.",
                    "yabancı_ot": "Parsel kenarlarında yabancı ot yoğunluğu artışı gözlemlendi.",
                    "su_stresi": "Bitki örtüsünde su stresine işaret eden renk değişimi tespit edildi.",
                    "genel_tarama": "Anomali tespit edilmedi, gelişim normal seyrediyor.",
                }[finding],
                "status": "tamamlandı",
            })
        await db.drone_missions.insert_many(drone_missions)

        # ============ BİLDİRİMLER ============
        # Roadmap: "Her gün değişen bildirimler — Parsel KNY-742 → Nem kritik
        # seviyeye düştü" gibi SOMUT, gerçek parsel koduna bağlı mesajlar.
        notifs = []

        # 1) Genel sistem bildirimleri (hava durumu, kantar, avans, görev)
        types = ["hava_uyarısı", "sulama_hatırlatma", "kantar_randevu", "avans_bilgi", "görev_atandı"]
        titles = ["Don uyarısı - Konya bölgesi", "Sulama zamanı yaklaşıyor",
                  "Kantar randevunuz onaylandı", "Avans hesabınıza yatırıldı", "Yeni görev atandı"]
        for _ in range(30):
            notifs.append({
                "id": str(uuid.uuid4()), "type": random.choice(types),
                "title": random.choice(titles),
                "message": "Sistem tarafından otomatik oluşturuldu.",
                "channel": random.choice(["sms", "whatsapp", "push", "in_app"]),
                "status": random.choice(["gönderildi", "okundu", "beklemede"]),
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 200))).isoformat()
            })

        # 2) Riskli/düşük NDVI'lı parsellerden gerçek uyarılar
        risky_parcels = [p for p in parcels if p["risk_level"] in ("turuncu", "kirmizi")]
        for p in random.sample(risky_parcels, min(25, len(risky_parcels))):
            msg = random.choice([
                f"Parsel {p['parcel_code']} → Nem kritik seviyeye düştü.",
                f"Parsel {p['parcel_code']} → NDVI değeri düşüş gösteriyor, kontrol önerilir.",
                f"Parsel {p['parcel_code']} → Yabancı ot riski oluştu.",
            ])
            notifs.append({
                "id": str(uuid.uuid4()), "type": "risk_uyarisi", "title": "Parsel Risk Uyarısı",
                "message": msg, "parcel_id": p["id"], "parcel_code": p["parcel_code"],
                "channel": "in_app", "status": random.choice(["gönderildi", "okundu"]),
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 72))).isoformat()
            })

        # 3) Hasat/verim ile ilgili olumlu bildirimler (sağlıklı parseller)
        healthy_parcels = [p for p in parcels if p["risk_level"] == "yesil"]
        for p in random.sample(healthy_parcels, min(15, len(healthy_parcels))):
            pct = random.randint(3, 12)
            msg = random.choice([
                f"Parsel {p['parcel_code']} → Hasat için uygun dönem başladı.",
                f"Parsel {p['parcel_code']} → Beklenen verim %{pct} arttı.",
            ])
            notifs.append({
                "id": str(uuid.uuid4()), "type": "hasat_bilgi", "title": "Hasat / Verim Bilgisi",
                "message": msg, "parcel_id": p["id"], "parcel_code": p["parcel_code"],
                "channel": "in_app", "status": "gönderildi",
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 48))).isoformat()
            })

        await db.notifications.insert_many(notifs)
    
        return {
            "status": "seeded",
            "counts": {
                "users": len(admin_users) + len(farmer_user_records),
                "admin_users": len(admin_users),
                "farmer_login_accounts": len(farmer_user_records),
                "regions": len(regions), "farmers": len(farmers), "parcels": len(parcels),
                "contracts": len(contracts), "plantings": len(plantings), "yields": len(yields_list),
                "soil_samples": len(soil_samples), "machines": len(machines), "workers": len(workers),
                "tasks": len(tasks), "appointments": len(appts), "irrigation_events": len(irrigation_events),
                "iot_sensors": len(iot_sensors), "drone_missions": len(drone_missions),
                "risky_parcels": len(risky_parcels)
            },
            "demo_logins": {
                "super_admin": "admin@turkseker.com.tr / admin123",
                "fabrika_muduru": "ahmet.yilmaz@turkseker.com.tr / ahmet123",
                "ziraat_muhendisi": "mehmet.demir@turkseker.com.tr / mehmet123",
                "ciftci_ornek": "ts-00001@ciftci.tr / ciftci123  (her çiftçi member_no@ciftci.tr ile)"
            }
        }


    # ============ KÖK ENDPOINT (Sağlık kontrolü) ============
    @api_router.get("/")
    async def root():
        return {"app": APP_NAME, "full_name": APP_FULL_NAME, "version": APP_VERSION, "status": "ok"}


    @api_router.get("/health")
    async def health_check():
        """Kimlik dogrulamasiz, hafif liveness/readiness endpoint'i.

        PR-07 (kurulum sonrasi smoke test) ve Docker/Compose HEALTHCHECK
        tarafindan kullanilir. Kasitli olarak require_permission/current_user
        kullanmaz -- orkestrasyon katmani (Docker, k8s, load balancer) bu uca
        auth olmadan erisebilmeli. Hassas bilgi donmez (bkz. CLAUDE.md #3.1).
        """
        checks = {}
        overall_ok = True

        try:
            await raw_db.command("ping")
            checks["database"] = {"status": "ok"}
        except Exception as exc:  # noqa: BLE001
            overall_ok = False
            checks["database"] = {"status": "error", "detail": "veritabanina baglanilamadi"}

        return {
            "status": "healthy" if overall_ok else "unhealthy",
            "app": APP_NAME,
            "version": APP_VERSION,
            "checks": checks,
        }


    @api_router.get("/roles")
    async def list_roles(user=Depends(current_user)):
        """Rol hiyerarşisini ve etiketlerini döner (frontend'de yetki gösterimi için)."""
        return {"hierarchy": ROLE_HIERARCHY, "labels": ROLE_LABELS}


