"""
TOPRAX Remote Sensing — Ekili / Söküm Durumu Tespiti (#2)

Bir parselin "ekili mi / söküldü mü" durumunu UYDU (NDVI) + MANUEL (ekim
kaydı) sinyallerini BİRLEŞTİREREK belirler ve parsel dokümanına TARİH DAMGALI
yazar. Eşikler parametrik (season_parameters, B3): `ndvi_ekili_esigi` /
`ndvi_sokum_esigi`.

Mantık:
  - Uydu: sezon içinde NDVI zirvesi `ndvi_ekili_esigi`'yi aştıysa "ekildi/gelişti";
    yüksekten `ndvi_sokum_esigi` altına düştüyse "söküldü/hasat" sinyali.
  - Manuel: parselde aktif bir ekim kaydı (plantings) varsa "ekili".
  - Çelişki/kaynak: `crop_status_source` = uydu | manuel | uydu+manuel | veri_yok.

Sonuç alanları (parsel dokümanında, top-level — filtre/aggregate kolay):
  ekim_durumu ∈ {ekili, sokuldu, ekili_degil}, son_ndvi, crop_status_source,
  crop_status_date.
"""
from datetime import datetime, timezone


def _now():
    return datetime.now(timezone.utc).isoformat()


async def update_crop_status(db, parcel: dict, series=None) -> dict:
    """Parselin ekili/söküm durumunu hesaplar + parsel dokümanına yazar.
    `series` verilmezse en güncel remote_sensing_statistics'ten okunur.
    EOSDA ÇAĞRISI YAPMAZ (yalnızca DB) — toplu recompute için güvenli."""
    pid = parcel.get("id")
    season = parcel.get("active_season") or datetime.now(timezone.utc).year
    crop = parcel.get("current_crop") or "Şeker Pancarı"

    from season_parameters import get_season_params
    params = await get_season_params(db, season, crop) or {}
    ekili_esik = float(params.get("ndvi_ekili_esigi", 0.55))
    sokum_esik = float(params.get("ndvi_sokum_esigi", 0.25))

    if series is None:
        stat = await db.remote_sensing_statistics.find_one(
            {"parcel_id": pid}, {"_id": 0}, sort=[("created_at", -1)])
        series = (stat or {}).get("series") or []
    vals = [p["ndvi"] for p in series if p.get("ndvi") is not None]
    latest = vals[-1] if vals else (parcel.get("remote_sensing") or {}).get("last_ndvi")
    peak = max(vals) if vals else None

    planting = await db.plantings.find_one(
        {"parcel_id": pid, "is_active": {"$ne": False}}, {"_id": 0}, sort=[("created_at", -1)])
    manual_planted = bool(planting)

    sat_high = peak is not None and peak >= ekili_esik
    sat_now_low = latest is not None and latest <= sokum_esik
    was_planted = manual_planted or sat_high or (latest is not None and latest >= ekili_esik)
    is_removed = (sat_high or manual_planted) and sat_now_low

    if is_removed:
        durum = "sokuldu"
    elif was_planted:
        durum = "ekili"
    else:
        durum = "ekili_degil"

    sat_signal = latest is not None
    if manual_planted and sat_signal:
        src = "uydu+manuel"
    elif sat_signal:
        src = "uydu"
    elif manual_planted:
        src = "manuel"
    else:
        src = "veri_yok"

    await db.parcels.update_one({"id": pid}, {"$set": {
        "ekim_durumu": durum,
        "son_ndvi": round(float(latest), 3) if latest is not None else None,
        "crop_status_source": src,
        "crop_status_date": _now(),
    }})
    return {"parcel_id": pid, "ekim_durumu": durum, "son_ndvi": latest, "source": src}


async def recompute_all(db) -> dict:
    """TÜM aktif parseller için ekili/söküm durumunu (manuel + son NDVI ile,
    EOSDA'sız) yeniden hesaplar. Dashboard bunu besler."""
    counts = {"ekili": 0, "sokuldu": 0, "ekili_degil": 0}
    cursor = db.parcels.find({"is_active": {"$ne": False}}, {"_id": 0})
    total = 0
    async for parcel in cursor:
        r = await update_crop_status(db, parcel)
        counts[r["ekim_durumu"]] = counts.get(r["ekim_durumu"], 0) + 1
        total += 1
    return {"processed": total, "counts": counts}
