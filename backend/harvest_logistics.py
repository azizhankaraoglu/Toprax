"""
=====================================================================
TOPRAX — Hasat & Kampanya Lojistiği (fabrika rolü)
=====================================================================
Kullanıcı: "Fabrika rolünü ekleyip entegre edebiliriz."

Şeker fabrikasının kampanya planlaması bugün Excel'le yapılan bir iştir:
hangi parsel hangi hafta sökülecek, kantara ne zaman gelecek, günlük işleme
kapasitesi aşılıyor mu. Bu modül aynı işi ÖLÇÜLMÜŞ verilerle yapar:

  parselin olgunlaşma endeksi + polar tahmini  (polar_engine)
  + hava penceresi (yağış/don)                 (weather)
  + sözleşme kotası                            (contracts)
  + günlük fabrika işleme kapasitesi           (ayar)
  ------------------------------------------------------
  = haftalık söküm/teslim çizelgesi + kantar randevusu

TASARIM: Çizelge KAYDEDİLMEZ, her çağrıda CANLI hesaplanır (ufyd/dashboard
ve field-ops/dashboard ile AYNI desen) — parselin olgunluğu her uydu
ölçümünde değişir, donmuş bir plan hızla yanlışa döner. Kabul edilen
randevular ise `appointments` koleksiyonuna GERÇEK kayıt olarak yazılır.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

#: Fabrika ayarları — `factory_settings` tek dokümanında saklanır
#: (karne_parameters / fire-scan-settings ile AYNI tek-doküman ayar deseni).
DEFAULT_FACTORY = {
    "gunluk_isleme_kapasitesi_ton": 12000,
    "kampanya_baslangic": "09-15",       # AA-GG
    "kampanya_bitis": "12-31",
    "gunluk_calisma_saati": 24,
    "kantar_sayisi": 4,
    "kantar_saatlik_arac": 12,
}


def _parse_md(value: str, year: int) -> date:
    month, day = value.split("-")
    return date(year, int(month), int(day))


def rank_parcels_for_harvest(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Söküm sırası: önce olgunlaşmış + polar zirvesindeki parseller.

    Sıralama ölçütü tek bir sayı değil, üç ölçünün birleşimi:
      * olgunlaşma endeksi (yüksek → hazır)
      * polar tahmini (yüksek → fabrika için değerli, bekletmenin maliyeti var)
      * kök donma riski (yüksek → erken alınmalı)
    """
    for r in rows:
        idx = r.get("olgunlasma_endeksi") or 0
        polar = r.get("beklenen_polar") or 0
        risk = 10 if r.get("don_riski") else 0
        r["oncelik_puani"] = round(idx * 0.6 + (polar - 14) * 6 + risk, 1)
    return sorted(rows, key=lambda r: r["oncelik_puani"], reverse=True)


def build_schedule(rows: List[Dict[str, Any]], settings: Dict[str, Any],
                   year: int) -> Dict[str, Any]:
    """Günlük kapasiteyi aşmayacak şekilde söküm/teslim çizelgesi."""
    capacity = settings.get("gunluk_isleme_kapasitesi_ton") or DEFAULT_FACTORY["gunluk_isleme_kapasitesi_ton"]
    start = _parse_md(settings.get("kampanya_baslangic") or DEFAULT_FACTORY["kampanya_baslangic"], year)
    end = _parse_md(settings.get("kampanya_bitis") or DEFAULT_FACTORY["kampanya_bitis"], year)

    ranked = rank_parcels_for_harvest(rows)
    plan: List[Dict[str, Any]] = []
    overflow: List[Dict[str, Any]] = []

    # ================= GÜN BAZLI KAPASİTE DEFTERİ (2026-08-19 düzeltmesi) ======
    # ÖNCEDEN tek bir `current` imleci vardı ve ASLA GERİ GİTMİYORDU. Parseller
    # `rank_parcels_for_harvest` ile ÖNCELİĞE göre sıralı (tarihe göre değil),
    # bu yüzden listede geç olgunlaşan bir parsel (23 Ekim) işlendikten sonra
    # imleç oraya sabitleniyor ve ARDINDAN gelen ERKEN olgunlaşan parseller
    # (20 Eylül) de 23 Ekim'e itiliyordu. Canlıda sonuç: 43. haftaya 117 parsel
    # / 32.468 ton yığılması.
    #
    # Artık her gün için kullanılan tonaj ayrı tutuluyor; her parsel KENDİ
    # olgunluk tarihinden itibaren kapasitesi müsait İLK günü buluyor. Böylece
    # erken olgunlaşan parsel erken güne yerleşir, öncelik sırası yalnızca
    # aynı güne yarışanlar arasında belirleyici olur.
    used_by_day: Dict[date, float] = {}

    for r in ranked:
        tonnage = r.get("tahmini_ton") or 0

        # Parselin kendi olgunluk tarihi kampanya başından sonraysa oradan başla
        cursor = start
        ready = r.get("tahmini_olgunluk_tarihi")
        if ready:
            try:
                ready_d = date.fromisoformat(ready)
                if ready_d > cursor:
                    cursor = ready_d
            except ValueError:
                pass

        # Kapasitesi yeten ilk günü ara
        placed = False
        while cursor <= end:
            if used_by_day.get(cursor, 0.0) + tonnage <= capacity:
                placed = True
                break
            cursor += timedelta(days=1)

        if not placed:
            overflow.append({**r, "sebep": "Kampanya penceresi doldu"})
            continue

        used_by_day[cursor] = used_by_day.get(cursor, 0.0) + tonnage
        plan.append({
            "parcel_id": r.get("parcel_id"), "parsel": r.get("parsel"),
            "ciftci": r.get("ciftci"), "koy": r.get("koy"),
            "planlanan_tarih": cursor.isoformat(),
            "tahmini_ton": round(tonnage, 1),
            "beklenen_polar": r.get("beklenen_polar"),
            "olgunlasma_endeksi": r.get("olgunlasma_endeksi"),
            "oncelik_puani": r.get("oncelik_puani"),
            "hafta": cursor.isocalendar()[1],
        })

    # Plan takvim sırasına alınır — çizelge bir ZAMAN çizelgesidir; öncelik
    # sırası yerleştirmede zaten kullanıldı. (Söküm ekranı isterse polara göre
    # yeniden sıralıyor, bkz. HasatLojistigi.jsx `sortedPlan`.)
    plan.sort(key=lambda p: p["planlanan_tarih"])

    by_week: Dict[int, Dict[str, Any]] = {}
    for p in plan:
        w = by_week.setdefault(p["hafta"], {"hafta": p["hafta"], "parsel_sayisi": 0,
                                            "toplam_ton": 0.0, "ortalama_polar": []})
        w["parsel_sayisi"] += 1
        w["toplam_ton"] += p["tahmini_ton"]
        if p.get("beklenen_polar"):
            w["ortalama_polar"].append(p["beklenen_polar"])
    haftalik = []
    for w in sorted(by_week.values(), key=lambda x: x["hafta"]):
        polars = w.pop("ortalama_polar")
        w["toplam_ton"] = round(w["toplam_ton"], 1)
        w["ortalama_polar"] = round(sum(polars) / len(polars), 2) if polars else None
        haftalik.append(w)

    # Kapasite kullanım özeti — çizelgenin gerçekten kapasiteye uyduğunun
    # görünür kanıtı (aşım varsa burada belli olur).
    gunluk = [{"tarih": d.isoformat(), "ton": round(t, 1),
               "doluluk_yuzde": round(t / max(capacity, 1) * 100, 1)}
              for d, t in sorted(used_by_day.items())]

    return {
        "kampanya": {"baslangic": start.isoformat(), "bitis": end.isoformat(),
                     "gunluk_kapasite_ton": capacity},
        "plan": plan,
        "haftalik_ozet": haftalik,
        "gunluk_doluluk": gunluk,
        "kullanilan_gun_sayisi": len(gunluk),
        "kapsam_disi": overflow,
        "toplam_ton": round(sum(p["tahmini_ton"] for p in plan), 1),
    }


async def collect_harvest_rows(db, season: int, limit: int = 400) -> List[Dict[str, Any]]:
    """Sezonun sözleşmeli parsellerini olgunluk/polar tahminleriyle toplar."""
    from polar_engine import analyze_parcel_harvest

    contracts = await db.contracts.find(
        {"season": season, "status": {"$ne": "iptal"}}, {"_id": 0}).limit(limit).to_list(limit)
    rows: List[Dict[str, Any]] = []
    farmers_cache: Dict[str, str] = {}

    for c in contracts:
        parcel = await db.parcels.find_one({"id": c.get("parcel_id")}, {"_id": 0})
        if not parcel:
            continue
        fid = parcel.get("farmer_id")
        if fid and fid not in farmers_cache:
            f = await db.farmers.find_one({"id": fid}, {"_id": 0, "full_name": 1})
            farmers_cache[fid] = (f or {}).get("full_name") or "—"
        analysis = await analyze_parcel_harvest(db, parcel, season)
        window = analysis.get("sokum_penceresi") or {}
        rows.append({
            "parcel_id": parcel["id"], "parsel": parcel.get("name"),
            "koy": parcel.get("village"), "ciftci": farmers_cache.get(fid, "—"),
            "alan_dekar": parcel.get("area_dekar"),
            "tahmini_ton": c.get("kota_ton"),
            "beklenen_polar": window.get("beklenen_polar"),
            "olgunlasma_endeksi": window.get("olgunlasma_endeksi"),
            "tahmini_olgunluk_tarihi": window.get("tahmini_olgunluk_tarihi"),
            "don_riski": bool(window.get("engeller")),
        })
    return rows


class AppointmentRequest(BaseModel):
    parcel_id: str
    tarih: str
    saat: Optional[str] = None
    tahmini_ton: Optional[float] = None
    notlar: Optional[str] = None


def register_harvest_logistics_routes(api_router, db, current_user, require_permission,
                                      log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    def _now():
        return datetime.now(timezone.utc).isoformat()

    @api_router.get("/harvest-logistics/settings")
    async def get_settings(user=Depends(require_permission("parcels:view"))):
        doc = await db.factory_settings.find_one({"key": "default"}, {"_id": 0})
        return (doc or {}).get("settings") or DEFAULT_FACTORY

    @api_router.put("/harvest-logistics/settings")
    async def update_settings(body: Dict[str, Any], request: Request,
                              user=Depends(require_permission("settings:fields_manage"))):
        settings = {**DEFAULT_FACTORY, **{k: v for k, v in body.items() if k in DEFAULT_FACTORY}}
        await db.factory_settings.update_one({"key": "default"},
                                             {"$set": {"key": "default", "settings": settings,
                                                       "updated_at": _now()}}, upsert=True)
        await log_audit(db, user, action="update", entity="factory_settings",
                        entity_id="default", new_value=settings, request=request)
        return settings

    @api_router.get("/harvest-logistics/schedule")
    async def schedule(season: Optional[int] = None, limit: int = 200,
                       user=Depends(require_permission("parcels:view"))):
        """Haftalık söküm/teslim çizelgesi — CANLI hesaplanır.

        `limit` bilinçli olarak düşük: her parsel için uydu/olgunluk analizi
        çalıştığından 200 parsel bile birkaç saniye sürer. Kapsam dışı kalan
        parsel sayısı yanıtta AÇIKÇA bildirilir (sessiz kırpma YOK).
        """
        season = season or date.today().year
        doc = await db.factory_settings.find_one({"key": "default"}, {"_id": 0})
        settings = (doc or {}).get("settings") or DEFAULT_FACTORY
        total = await db.contracts.count_documents({"season": season, "status": {"$ne": "iptal"}})
        rows = await collect_harvest_rows(db, season, limit)
        result = build_schedule(rows, settings, season)
        result["kapsam"] = {"islenen_sozlesme": len(rows), "toplam_sozlesme": total,
                            "truncated": total > len(rows)}
        return result

    @api_router.post("/harvest-logistics/appointments")
    async def create_appointment(body: AppointmentRequest, request: Request,
                                 user=Depends(require_permission("parcels:edit"))):
        """Çizelgeden kantar randevusu üretir — mevcut `appointments` koleksiyonuna."""
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        doc = {
            "id": str(uuid.uuid4()), "parcel_id": body.parcel_id,
            "farmer_id": parcel.get("farmer_id"),
            "tip": "kantar_teslim", "tarih": body.tarih, "saat": body.saat,
            "tahmini_ton": body.tahmini_ton, "notlar": body.notlar,
            "status": "planlandi", "kaynak": "hasat_lojistigi",
            "created_at": _now(),
        }
        await db.appointments.insert_one(dict(doc))
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="appointment",
                        entity_id=doc["id"], new_value={"parcel_id": body.parcel_id,
                                                        "tarih": body.tarih}, request=request)
        return doc
