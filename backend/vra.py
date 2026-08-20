"""
=====================================================================
Toprax — VRA (Değişken Oranlı Uygulama / Variable Rate Application)
=====================================================================
OTURUM-DEVAM-19082026.md madde 9: "zon haritası → shapefile/ISOXML
dışa aktarma".

DÜRÜST SINIR (crop_classification.py'nin "motor doğru, veri kısıtı
dürüst" ilkesiyle AYNI): sistemde parsel İÇİ (sub-field) çözünürlükte
bir raster/nokta bulutu YOK — `parcels.ndvi_latest` ve toprak analizleri
(`soil_samples.n_ppm/p_ppm/k_ppm`) PARSEL bazlı tekil değerlerdir. Bu
yüzden VRA burada PARSEL GRANÜLERİTESİNDE çalışır: her "zon" bir
parseldir, sabit oranlı (constant-rate) bir uygulama haritası üretir —
tek bir parsel içinde noktadan noktaya değişen GERÇEK bir alt-alan
zonu ÜRETMEZ (üretirse UYDURMA veri olurdu). Bu, sensör çözünürlüğü
sınırlı olan gerçek VRA sistemlerinde de sık kullanılan meşru bir
sadeleştirmedir (parsel = en küçük adreslenebilir tarla birimi).

Sınıflandırma: seçilen sinyalin (NDVI / N-P-K) parsel değerleri EŞİT
ARALIK (equal-interval, min-max/3) yöntemiyle 3 sınıfa (düşük/orta/
yüksek) ayrılır — tercile/quantile YERİNE bilinçli olarak equal-interval
seçildi: kullanıcıya "bu parsel neden bu sınıfta" sorusuna min-max
aralığına göre sezgisel bir cevap verir. Sinyali eksik olan parseller
`veri_yok` sınıfına düşer, RATE ATANMAZ (uydurma oran YOK) — motoru
gerçek veri eksikliğinde SESSİZCE yanlış bir oran üretmez.

Rate (uygulama oranı) her sınıf için KULLANICI belirler (`zone_rates`)
— motor agronomik bir varsayımda (ör. "düşük NDVI = daha çok gübre")
BULUNMAZ, bu karar kullanıcının/mühendisin alan bilgisidir.

Dışa aktarım — İKİ format:
- Shapefile (.shp/.shx/.dbf, zip): `geo_import.py`'nin ZATEN bağımlılığı
  olan `pyshp` kullanılır (yeni bir kütüphane EKLENMEDİ). Her parsel
  poligonu + `RATE`/`ZONE`/`PARCEL` DBF alanlarıyla, çoğu traktör/
  gübre dağıtıcı terminali (Trimble, John Deere Operations Center, vb.)
  bu formatı doğrudan içe aktarabilir.
- ISOXML (TASKDATA.XML, ISO 11783-10): tam şema (DVC/DPD/DDI grid'leri)
  KAPSAM DIŞI — burada PFD (Partfield, parsel sınırı) + TSK (Task) +
  TZN (Treatment Zone, parsel bazlı sabit oranlı bölge) + PDV (Product
  Data Value, DDI 0043 "Target Rate") ile GEÇERLİ ŞEMALı ama sadeleştirilmiş
  bir TASKDATA üretilir — birçok VRA terminalinin "sabit oranlı görev"
  içe aktarımıyla uyumludur, sub-field grid tabanlı VRA (DDI+Grid Type 2)
  DEĞİLDİR (veri kısıtı yukarıda açıklandı).
"""
import io
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

ZONE_CLASSES = ["dusuk", "orta", "yuksek"]
ZONE_LABELS = {"dusuk": "Düşük", "orta": "Orta", "yuksek": "Yüksek", "veri_yok": "Veri Yok"}
SIGNAL_LABELS = {
    "ndvi": "NDVI (Uydu)",
    "soil_n": "Toprak Azot (N, ppm)",
    "soil_p": "Toprak Fosfor (P, ppm)",
    "soil_k": "Toprak Potasyum (K, ppm)",
}


class VraPlanCreate(BaseModel):
    title: str
    parcel_ids: List[str]
    signal: str                              # ndvi | soil_n | soil_p | soil_k
    zone_rates: Dict[str, float]             # {"dusuk": .., "orta": .., "yuksek": ..}
    unit: str = "kg/da"
    product_name: Optional[str] = None


async def _signal_value(db, parcel: dict, signal: str) -> Optional[float]:
    if signal == "ndvi":
        v = parcel.get("ndvi_latest")
        return float(v) if v not in (None, "") else None
    field_map = {"soil_n": "n_ppm", "soil_p": "p_ppm", "soil_k": "k_ppm"}
    field = field_map.get(signal)
    if not field:
        raise HTTPException(400, f"Bilinmeyen sinyal: {signal}")
    sample = await db.soil_samples.find_one(
        {"parcel_id": parcel["id"], field: {"$ne": None}}, {"_id": 0}, sort=[("date", -1)],
    )
    if not sample:
        return None
    v = sample.get(field)
    return float(v) if v is not None else None


def _classify(value: Optional[float], vmin: float, vmax: float) -> str:
    if value is None:
        return "veri_yok"
    if vmax <= vmin:
        return "orta"
    span = (vmax - vmin) / 3
    if value <= vmin + span:
        return "dusuk"
    if value >= vmax - span:
        return "yuksek"
    return "orta"


def _ring_to_lonlat(geometry: dict) -> List[List[List[float]]]:
    """GeoJSON Polygon/MultiPolygon'dan dış halkaları [[lon,lat],...] listesi olarak döner.
    Sadece dış halka (exterior ring) kullanılır — deliği (hole) olan parsel
    poligonları bu iterasyonda kapsam dışı (nadiren rastlanan bir durum)."""
    if not geometry:
        return []
    t = geometry.get("type")
    coords = geometry.get("coordinates")
    if t == "Polygon":
        return [coords[0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in coords]
    return []


def register_vra_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.post("/vra/plans")
    async def create_vra_plan(body: VraPlanCreate, request: Request,
                               user=Depends(require_permission("vra:create")),
                               _feat=Depends(require_feature("vra"))):
        if not body.parcel_ids:
            raise HTTPException(400, "En az bir parsel seçilmeli")
        missing_rate_classes = [c for c in ZONE_CLASSES if c not in body.zone_rates]
        if missing_rate_classes:
            raise HTTPException(400, f"Eksik zon oranı: {', '.join(ZONE_LABELS[c] for c in missing_rate_classes)}")
        if body.signal not in SIGNAL_LABELS:
            raise HTTPException(400, f"Bilinmeyen sinyal: {body.signal}")

        parcels = await db.parcels.find({"id": {"$in": body.parcel_ids}}, {"_id": 0}).to_list(len(body.parcel_ids))
        if not parcels:
            raise HTTPException(404, "Parsel bulunamadı")

        values = []
        for p in parcels:
            values.append((p, await _signal_value(db, p, body.signal)))

        real_values = [v for _, v in values if v is not None]
        vmin, vmax = (min(real_values), max(real_values)) if real_values else (0.0, 0.0)

        assignments = []
        for p, v in values:
            zone = _classify(v, vmin, vmax)
            rate = body.zone_rates.get(zone) if zone != "veri_yok" else None
            assignments.append({
                "parcel_id": p["id"], "parcel_name": p.get("name"),
                "signal_value": v, "zone_class": zone, "rate": rate,
            })

        no_data_count = sum(1 for a in assignments if a["zone_class"] == "veri_yok")

        doc = {
            "id": str(uuid.uuid4()),
            "title": body.title,
            "signal": body.signal,
            "zone_rates": body.zone_rates,
            "unit": body.unit,
            "product_name": body.product_name,
            "assignments": assignments,
            "no_data_count": no_data_count,
            "created_by": user.get("full_name") or user.get("email"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.vra_plans.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="vra_plan", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.get("/vra/plans")
    async def list_vra_plans(user=Depends(require_permission("vra:view")), _feat=Depends(require_feature("vra"))):
        return await db.vra_plans.find({}, {"_id": 0, "assignments": 0}).sort("created_at", -1).to_list(200)

    @api_router.get("/vra/plans/{plan_id}")
    async def get_vra_plan(plan_id: str, user=Depends(require_permission("vra:view")), _feat=Depends(require_feature("vra"))):
        doc = await db.vra_plans.find_one({"id": plan_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "VRA planı bulunamadı")
        return doc

    async def _plan_with_geometry(plan_id: str):
        plan = await db.vra_plans.find_one({"id": plan_id}, {"_id": 0})
        if not plan:
            raise HTTPException(404, "VRA planı bulunamadı")
        ids = [a["parcel_id"] for a in plan["assignments"]]
        parcels = await db.parcels.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "geometry": 1, "name": 1}).to_list(len(ids))
        geom_by_id = {p["id"]: p.get("geometry") for p in parcels}
        return plan, geom_by_id

    @api_router.get("/vra/plans/{plan_id}/export/shapefile")
    async def export_shapefile(plan_id: str, user=Depends(require_permission("vra:export")),
                                _feat=Depends(require_feature("vra"))):
        import shapefile
        plan, geom_by_id = await _plan_with_geometry(plan_id)

        shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
        w.field("PARCEL", "C", size=64)
        w.field("ZONE", "C", size=16)
        w.field("RATE", "N", decimal=3)
        w.field("UNIT", "C", size=16)

        written = 0
        for a in plan["assignments"]:
            geometry = geom_by_id.get(a["parcel_id"])
            rings = _ring_to_lonlat(geometry) if geometry else []
            if not rings:
                continue
            for ring in rings:
                w.poly([ring])
                w.record(
                    PARCEL=(a.get("parcel_name") or a["parcel_id"])[:64],
                    ZONE=ZONE_LABELS.get(a["zone_class"], a["zone_class"]),
                    RATE=a["rate"] if a["rate"] is not None else 0,
                    UNIT=plan["unit"],
                )
                written += 1
        w.close()
        if written == 0:
            raise HTTPException(400, "Seçili parsellerin hiçbirinde geometri kaydı yok — dışa aktarılacak bir şey bulunamadı")

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"vra_{plan_id[:8]}.shp", shp.getvalue())
            z.writestr(f"vra_{plan_id[:8]}.shx", shx.getvalue())
            z.writestr(f"vra_{plan_id[:8]}.dbf", dbf.getvalue())
        zip_buf.seek(0)
        await log_audit(db, user, action="export_shapefile", entity="vra_plan", entity_id=plan_id, request=None)
        return StreamingResponse(
            zip_buf, media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="vra_{plan_id[:8]}.zip"'},
        )

    @api_router.get("/vra/plans/{plan_id}/export/isoxml")
    async def export_isoxml(plan_id: str, user=Depends(require_permission("vra:export")),
                             _feat=Depends(require_feature("vra"))):
        plan, geom_by_id = await _plan_with_geometry(plan_id)

        root = ET.Element("ISO11783_TaskData", {
            "VersionMajor": "4", "VersionMinor": "3", "DataTransferOrigin": "1",
            "ManagementSoftwareManufacturer": "TOPRAX",
            "ManagementSoftwareVersion": "1.5",
        })

        written = 0
        for idx, a in enumerate(plan["assignments"], start=1):
            geometry = geom_by_id.get(a["parcel_id"])
            rings = _ring_to_lonlat(geometry) if geometry else []
            if not rings or a["rate"] is None:
                continue
            pfd_id = f"PFD{idx}"
            pfd = ET.SubElement(root, "PFD", {
                "A": pfd_id, "C": (a.get("parcel_name") or a["parcel_id"])[:32],
                "D": "0", "I": "0",
            })
            pln = ET.SubElement(pfd, "PLN", {"A": "1"})
            for ring in rings:
                lsg = ET.SubElement(pln, "LSG", {"A": "1"})
                for lon, lat in ring:
                    ET.SubElement(lsg, "PNT", {"A": "2", "C": f"{lat:.7f}", "D": f"{lon:.7f}"})

            tsk = ET.SubElement(root, "TSK", {
                "A": f"TSK{idx}", "C": f"{plan['title']} — {a.get('parcel_name') or a['parcel_id']}"[:32],
                "E": pfd_id, "F": "2",
            })
            tzn = ET.SubElement(tsk, "TZN", {
                "A": f"TZN{idx}", "B": ZONE_LABELS.get(a["zone_class"], a["zone_class"]),
            })
            # DDI 0043 = "Setpoint Volume Per Area Application Rate" (ISO 11783-11 DDE).
            ET.SubElement(tzn, "PDV", {"A": "0043", "B": str(a["rate"]), "D": "0"})
            pln2 = ET.SubElement(tzn, "PLN", {"A": "1"})
            for ring in rings:
                lsg2 = ET.SubElement(pln2, "LSG", {"A": "1"})
                for lon, lat in ring:
                    ET.SubElement(lsg2, "PNT", {"A": "2", "C": f"{lat:.7f}", "D": f"{lon:.7f}"})
            written += 1

        if written == 0:
            raise HTTPException(400, "Rate atanmış + geometrisi olan bir parsel bulunamadı — dışa aktarılacak bir şey yok")

        xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        await log_audit(db, user, action="export_isoxml", entity="vra_plan", entity_id=plan_id, request=None)
        return StreamingResponse(
            io.BytesIO(xml_bytes), media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="TASKDATA_{plan_id[:8]}.xml"'},
        )
