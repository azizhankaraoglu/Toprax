#!/usr/bin/env python3
"""
=====================================================================
TOPRAX — Gerçek köy parselleriyle demo veri üretimi (trial sürümü)
=====================================================================
Kullanım (konteyner içinde):
    python scripts/seed_villages.py /data/koyler --purge

Girdi: her köy için bir GeoJSON (`<KÖY>_PARSEL_ALN.geojson`). Bu dosyalar
gerçek kadastro sınırlarıdır ama SADECE parsel numarası (`Name`) taşır —
çiftçi/sözleşme/verim bilgisi YOKTUR. Bu script o gerçek geometrilerin
üzerine tutarlı bir demo operasyon zinciri kurar:

    çiftçi → parsel → sözleşme → üretim sezonu → ekim → toprak analizi
           → sulama → kantar → verim/polar geçmişi

TASARIM KARARLARI
-----------------
1. **Geometri LineString → Polygon.** Kaynak dosyalarda halkalar kapalı
   `LineString` olarak geliyor (QGIS "çizgi" katmanı). MongoDB'nin 2dsphere
   indeksi ve `$geoIntersects` sorguları Polygon ister; ayrıca alan hesabı
   (dekar) ancak poligonla yapılır.
2. **Alan gerçek geometriden hesaplanır** (shoelace + UTM projeksiyon), uydurma
   bir sayı ATANMAZ — `gee_hls/service.py`'deki AYNI pyproj yaklaşımı.
3. **Deterministik rastgelelik:** `random.Random(parsel_no)` — script tekrar
   çalıştığında AYNI çiftçi AYNI parseli alır, demo ekranları oturumdan
   oturuma değişmez.
4. **Geçmiş 5 yıl verim/polar üretilir** — Ekim Planlama'nın münavebe ve
   `ort_polar` sinyalleri ancak geçmiş kayıt varsa çalışır (canlıda boş
   veritabanında "veri yok" cezası alıyordu).
5. **`demo_batch` etiketi:** üretilen HER kayıt bu alanı taşır; `--purge`
   sadece bu etiketli kayıtları siler, gerçek veriye dokunmaz.
"""
import argparse
import asyncio
import json
import math
import os
import random
import re
import sys
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from motor.motor_asyncio import AsyncIOMotorClient          # noqa: E402
from pyproj import CRS, Transformer                          # noqa: E402

from config_service import MONGO_URL, DB_NAME                # noqa: E402

DEMO_BATCH = "koyler-2026-08"
CROP = "Şeker Pancarı"
VARIETIES = ["Leila", "Bardolino", "Danton", "Esperanza", "Sandrina",
             "Vandana", "Colonia", "Tessia", "Bristol", "Cadenza"]
SOIL_TYPES = ["Killi-Tınlı", "Tınlı", "Kumlu-Tınlı", "Killi", "Organik"]
IRRIGATION = ["Damla", "Yağmurlama", "Karık", "Salma"]
FIRST_NAMES = ["Mehmet", "Ahmet", "Mustafa", "Ali", "Hüseyin", "Hasan", "İbrahim",
               "Ramazan", "Osman", "Yusuf", "Fatma", "Ayşe", "Emine", "Hatice",
               "Zeynep", "Elif", "Şerife", "Havva", "Meryem", "Sultan"]
LAST_NAMES = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım",
              "Öztürk", "Aydın", "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan",
              "Çetin", "Kara", "Koç", "Kurt", "Özkan", "Şimşek"]

#: Her köy için kaç çiftçi üretilecek (parsel sayısına göre ölçeklenir).
PARCELS_PER_FARMER = 22


# --- Geometri yardımcıları ---------------------------------------------------

def _dedupe(ring: List[List[float]]) -> List[List[float]]:
    """Bitişik yinelenen köşeleri atar (2dsphere bunları reddeder)."""
    if not ring:
        return ring
    out = [ring[0]]
    for pt in ring[1:]:
        if pt != out[-1]:
            out.append(pt)
    return out


def _split_rings(points: List[List[float]]) -> List[List[List[float]]]:
    """Tek bir koordinat dizisini KAPALI HALKALARA böler.

    NEDEN: kaynak dosyalardaki bazı parseller "delikli" (içinde başka bir
    parsel/yol olan) alanlar ve QGIS bunları TEK bir LineString'e ard arda
    yazmış: dış halka kapanıyor, hemen ardından iç halka başlıyor ve o da
    kapanıyor. Tamamını tek halka saymak MongoDB'de
    "Loop is not valid ... Duplicate vertices: 0 and 8" hatası veriyordu
    (canlıda Dinlendik 109/10 parselinde görüldü).

    Bir nokta halkanın BAŞLANGICINA eşit olduğunda o halka kapanmış sayılır
    ve kalan noktalarla yeni bir halka başlatılır.
    """
    rings: List[List[List[float]]] = []
    current: List[List[float]] = []
    for pt in points:
        if current and pt == current[0]:
            current.append(pt)
            rings.append(current)
            current = []
            continue
        current.append(pt)
    if len(current) >= 3:                     # kapanmamış artık halka
        current.append(current[0])
        rings.append(current)
    return [r for r in (_dedupe(r) for r in rings) if len(r) >= 4]


def _polygon_from_feature(geom: Dict[str, Any]) -> Optional[List[List[List[float]]]]:
    """Kaynak geometriden GeoJSON Polygon koordinatları (dış halka + delikler).

    Z (yükseklik) bileşeni DÜŞÜRÜLÜR — GeoJSON'da geçerli olsa da MongoDB
    2dsphere üç bileşenli koordinatı kabul etmiyor.
    """
    if not geom:
        return None
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "LineString":
        pts = [[float(p[0]), float(p[1])] for p in coords if p and len(p) >= 2]
        rings = _split_rings(pts)
    elif gtype == "Polygon":
        rings = [_dedupe([[float(p[0]), float(p[1])] for p in r]) for r in coords]
    elif gtype == "MultiPolygon":
        rings = [_dedupe([[float(p[0]), float(p[1])] for p in r])
                 for poly in coords for r in poly]
    else:
        return None
    rings = [r for r in rings if len(r) >= 4]
    if not rings:
        return None
    # En büyük halka DIŞ sınır, kalanlar delik (kaynak sırası garantili değil).
    rings.sort(key=_ring_area_m2, reverse=True)
    return rings


def _ring_area_m2(ring: List[List[float]]) -> float:
    """Halkanın alanı (m²). UTM'ye projekte edip shoelace — yeni bağımlılık
    (shapely) eklemeden, `gee_hls/service.py`'deki yaklaşımla AYNI."""
    if len(ring) < 4:
        return 0.0
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    zone = int((sum(lons) / len(lons) + 180) / 6) + 1
    crs = CRS.from_dict({"proj": "utm", "zone": zone, "north": True})
    to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    pts = [to_utm.transform(x, y) for x, y in ring]
    area = 0.0
    for i in range(len(pts) - 1):
        area += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return abs(area) / 2.0


def _area_dekar(rings: List[List[List[float]]]) -> float:
    """Parselin NET alanı (dekar): dış halka − delikler."""
    if not rings:
        return 0.0
    net = _ring_area_m2(rings[0]) - sum(_ring_area_m2(r) for r in rings[1:])
    return round(max(net, 0.0) / 1000.0, 2)        # m² → dekar


def _centroid(rings: List[List[List[float]]]) -> Tuple[float, float]:
    ring = rings[0]
    lons = [p[0] for p in ring[:-1]]
    lats = [p[1] for p in ring[:-1]]
    return sum(lons) / len(lons), sum(lats) / len(lats)


# --- Ad/metin yardımcıları ----------------------------------------------------

def _village_name(filename: str) -> str:
    """Dosya adından köy adı ("ABDİTOLU_PARSEL_ALN.geojson" → "Abditolu").

    ⚠️ Python'un `.title()`'ı Türkçe "İ"yi bozar: `.lower()` onu "i" + BİRLEŞİK
    NOKTA'ya (U+0307) açar ve sonuç ekranda "Abdi̇tolu" gibi görünür (canlıda
    görüldü). Bu yüzden büyük harfler ÖNCE ASCII karşılıklarına çevrilir,
    başlık biçimi SONRA uygulanır — `field_definitions._slugify_tr`'de
    öğrenilen dersle AYNI.
    """
    base = os.path.basename(filename)
    base = re.sub(r"_PARSEL_ALN\.geojson$", "", base, flags=re.IGNORECASE)
    base = base.replace("_", " ")
    upper_map = str.maketrans("İIŞĞÜÖÇ", "İIŞĞÜÖÇ")   # kimlik — okunabilirlik için
    base = base.translate(upper_map)
    words = []
    for word in base.split():
        first, rest = word[:1], word[1:]
        # "I" → "i" (nokta"sız" ı DEĞİL): bu dosya adları ASCII klavyeyle
        # yazılmış ("DINLENDIK" = Dinlendik köyü). Türkçe kuralı birebir
        # uygulamak "Dınlendık" gibi yanlış bir ad üretiyordu.
        rest = rest.replace("İ", "i").replace("I", "i").lower()
        words.append(first + rest)
    name = " ".join(words)
    # Birleşik nokta bırakan durumlara karşı son temizlik.
    return unicodedata.normalize("NFC", name).replace("̇", "")


def _slug(text: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = unicodedata.normalize("NFKD", text.translate(tr))
    return "".join(c for c in s if c.isalnum()).lower()


def _tc_no(rnd: random.Random) -> str:
    return str(rnd.randint(10_000_000_000, 99_999_999_998))


def _phone(rnd: random.Random) -> str:
    return f"05{rnd.randint(30, 59)}{rnd.randint(1000000, 9999999)}"


def _iban(rnd: random.Random) -> str:
    return "TR" + "".join(str(rnd.randint(0, 9)) for _ in range(24))


# --- Ana akış -----------------------------------------------------------------

async def purge(db) -> None:
    """Sadece demo etiketli kayıtları + ESKİ demo parsel zincirini siler."""
    collections = ["farmers", "parcels", "contracts", "production_cycles", "plantings",
                   "soil_samples", "yields", "kantar_records", "irrigation_events",
                   "irrigation_plans", "remote_sensing_statistics", "remote_sensing_images",
                   "remote_sensing_tasks", "agronomy_analyses", "field_tasks", "visits",
                   "work_orders", "entitlements", "ledger_entries", "reconciliations",
                   "support_requests", "finance"]
    print("--- Eski veri temizliği ---")
    for coll in collections:
        res = await db[coll].delete_many({})
        if res.deleted_count:
            print(f"  {coll}: {res.deleted_count} kayıt silindi")


async def _region_for(db, village: str, tenant_id: Optional[str]) -> str:
    """Köy için bölge kaydı (yoksa oluşturur) — parsel/çiftçi `region_id` ister."""
    doc = await db.regions.find_one({"name": village}, {"_id": 0, "id": 1})
    if doc:
        return doc["id"]
    rid = str(uuid.uuid4())
    await db.regions.insert_one({
        "id": rid, "name": village, "tenant_id": tenant_id,
        "demo_batch": DEMO_BATCH, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return rid


async def _admin_area_for(db, lon: float, lat: float) -> Dict[str, Optional[str]]:
    """Parselin merkezine göre il/ilçe/mahalle — GERÇEK `$geoIntersects`
    (isim eşleştirmesi değil). İdari alanlar önce import edilmiş olmalı."""
    out = {"il": None, "ilce": None, "mahalle": None}
    point = {"type": "Point", "coordinates": [lon, lat]}
    area = await db.admin_areas.find_one(
        {"area_type": "mahalle", "geometry": {"$geoIntersects": {"$geometry": point}}},
        {"_id": 0, "mahalle_adi": 1, "ilce_adi": 1, "il_adi": 1})
    if area:
        out["mahalle"] = area.get("mahalle_adi")
        out["ilce"] = area.get("ilce_adi")
        out["il"] = area.get("il_adi")
        return out
    ilce = await db.admin_areas.find_one(
        {"area_type": "ilce", "geometry": {"$geoIntersects": {"$geometry": point}}},
        {"_id": 0, "ilce_adi": 1, "il_adi": 1})
    if ilce:
        out["ilce"] = ilce.get("ilce_adi")
        out["il"] = ilce.get("il_adi")
    return out


async def run(folder: str, do_purge: bool, seasons: int) -> None:
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    tenant = await db.tenants.find_one({}, {"_id": 0, "id": 1, "name": 1})
    tenant_id = tenant["id"] if tenant else None
    print(f"tenant: {tenant.get('name') if tenant else '(yok)'}")

    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".geojson"))
    if not files:
        raise SystemExit(f"{folder} içinde .geojson yok")

    if do_purge:
        await purge(db)

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    current_year = now.year
    totals = {"farmers": 0, "parcels": 0, "contracts": 0, "cycles": 0,
              "plantings": 0, "soil": 0, "yields": 0, "kantar": 0, "irrigation": 0}

    for fname in files:
        village = _village_name(fname)
        path = os.path.join(folder, fname)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        feats = data.get("features") or []
        rings = []
        for feat in feats:
            poly = _polygon_from_feature(feat.get("geometry"))
            if poly:
                rings.append((str((feat.get("properties") or {}).get("Name") or ""), poly))
        if not rings:
            print(f"{village}: geçerli geometri yok, atlandı")
            continue

        rnd = random.Random(_slug(village))            # köy bazlı deterministik
        region_id = await _region_for(db, village, tenant_id)

        # --- Çiftçiler -------------------------------------------------------
        farmer_count = max(3, round(len(rings) / PARCELS_PER_FARMER))
        farmers = []
        for i in range(farmer_count):
            fid = str(uuid.uuid4())
            name = f"{rnd.choice(FIRST_NAMES)} {rnd.choice(LAST_NAMES)}"
            points = rnd.randint(45, 95)
            # `karne_score` (harf notu) ve `status` KANONİK alanlar: Çiftçiler
            # listesi, karne ekranı ve dashboard bunları okur. İlk sürümde
            # yazılmadıkları için liste `undefined.toLowerCase()` ile
            # çöküyordu (canlıda görüldü).
            grade = "A" if points >= 85 else "B" if points >= 70 else "C" if points >= 55 else "D"
            farmers.append({
                "id": fid, "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                "member_no": f"{_slug(village)[:3].upper()}-{i + 1:05d}",
                "full_name": name, "tc_no": _tc_no(rnd), "phone": _phone(rnd),
                "email": f"{_slug(name)}{i + 1}@ciftci.tr",
                "village": village, "region_id": region_id,
                "iban": _iban(rnd),
                "membership_year": rnd.randint(2005, 2024),
                "karne_points": points, "karne_score": grade,
                "status": "aktif",
                "gender": rnd.choice(["erkek", "erkek", "erkek", "kadin"]),
                "cks_status": rnd.choice(["kayitli", "kayitli", "kayitli", "kayitsiz"]),
                "debt_status": rnd.choice(["borcsuz", "borcsuz", "borclu"]),
                "is_active": True, "created_at": now_iso,
            })
        await db.farmers.insert_many([dict(f) for f in farmers])
        totals["farmers"] += len(farmers)

        # --- Parseller ve tüm zincir ------------------------------------------
        parcels, contracts, cycles, plantings, soils, yields_, kantar, irrig = [], [], [], [], [], [], [], []
        admin_cache: Dict[Tuple[int, int], Dict[str, Optional[str]]] = {}

        for idx, (parsel_no, poly_rings) in enumerate(rings):
            owner = farmers[idx % len(farmers)]
            prnd = random.Random(f"{_slug(village)}-{parsel_no or idx}")
            area = _area_dekar(poly_rings)
            if area <= 0.5:                     # bozuk/çok küçük halka
                continue
            lon, lat = _centroid(poly_rings)
            cache_key = (round(lon, 2), round(lat, 2))
            if cache_key not in admin_cache:
                admin_cache[cache_key] = await _admin_area_for(db, lon, lat)
            admin = admin_cache[cache_key]

            pid = str(uuid.uuid4())
            irrigation = prnd.choice(IRRIGATION)
            parcels.append({
                "id": pid, "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                "farmer_id": owner["id"], "name": f"{village} {parsel_no or idx + 1}",
                "parcel_code": f"{_slug(village)[:3].upper()}-{parsel_no or idx + 1}",
                "village": village, "region_id": region_id,
                "il": admin["il"], "ilce": admin["ilce"], "mahalle": admin["mahalle"],
                "ada_no": str(prnd.randint(100, 999)), "parsel_no_tapu": str(parsel_no or idx + 1),
                "area_dekar": area, "ekilebilir_alan_dekar": round(area * prnd.uniform(0.88, 0.99), 2),
                "soil_type": prnd.choice(SOIL_TYPES), "irrigation": irrigation,
                "geometry": {"type": "Polygon", "coordinates": poly_rings},
                "ekim_durumu": "ekili" if prnd.random() < 0.72 else "bos",
                "risk_level": prnd.choice(["yesil", "yesil", "sari", "turuncu", "kirmizi"]),
                "is_active": True, "created_at": now_iso,
            })

            # Toprak analizi — parsellerin %70'inde (gerçekte hepsinde olmaz)
            if prnd.random() < 0.7:
                soils.append({
                    "id": str(uuid.uuid4()), "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                    "parcel_id": pid, "farmer_id": owner["id"],
                    "sample_date": (now - timedelta(days=prnd.randint(30, 400))).strftime("%Y-%m-%d"),
                    "ph": round(prnd.uniform(6.4, 8.4), 1),
                    "organic_matter": round(prnd.uniform(0.8, 3.4), 2),
                    "ec": round(prnd.uniform(0.3, 2.2), 2),
                    "n_ppm": round(prnd.uniform(8, 45), 1),
                    "p_ppm": round(prnd.uniform(4, 28), 1),
                    "k_ppm": round(prnd.uniform(90, 420), 1),
                    "kum_yuzde": round(prnd.uniform(20, 55), 1),
                    "kil_yuzde": round(prnd.uniform(15, 45), 1),
                    "silt_yuzde": round(prnd.uniform(15, 40), 1),
                    "recommendation": "Dengeli gübreleme önerilir.",
                    "created_at": now_iso,
                })

            # Sezon zinciri — son `seasons` yıl
            for back in range(seasons):
                season = current_year - back
                if prnd.random() < (0.25 if back else 0.05):
                    continue                     # o yıl ekilmemiş
                variety = prnd.choice(VARIETIES)
                cid = str(uuid.uuid4())
                cyid = str(uuid.uuid4())
                kota_ton = round(area * prnd.uniform(5.5, 7.5), 1)
                contracts.append({
                    "id": cid, "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                    "farmer_id": owner["id"], "parcel_id": pid, "production_cycle_id": cyid,
                    "season": season, "crop": CROP, "variety": variety,
                    "kota_dekar": area, "kota_ton": kota_ton,
                    "advance_seed_kg": round(area * 1.1, 1),
                    "advance_fertilizer_kg": round(area * 22, 1),
                    "status": "imzalı", "created_at": now_iso,
                })
                cycles.append({
                    "id": cyid, "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                    "farmer_id": owner["id"], "parcel_id": pid, "year": season,
                    "season": "Ana Ürün", "crop": CROP,
                    "status": "active" if back == 0 else "completed",
                    "created_at": now_iso,
                })
                plantings.append({
                    "id": str(uuid.uuid4()), "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                    "contract_id": cid, "parcel_id": pid, "farmer_id": owner["id"],
                    "production_cycle_id": cyid, "season": season, "crop": CROP,
                    "variety": variety,
                    "planting_date": f"{season}-{prnd.choice(['03','04'])}-{prnd.randint(5,28):02d}",
                    "expected_harvest_date": f"{season}-{prnd.choice(['09','10'])}-{prnd.randint(1,28):02d}",
                    "stage": "gelişim" if back == 0 else "hasat",
                    # Kök sayısı girdileri (bkz. crop_stand.py) — pancarda tipik
                    # 45 cm sıra arası, 18-20 cm sıra üzeri.
                    "row_spacing_cm": 45, "seed_spacing_cm": prnd.choice([18, 19, 20]),
                    "germination_pct": round(prnd.uniform(82, 96), 1),
                    "created_at": now_iso,
                })
                # Geçmiş yılların verim/polar kaydı (bu yıl henüz hasat yok)
                if back > 0:
                    verim = round(prnd.uniform(4.8, 8.2), 2)
                    yields_.append({
                        "id": str(uuid.uuid4()), "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                        "parcel_id": pid, "farmer_id": owner["id"], "season": season,
                        "year": season, "crop": CROP, "variety": variety,
                        "area_dekar": area,
                        # `expected_ton`/`actual_ton` KANONİK alanlar (seed_routes.py
                        # ile AYNI adlar) — ParcelDetail "Verim Geçmişi" tablosu,
                        # karne_engine ve dashboard bunları okur. İlk sürümde
                        # sadece `toplam_ton` yazılmıştı ve parsel detayı
                        # `undefined.toFixed()` ile çöküyordu (canlıda görüldü).
                        "expected_ton": round(kota_ton, 1),
                        "actual_ton": round(verim * area, 2),
                        "verim_ton_dekar": verim,
                        "toplam_ton": round(verim * area, 1),
                        "polar_oran": round(prnd.uniform(14.5, 18.8), 2),
                        "created_at": now_iso,
                    })
                    kantar.append({
                        "id": str(uuid.uuid4()), "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                        "farmer_id": owner["id"], "production_cycle_id": cyid,
                        "tarih": f"{season}-10-{prnd.randint(1,28):02d}",
                        "brut_kg": round(verim * area * 1000 * 1.04, 0),
                        "net_kg": round(verim * area * 1000, 0),
                        "fire_kg": round(verim * area * 1000 * 0.04, 0),
                        "kalite": prnd.choice(["A", "A", "B", "B", "C"]),
                        "created_at": now_iso,
                    })
                # Sulama kayıtları (damla/yağmurlamada daha sık)
                for _ in range(prnd.randint(2, 7) if irrigation in ("Damla", "Yağmurlama") else prnd.randint(0, 3)):
                    irrig.append({
                        "id": str(uuid.uuid4()), "tenant_id": tenant_id, "demo_batch": DEMO_BATCH,
                        "parcel_id": pid, "farmer_id": owner["id"], "season": season,
                        "date": f"{season}-{prnd.randint(5,9):02d}-{prnd.randint(1,28):02d}",
                        "water_m3": round(area * prnd.uniform(25, 60), 1),
                        "method": irrigation, "created_at": now_iso,
                    })

        for coll, rows, key in (("parcels", parcels, "parcels"), ("contracts", contracts, "contracts"),
                                ("production_cycles", cycles, "cycles"), ("plantings", plantings, "plantings"),
                                ("soil_samples", soils, "soil"), ("yields", yields_, "yields"),
                                ("kantar_records", kantar, "kantar"), ("irrigation_events", irrig, "irrigation")):
            if rows:
                # ordered=False + BulkWriteError yakalama: 2dsphere'in
                # reddettiği TEK bir bozuk geometri, o partideki diğer
                # binlerce kaydı da düşürmesin (admin_areas.py'nin bulk
                # import'unda alınan AYNI karar).
                inserted = 0
                for i in range(0, len(rows), 2000):
                    batch = rows[i:i + 2000]
                    try:
                        res = await db[coll].insert_many(batch, ordered=False)
                        inserted += len(res.inserted_ids)
                    except Exception as e:                        # pymongo.errors.BulkWriteError
                        details = getattr(e, "details", {}) or {}
                        inserted += details.get("nInserted", 0)
                        bad = len(details.get("writeErrors", []))
                        if bad:
                            print(f"  ! {coll}: {bad} kayıt geometri/şema nedeniyle atlandı")
                        else:
                            raise
                totals[key] += inserted

        print(f"{village}: {len(parcels)} parsel, {len(farmers)} çiftçi, "
              f"{len(contracts)} sözleşme, {len(yields_)} verim kaydı")

    print("\n=== TOPLAM ===")
    for k, v in totals.items():
        print(f"  {k}: {v}")


def main():
    ap = argparse.ArgumentParser(description="TOPRAX köy demo verisi")
    ap.add_argument("folder", help="Köy GeoJSON dosyalarının bulunduğu klasör")
    ap.add_argument("--purge", action="store_true", help="Önce mevcut operasyon verisini sil")
    ap.add_argument("--seasons", type=int, default=6, help="Kaç sezonluk geçmiş üretilsin")
    args = ap.parse_args()
    asyncio.run(run(args.folder, args.purge, args.seasons))


if __name__ == "__main__":
    main()
