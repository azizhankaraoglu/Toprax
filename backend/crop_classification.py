"""
=====================================================================
Toprax — Uydu ile Ürün Tanıma (2026-08-19)
=====================================================================
Kullanıcı isteği:

> "uydu aracılığı ile hangi parselde ne ekili konusunda ayrı bir alan halinde
>  tasarla. il ilçe mahalle verdiğimde burdaki tarlalarda hangi bitkiler ekili
>  diye sorabilirim. yada uydu üzerinden bende kayıtlı olmayan ama bölge sınırı
>  çizdiğim alanlarda buğday ekili tarlaları işaretle diyebilirim."
> "bu ürün tespiti için de ai model eğitim modeline alan ekleyelim. manuel
>  olarak eğitebilirim. yani uydu görüntüsü ve etiketi ekleyebilirim."

## Yöntem — fenolojik NDVI imzası

Her ürünün NDVI zaman serisinde karakteristik bir "imzası" vardır: ne zaman
yeşerir, ne zaman zirve yapar, ne zaman sararıp hasat edilir. Kışlık buğday
Nisan-Mayıs'ta zirve yapıp Haziran'da HIZLA düşer; şeker pancarı Ağustos-Eylül'de
zirvededir ve Ekim-Kasım'a kadar yeşil kalır. Bu fark, tek bir görüntüyle değil
ZAMAN SERİSİYLE ayırt edilir.

`classify_series()` gözlenen seriyi her imzayla karşılaştırıp benzerlik
(0-1) üretir; en yüksek olan tahmin, ikinci en yüksek "alternatif" olur.

**Bu bir ML modeli DEĞİLDİR** — açıklanabilir, kural tabanlı bir eşleştirmedir
(`polar_engine.predict_polar` ve `entitlement.calculate_*` ile AYNI felsefe:
saf fonksiyon, katkı dökümü, dürüst güven skoru). UI'da da böyle etiketlenir.

## Kalibrasyon (eğitim)

İmzalar bölgeye göre kayar (Konya'nın buğdayı Trakya'nınkiyle aynı takvimde
değildir). Bu yüzden imza kataloğu `catalog_registry.py`'ye kayıtlıdır: admin
elle düzenleyebilir VEYA `POST /crop-classification/calibrate` ile etiketlenmiş
gerçek örneklerden otomatik türetebilir. Kod varsayılanı hiç bozulmaz —
"Varsayılana Döndür" her zaman mümkündür.

## Sağlayıcı zinciri

Kullanıcı kararı: "copernicus sonra sentinel sonra gee, eminlik yüzdesine göre
üçünü de kullanabilir".

**Teknik not:** `remote_sensing/providers/sentinel2.py` ZATEN Copernicus
üzerinden gider (CDSE = Copernicus Data Space Ecosystem). "Copernicus" ve
"Sentinel-2" ayrı iki kaynak değil, aynı kaynağın adlarıdır. Zincir bu yüzden
şöyle kuruldu:

  1. `clms`      — Copernicus Land Monitoring Service'in HAZIR ürün tipi
                   katmanı (iskelet; erişilemezse dürüstçe "veri yok" döner,
                   ASLA uydurma sonuç üretmez)
  2. `sentinel2` — Copernicus CDSE NDVI zaman serisi  ← asıl çalışan katman
  3. `gee`       — NASA HLS / Google Earth Engine (bulutlu dönemlerde yedek)

Bir katman `CONFIDENCE_ACCEPT` (varsayılan 0.70) üzerinde sonuç verirse durulur.
Altındaysa sıradaki denenir; iki katman AYNI ürünü söylerse güven yükseltilir,
farklı söylerse ikisi de gösterilip karar kullanıcıya bırakılır.
"""
import math
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

CONFIDENCE_ACCEPT = 0.70
MIN_OBSERVATIONS = 4          # bu sayının altında seri güvenilir sınıflandırılamaz
MAX_AREA_CELLS = 150          # alan taramasında hücre üst sınırı (kota koruması)


# =====================================================================
# FENOLOJİ İMZA KATALOĞU (kod varsayılanı — catalog_registry ile override edilir)
# =====================================================================
# `aylik_ndvi`: 1-12 aylar için beklenen NDVI. Konya/İç Anadolu sulu tarım
# koşullarına göre; başka bölgede kalibrasyon gerekir (bkz. /calibrate).
CROP_SIGNATURES: List[Dict[str, Any]] = [
    {
        "key": "bugday", "label": "Buğday (kışlık)", "renk": "#eab308",
        "aylik_ndvi": [0.25, 0.30, 0.42, 0.68, 0.75, 0.45, 0.18, 0.15, 0.14, 0.16, 0.20, 0.23],
        "aciklama": "Nisan-Mayıs zirve, Haziran'da hasatla HIZLI düşüş.",
    },
    {
        "key": "pancar", "label": "Şeker Pancarı", "renk": "#22c55e",
        "aylik_ndvi": [0.14, 0.15, 0.18, 0.28, 0.48, 0.68, 0.80, 0.82, 0.75, 0.55, 0.28, 0.16],
        "aciklama": "Mayıs ekim, Ağustos-Eylül zirve, Ekim-Kasım söküm.",
    },
    {
        "key": "misir", "label": "Mısır", "renk": "#f97316",
        "aylik_ndvi": [0.13, 0.14, 0.16, 0.20, 0.35, 0.62, 0.82, 0.78, 0.42, 0.20, 0.15, 0.13],
        "aciklama": "Haziran-Temmuz hızlı gelişim, Ağustos zirve, Eylül'de keskin düşüş.",
    },
    {
        "key": "aycicegi", "label": "Ayçiçeği", "renk": "#facc15",
        "aylik_ndvi": [0.13, 0.14, 0.17, 0.24, 0.45, 0.72, 0.70, 0.38, 0.20, 0.16, 0.14, 0.13],
        "aciklama": "Temmuz zirve, Ağustos'ta hızlı yaşlanma.",
    },
    {
        "key": "yonca", "label": "Yonca / Yem Bitkisi", "renk": "#14b8a6",
        "aylik_ndvi": [0.25, 0.32, 0.50, 0.68, 0.45, 0.66, 0.44, 0.64, 0.46, 0.40, 0.30, 0.26],
        "aciklama": "Sezonda 3-4 biçim — çoklu zirve/düşüş dalgası.",
    },
    {
        "key": "arpa", "label": "Arpa", "renk": "#a3a3a3",
        "aylik_ndvi": [0.24, 0.30, 0.44, 0.70, 0.66, 0.28, 0.16, 0.14, 0.14, 0.16, 0.20, 0.22],
        "aciklama": "Buğdaya benzer ama ~2-3 hafta ERKEN hasat.",
    },
    {
        "key": "nadas", "label": "Nadas / Ekilmemiş", "renk": "#78716c",
        "aylik_ndvi": [0.12, 0.13, 0.16, 0.20, 0.22, 0.20, 0.16, 0.14, 0.13, 0.13, 0.12, 0.12],
        "aciklama": "Sezon boyu düşük NDVI, belirgin zirve YOK.",
    },
]
SIGNATURE_BY_KEY = {s["key"]: s for s in CROP_SIGNATURES}


# =====================================================================
# SAF HESAP — DB/HTTP'siz, test edilebilir
# =====================================================================
def series_to_monthly(series: List[Dict[str, Any]], index: str = "ndvi") -> Dict[int, float]:
    """Zaman serisini ay→ortalama NDVI sözlüğüne indirger.

    Uydu geçişleri düzensizdir (bulut, yörünge); aylık ortalama hem gürültüyü
    azaltır hem imzalarla aynı ölçeğe getirir.
    """
    buckets: Dict[int, List[float]] = {}
    for p in series or []:
        val = p.get(index)
        d = p.get("date")
        if val is None or not d:
            continue
        try:
            m = int(str(d)[5:7])
        except (ValueError, IndexError):
            continue
        if 1 <= m <= 12:
            buckets.setdefault(m, []).append(float(val))
    return {m: sum(v) / len(v) for m, v in buckets.items() if v}


def _shape_similarity(observed: Dict[int, float], signature: List[float]) -> Tuple[float, int]:
    """Gözlem ile imza arasındaki benzerlik (0-1) ve karşılaştırılan ay sayısı.

    İki bileşenin ortalaması:
      - **mutlak yakınlık**: aynı aylardaki NDVI farkı ne kadar küçük
      - **şekil korelasyonu**: eğrinin yükseliş/düşüş DESENİ ne kadar benziyor
    Şekil bileşeni kritik: sulama/toprak farkı NDVI'yı topluca yukarı-aşağı
    kaydırabilir ama ürünün fenolojik deseni yine de kendine özgü kalır.
    """
    common = [(m, v) for m, v in sorted(observed.items()) if 1 <= m <= 12]
    if len(common) < 2:
        return 0.0, len(common)

    obs = [v for _, v in common]
    sig = [signature[m - 1] for m, _ in common]

    # 1) Mutlak yakınlık
    mae = sum(abs(o - s) for o, s in zip(obs, sig)) / len(obs)
    closeness = max(0.0, 1.0 - mae / 0.45)        # 0.45 NDVI fark = tamamen farklı

    # 2) Şekil korelasyonu (Pearson)
    n = len(obs)
    mo, ms = sum(obs) / n, sum(sig) / n
    cov = sum((o - mo) * (s - ms) for o, s in zip(obs, sig))
    vo = math.sqrt(sum((o - mo) ** 2 for o in obs))
    vs = math.sqrt(sum((s - ms) ** 2 for s in sig))
    corr = (cov / (vo * vs)) if vo > 1e-9 and vs > 1e-9 else 0.0
    shape = max(0.0, corr)                         # negatif korelasyon = benzemiyor

    return round(0.5 * closeness + 0.5 * shape, 4), len(common)


def classify_series(series: List[Dict[str, Any]],
                    signatures: Optional[List[Dict[str, Any]]] = None,
                    index: str = "ndvi") -> Dict[str, Any]:
    """NDVI zaman serisinden ürün tahmini.

    SAF fonksiyon — DB/HTTP'ye gitmez, doğrudan test edilebilir.
    Dönen zarf her zaman `guven` ve `alternatifler` taşır; "kesin ürün"
    iddiası edilmez.
    """
    sigs = signatures if signatures is not None else CROP_SIGNATURES
    monthly = series_to_monthly(series, index)

    if len(monthly) < MIN_OBSERVATIONS:
        return {
            "urun": None, "urun_label": None, "guven": 0.0,
            "yetersiz_veri": True,
            "sebep": f"Sınıflandırma için en az {MIN_OBSERVATIONS} aylık gözlem gerekir "
                     f"(mevcut: {len(monthly)}). Bulutluluk veya kısa arşiv olabilir.",
            "alternatifler": [], "gozlem_ay_sayisi": len(monthly), "aylik_ndvi": monthly,
        }

    scored = []
    for s in sigs:
        curve = s.get("aylik_ndvi") or []
        if len(curve) != 12:
            continue
        sim, n = _shape_similarity(monthly, curve)
        scored.append({"key": s["key"], "label": s.get("label") or s["key"],
                       "renk": s.get("renk"), "benzerlik": sim, "karsilastirilan_ay": n})
    if not scored:
        return {"urun": None, "urun_label": None, "guven": 0.0, "yetersiz_veri": True,
                "sebep": "İmza kataloğu boş.", "alternatifler": [],
                "gozlem_ay_sayisi": len(monthly), "aylik_ndvi": monthly}

    scored.sort(key=lambda x: x["benzerlik"], reverse=True)
    best, second = scored[0], (scored[1] if len(scored) > 1 else None)

    # Güven = benzerliğin kendisi × ikinciden ne kadar AYRIŞTIĞI. İki ürün
    # birbirine çok yakın skor aldıysa (ör. buğday/arpa) güven düşürülür —
    # bu dürüstlük, kullanıcı alternatifi görüp kendi kararını verebilsin.
    margin = (best["benzerlik"] - second["benzerlik"]) if second else best["benzerlik"]
    separation = min(1.0, margin / 0.15)
    guven = round(best["benzerlik"] * (0.6 + 0.4 * separation), 4)
    # Az gözlem güveni düşürür.
    if len(monthly) < 6:
        guven = round(guven * (0.6 + 0.4 * (len(monthly) - MIN_OBSERVATIONS) / 2), 4)

    return {
        "urun": best["key"], "urun_label": best["label"], "renk": best.get("renk"),
        "guven": max(0.0, min(1.0, guven)),
        "benzerlik": best["benzerlik"],
        "yetersiz_veri": False,
        "alternatifler": scored[1:4],
        "gozlem_ay_sayisi": len(monthly),
        "aylik_ndvi": monthly,
        "yontem": "Fenolojik NDVI imza eşleştirmesi (kural tabanlı, ML modeli değil)",
    }


def polygon_bbox(geometry: Dict[str, Any]) -> Tuple[float, float, float, float]:
    """GeoJSON poligonun bbox'ı (minLon, minLat, maxLon, maxLat)."""
    pts: List[List[float]] = []

    def walk(c):
        if isinstance(c, (list, tuple)):
            if c and isinstance(c[0], (int, float)):
                pts.append(list(c))
            else:
                for x in c:
                    walk(x)
    walk((geometry or {}).get("coordinates") or [])
    if not pts:
        raise ValueError("Geometride koordinat yok")
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return min(lons), min(lats), max(lons), max(lats)


def point_in_polygon(lon: float, lat: float, geometry: Dict[str, Any]) -> bool:
    """Ray-casting — dış halkaya bakar (delik desteği YOK, bilinçli sadelik)."""
    coords = (geometry or {}).get("coordinates") or []
    gtype = (geometry or {}).get("type")
    rings = []
    if gtype == "Polygon":
        rings = coords[:1]
    elif gtype == "MultiPolygon":
        rings = [poly[0] for poly in coords if poly]
    for ring in rings:
        inside = False
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i][0], ring[i][1]
            x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
            if ((y1 > lat) != (y2 > lat)) and \
               (lon < (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1):
                inside = not inside
        if inside:
            return True
    return False


def build_grid(geometry: Dict[str, Any], cell_m: float = 100.0,
               max_cells: int = MAX_AREA_CELLS) -> Dict[str, Any]:
    """Poligonu ~`cell_m` metrelik hücrelere böler.

    **Dürüstlük sınırı:** bu GERÇEK piksel-seviyesi segmentasyon DEĞİLDİR.
    Tarla sınırlarını çıkarmaz; alanı ızgaraya bölüp her hücreyi ayrı ayrı
    sınıflandırır. Hücre çözünürlüğünde bir yaklaşımdır ve UI'da böyle
    belirtilir.
    """
    min_lon, min_lat, max_lon, max_lat = polygon_bbox(geometry)
    mid_lat = (min_lat + max_lat) / 2
    deg_lat = cell_m / 111_320.0
    deg_lon = cell_m / (111_320.0 * max(0.1, math.cos(math.radians(mid_lat))))

    cells: List[Dict[str, Any]] = []
    truncated = False
    lat = min_lat
    while lat < max_lat:
        lon = min_lon
        while lon < max_lon:
            c_lon, c_lat = lon + deg_lon / 2, lat + deg_lat / 2
            if point_in_polygon(c_lon, c_lat, geometry):
                if len(cells) >= max_cells:
                    truncated = True
                    break
                cells.append({
                    "center": [round(c_lon, 6), round(c_lat, 6)],
                    "geometry": {"type": "Polygon", "coordinates": [[
                        [lon, lat], [lon + deg_lon, lat],
                        [lon + deg_lon, lat + deg_lat], [lon, lat + deg_lat], [lon, lat],
                    ]]},
                })
            lon += deg_lon
        if truncated:
            break
        lat += deg_lat
    return {"cells": cells, "truncated": truncated, "cell_m": cell_m}


# =====================================================================
# SAĞLAYICI ZİNCİRİ
# =====================================================================
PROVIDER_CHAIN = [
    {"key": "clms", "label": "Copernicus CLMS (hazır ürün haritası)"},
    {"key": "sentinel2", "label": "Copernicus CDSE / Sentinel-2 (NDVI imzası)"},
    {"key": "gee_hls", "label": "Google Earth Engine / NASA HLS"},
]


async def _fetch_series(db, provider_key: str, parcel_id: Optional[str],
                        geometry: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bir sağlayıcıdan NDVI zaman serisi çeker. Hata/boş durumda [] döner —
    zincirin bir sonraki halkasına geçilebilsin diye ASLA istisna fırlatmaz."""
    if provider_key == "clms":
        # Copernicus Land Monitoring Service'in hazır ürün tipi katmanı.
        # HENÜZ BAĞLANMADI (Türkiye kapsamı/erişim doğrulanmadı) — bilinçli
        # olarak boş döner, uydurma sonuç ÜRETMEZ. Bağlandığında bu fonksiyon
        # doğrudan ürün etiketi döndürecek şekilde genişletilir.
        return []
    try:
        from remote_sensing.providers import get_remote_sensing_provider
        provider = await get_remote_sensing_provider(db, provider_override=provider_key)
        series = provider.get_ndvi_time_series(parcel_id or "adhoc", geometry=geometry)
        return series or []
    except Exception:  # noqa: BLE001
        return []


async def classify_with_chain(db, parcel_id: Optional[str], geometry: Optional[Dict[str, Any]],
                              signatures: List[Dict[str, Any]],
                              stored_series: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Sağlayıcı zincirini güven eşiğine göre gezer (kullanıcı kararı).

    Bir katman `CONFIDENCE_ACCEPT` üzerinde sonuç verirse durulur. Altındaysa
    sıradaki denenir; İKİ katman AYNI ürünü söylerse güven yükseltilir,
    FARKLI söylerse ikisi de raporlanır ve karar kullanıcıya bırakılır.
    """
    attempts: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None

    # Önce DB'de kayıtlı seri (ücretsiz — yeni uydu isteği harcamaz)
    sources: List[Tuple[str, List[Dict[str, Any]]]] = []
    if stored_series:
        sources.append(("kayitli", stored_series))

    for prov in PROVIDER_CHAIN:
        if best and best.get("guven", 0) >= CONFIDENCE_ACCEPT:
            break
        if not sources or prov["key"] != "clms":
            series = await _fetch_series(db, prov["key"], parcel_id, geometry)
            if series:
                sources.append((prov["key"], series))

        while sources:
            src_key, series = sources.pop(0)
            res = classify_series(series, signatures)
            attempts.append({"kaynak": src_key, "urun": res.get("urun"),
                             "guven": res.get("guven"), "ay": res.get("gozlem_ay_sayisi"),
                             "yetersiz": res.get("yetersiz_veri")})
            if res.get("yetersiz_veri"):
                continue
            if best is None or res["guven"] > best["guven"]:
                res["kaynak"] = src_key
                best = res
            elif res["urun"] == best["urun"]:
                # İki bağımsız kaynak AYNI ürünü söyledi — güven yükselir.
                best["guven"] = round(min(1.0, best["guven"] + 0.15), 4)
                best["dogrulayan_kaynak"] = src_key

    if best is None:
        return {"urun": None, "urun_label": None, "guven": 0.0, "yetersiz_veri": True,
                "sebep": "Hiçbir sağlayıcıdan yeterli uydu gözlemi alınamadı.",
                "alternatifler": [], "denemeler": attempts}
    best["denemeler"] = attempts
    return best


# =====================================================================
# PYDANTIC MODELLERİ
# =====================================================================
class ParcelClassifyRequest(BaseModel):
    parcel_ids: List[str] = []
    il: Optional[str] = None
    ilce: Optional[str] = None
    mahalle: Optional[str] = None
    season: Optional[int] = None
    limit: int = 50


class AreaScanRequest(BaseModel):
    geometry: Dict[str, Any]
    crop: Optional[str] = None          # verilirse SADECE bu ürün işaretlenir
    cell_m: float = 200.0
    season: Optional[int] = None


class TrainingSampleCreate(BaseModel):
    crop_label: str
    season: Optional[int] = None
    parcel_id: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None
    ndvi_series: Optional[List[Dict[str, Any]]] = None
    image_ref: Optional[str] = None
    note: Optional[str] = None


# =====================================================================
# ROUTE KAYDI (convention #1)
# =====================================================================
def register_crop_classification_routes(api_router, db, current_user, require_permission,
                                        log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    async def _signatures() -> List[Dict[str, Any]]:
        """İmza kataloğu — admin override'ı (catalog_registry) ile birlikte."""
        try:
            from catalog_registry import get_catalog
            rows = await get_catalog(db, "crop_signatures")
            out = []
            for r in rows:
                curve = r.get("aylik_ndvi")
                if isinstance(curve, str):        # admin ekranından virgüllü metin gelebilir
                    try:
                        curve = [float(x) for x in curve.split(",")]
                    except ValueError:
                        continue
                if isinstance(curve, list) and len(curve) == 12:
                    out.append({**r, "aylik_ndvi": [float(x) for x in curve]})
            return out or CROP_SIGNATURES
        except Exception:  # noqa: BLE001
            return CROP_SIGNATURES

    async def _stored_series(parcel_id: str) -> List[Dict[str, Any]]:
        st = await db.remote_sensing_statistics.find_one(
            {"parcel_id": parcel_id}, {"_id": 0}, sort=[("created_at", -1)])
        return (st or {}).get("series") or []

    # ---------------- Katalog / meta ----------------
    @api_router.get("/crop-classification/crops")
    async def list_crops(user=Depends(require_permission("remote_sensing:view"))):
        sigs = await _signatures()
        return {"crops": [{"key": s["key"], "label": s.get("label"), "renk": s.get("renk"),
                           "aciklama": s.get("aciklama")} for s in sigs],
                "saglayici_zinciri": PROVIDER_CHAIN,
                "min_gozlem_ayi": MIN_OBSERVATIONS,
                "guven_esigi": CONFIDENCE_ACCEPT}

    # ---------------- 1) BÖLGEDE NE EKİLİ ----------------
    @api_router.post("/crop-classification/parcels")
    async def classify_parcels(body: ParcelClassifyRequest, request: Request,
                               user=Depends(require_permission("remote_sensing:view")),
                               _feat=Depends(require_feature("remote_sensing"))):
        """Kayıtlı parseller için ürün tanıma + BEYAN KARŞILAŞTIRMASI.

        Sonuç `plantings` kaydıyla karşılaştırılır: beyan "pancar" derken uydu
        "buğday" diyorsa `uyusmazlik: true` işaretlenir — denetim değeri en
        yüksek çıktı budur.
        """
        season = body.season or date.today().year
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}
        if body.parcel_ids:
            filt["id"] = {"$in": body.parcel_ids}
        for f, v in (("il", body.il), ("ilce", body.ilce), ("mahalle", body.mahalle)):
            if v:
                filt[f] = v
        if not body.parcel_ids and not (body.il or body.ilce or body.mahalle):
            raise HTTPException(400, "En az bir parsel VEYA il/ilçe/mahalle filtresi verin.")

        total = await db.parcels.count_documents(filt)
        parcels = await db.parcels.find(filt, {"_id": 0}).limit(
            max(1, min(body.limit, 200))).to_list(200)
        sigs = await _signatures()

        results, dagilim = [], {}
        for p in parcels:
            res = await classify_with_chain(db, p["id"], p.get("geometry"), sigs,
                                            stored_series=await _stored_series(p["id"]))
            planting = await db.plantings.find_one(
                {"parcel_id": p["id"], "season": season}, {"_id": 0, "crop": 1})
            beyan = (planting or {}).get("crop")
            urun = res.get("urun")
            if urun:
                dagilim[urun] = dagilim.get(urun, 0) + 1
            # Beyan serbest metin ("Şeker Pancarı"), tahmin anahtar ("pancar") —
            # kaba ama güvenli bir eşleştirme yapıyoruz.
            uyusmazlik = None
            if beyan and urun:
                bl = (res.get("urun_label") or "").lower()
                uyusmazlik = not (urun in beyan.lower().replace(" ", "") or
                                  beyan.lower()[:5] in bl)
            results.append({
                "parcel_id": p["id"], "parsel": p.get("name"),
                "il": p.get("il"), "ilce": p.get("ilce"), "mahalle": p.get("mahalle"),
                "alan_dekar": p.get("area_dekar"),
                "tahmin": urun, "tahmin_label": res.get("urun_label"),
                "renk": res.get("renk"), "guven": res.get("guven"),
                "yetersiz_veri": res.get("yetersiz_veri"), "sebep": res.get("sebep"),
                "alternatifler": res.get("alternatifler", [])[:2],
                "kaynak": res.get("kaynak"), "gozlem_ay_sayisi": res.get("gozlem_ay_sayisi"),
                "beyan": beyan, "uyusmazlik": uyusmazlik,
            })

        sig_by_key = {s["key"]: s for s in sigs}
        return {
            "season": season,
            "kapsam": {"islenen": len(parcels), "toplam": total, "truncated": len(parcels) < total},
            "dagilim": sorted(
                [{"urun": k, "label": sig_by_key.get(k, {}).get("label", k),
                  "renk": sig_by_key.get(k, {}).get("renk"), "parsel_sayisi": v}
                 for k, v in dagilim.items()],
                key=lambda x: x["parsel_sayisi"], reverse=True),
            "uyusmazlik_sayisi": sum(1 for r in results if r.get("uyusmazlik")),
            "sonuclar": results,
        }

    # ---------------- 2) ALAN TARAMASI (kayıtsız alanlar) ----------------
    @api_router.post("/crop-classification/area")
    async def scan_area(body: AreaScanRequest, request: Request,
                        user=Depends(require_permission("remote_sensing:view")),
                        _feat=Depends(require_feature("remote_sensing"))):
        """Çizilen poligonu ızgaraya bölüp her hücreyi sınıflandırır.

        Kayıtlı parsel GEREKTİRMEZ — "bende kayıtlı olmayan ama sınır çizdiğim
        alanlarda buğday ekili tarlaları işaretle" isteğinin karşılığı.

        **Sınır:** gerçek tarla-sınırı segmentasyonu değildir; hücre
        çözünürlüğünde yaklaşımdır (bkz. build_grid docstring'i).
        """
        try:
            grid = build_grid(body.geometry, cell_m=max(50.0, body.cell_m))
        except ValueError as e:
            raise HTTPException(400, str(e))
        if not grid["cells"]:
            raise HTTPException(400, "Çizilen alan çok küçük — hiç hücre üretilmedi. "
                                     "Daha büyük bir alan çizin veya hücre boyutunu küçültün.")

        sigs = await _signatures()
        cells_out, dagilim = [], {}
        yetersiz = 0
        for c in grid["cells"]:
            res = await classify_with_chain(db, None, c["geometry"], sigs)
            urun = res.get("urun")
            if res.get("yetersiz_veri"):
                yetersiz += 1
            if body.crop and urun != body.crop:
                continue                       # sadece istenen ürün işaretlensin
            if urun:
                dagilim[urun] = dagilim.get(urun, 0) + 1
            cells_out.append({
                "center": c["center"], "geometry": c["geometry"],
                "tahmin": urun, "tahmin_label": res.get("urun_label"),
                "renk": res.get("renk"), "guven": res.get("guven"),
                "yetersiz_veri": res.get("yetersiz_veri"),
            })

        # Hiç sonuç çıkmadıysa SEBEBİNİ söyle — boş bir harita kullanıcıya
        # "burada ürün yok" izlenimi verir, oysa gerçek sebep uydu verisinin
        # alınamamış olmasıdır.
        uyari = None
        if yetersiz == len(grid["cells"]) and grid["cells"]:
            uyari = ("Hiçbir hücre için yeterli uydu gözlemi alınamadı. Uzaktan algılama "
                     "sağlayıcısı (Ayarlar > Entegrasyonlar > Sentinel Hub / Google Earth "
                     "Engine) gerçek modda yapılandırılmış olmalı; demo/mock modda kayıtsız "
                     "alanlar için zaman serisi üretilmez.")
        elif yetersiz:
            uyari = f"{yetersiz}/{len(grid['cells'])} hücrede yeterli uydu gözlemi yok."

        sig_by_key = {s["key"]: s for s in sigs}
        return {
            "kapsam": {"hucre_sayisi": len(grid["cells"]), "isaretlenen": len(cells_out),
                       "yetersiz_veri_hucre": yetersiz,
                       "hucre_metre": grid["cell_m"], "truncated": grid["truncated"],
                       "ust_sinir": MAX_AREA_CELLS},
            "uyari": uyari,
            "filtre_urun": body.crop,
            "dagilim": sorted(
                [{"urun": k, "label": sig_by_key.get(k, {}).get("label", k),
                  "renk": sig_by_key.get(k, {}).get("renk"), "hucre_sayisi": v}
                 for k, v in dagilim.items()],
                key=lambda x: x["hucre_sayisi"], reverse=True),
            "hucreler": cells_out,
            "not": "Hücre çözünürlüğünde yaklaşımdır; gerçek tarla sınırı "
                   "segmentasyonu değildir.",
        }

    # ---------------- 3) EĞİTİM / ETİKETLEME ----------------
    @api_router.get("/crop-classification/samples")
    async def list_samples(limit: int = 500,
                           user=Depends(require_permission("ai_knowledge:view"))):
        return await db.crop_training_samples.find({"is_active": {"$ne": False}}, {"_id": 0}) \
                                             .sort("created_at", -1).to_list(min(limit, 2000))

    @api_router.post("/crop-classification/samples")
    async def add_sample(body: TrainingSampleCreate, request: Request,
                         user=Depends(require_permission("ai_knowledge:create"))):
        """Manuel etiket ekleme — uydu görüntüsü/serisi + gerçek ürün etiketi."""
        if not body.parcel_id and not body.geometry:
            raise HTTPException(400, "parcel_id veya geometry verin.")
        series = body.ndvi_series
        if series is None and body.parcel_id:
            series = await _stored_series(body.parcel_id)
        doc = {
            "id": str(uuid.uuid4()), "crop_label": body.crop_label,
            "season": body.season or date.today().year,
            "parcel_id": body.parcel_id, "geometry": body.geometry,
            "ndvi_series": series or [], "image_ref": body.image_ref, "note": body.note,
            "kaynak": "manuel", "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user.get("email"),
        }
        await db.crop_training_samples.insert_one(doc)
        await log_audit(db, user, "create", "crop_training_sample", doc["id"], None, doc, request)
        return {k: v for k, v in doc.items() if k != "_id"}

    @api_router.delete("/crop-classification/samples/{sample_id}")
    async def delete_sample(sample_id: str, request: Request,
                            user=Depends(require_permission("ai_knowledge:manage"))):
        old = await db.crop_training_samples.find_one({"id": sample_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Örnek bulunamadı")
        await db.crop_training_samples.update_one({"id": sample_id},
                                                  {"$set": {"is_active": False}})
        await log_audit(db, user, "delete", "crop_training_sample", sample_id, old, None, request)
        return {"status": "deactivated"}

    @api_router.post("/crop-classification/samples/from-plantings")
    async def samples_from_plantings(season: Optional[int] = None, limit: int = 500,
                                     user=Depends(require_permission("ai_knowledge:create"))):
        """Beyandan TOPLU ground truth üretimi.

        `plantings` kayıtları zaten "hangi parselde ne ekili" beyanını taşıyor;
        bu uç onları tek çağrıyla etiketli örneğe çevirir. İdempotent — aynı
        parsel+sezon iki kez eklenmez (catalog_registry seed deseniyle AYNI).
        """
        season = season or date.today().year
        plantings = await db.plantings.find(
            {"season": season, "crop": {"$nin": [None, ""]}}, {"_id": 0}).limit(
            max(1, min(limit, 2000))).to_list(2000)
        created = skipped = no_series = 0
        for pl in plantings:
            pid = pl.get("parcel_id")
            if not pid:
                continue
            if await db.crop_training_samples.find_one(
                    {"parcel_id": pid, "season": season, "is_active": {"$ne": False}}):
                skipped += 1
                continue
            series = await _stored_series(pid)
            if not series:
                no_series += 1
                continue           # serisi olmayan örnek eğitime katkı sağlamaz
            await db.crop_training_samples.insert_one({
                "id": str(uuid.uuid4()), "crop_label": pl["crop"], "season": season,
                "parcel_id": pid, "geometry": None, "ndvi_series": series,
                "kaynak": "beyan", "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": user.get("email"),
            })
            created += 1
        return {"status": "ok", "created": created, "skipped_existing": skipped,
                "skipped_no_series": no_series, "scanned": len(plantings),
                "not": "Uydu serisi olmayan parseller atlandı — seri olmadan örnek "
                       "eğitime katkı sağlamaz."}

    def _label_to_key(label: str, sigs: List[Dict[str, Any]]) -> Optional[str]:
        """Serbest metin beyanını ("Şeker Pancarı") imza anahtarına çevirir."""
        low = (label or "").lower().replace(" ", "")
        for s in sigs:
            if s["key"] in low or (s.get("label") or "").lower().replace(" ", "")[:6] in low:
                return s["key"]
        return None

    @api_router.get("/crop-classification/accuracy")
    async def accuracy(user=Depends(require_permission("ai_knowledge:view"))):
        """Etiketli örnekler üzerinde doğruluk + karışıklık matrisi.

        "Eğitim işe yaradı mı" sorusunun ÖLÇÜLEN cevabı — kalibrasyon öncesi ve
        sonrası çağrılıp karşılaştırılabilir.
        """
        sigs = await _signatures()
        samples = await db.crop_training_samples.find(
            {"is_active": {"$ne": False}}, {"_id": 0}).to_list(5000)
        dogru = yanlis = atlanan = 0
        matris: Dict[str, Dict[str, int]] = {}
        for s in samples:
            gercek = _label_to_key(s.get("crop_label"), sigs)
            if not gercek or not s.get("ndvi_series"):
                atlanan += 1
                continue
            res = classify_series(s["ndvi_series"], sigs)
            if res.get("yetersiz_veri"):
                atlanan += 1
                continue
            tahmin = res.get("urun")
            matris.setdefault(gercek, {})
            matris[gercek][tahmin] = matris[gercek].get(tahmin, 0) + 1
            if tahmin == gercek:
                dogru += 1
            else:
                yanlis += 1
        degerlendirilen = dogru + yanlis
        return {
            "ornek_sayisi": len(samples), "degerlendirilen": degerlendirilen,
            "atlanan": atlanan, "dogru": dogru, "yanlis": yanlis,
            "dogruluk_yuzde": round(dogru / degerlendirilen * 100, 1) if degerlendirilen else None,
            "karisiklik_matrisi": matris,
            "not": "Atlananlar: ürün etiketi imza kataloğuyla eşleşmeyen veya "
                   "yeterli uydu gözlemi olmayan örnekler.",
        }

    @api_router.post("/crop-classification/calibrate")
    async def calibrate(request: Request, min_samples: int = 3,
                        user=Depends(require_permission("ai_knowledge:manage"))):
        """Etiketli örneklerden imzaları yeniden hesaplar.

        Ürün başına aylık ortalama NDVI eğrisi türetilir ve
        `catalog_registry`'deki `crop_signatures` kalemi OVERRIDE edilir.
        Kod varsayılanı BOZULMAZ — admin "Varsayılana Döndür" ile her an
        geri alabilir (bu, catalog_registry katmanının tasarlandığı senaryo).
        """
        sigs = await _signatures()
        samples = await db.crop_training_samples.find(
            {"is_active": {"$ne": False}}, {"_id": 0}).to_list(5000)

        toplam: Dict[str, Dict[int, List[float]]] = {}
        ornek_sayisi: Dict[str, int] = {}       # ürün başına KAÇ AYRI örnek
        for s in samples:
            key = _label_to_key(s.get("crop_label"), sigs)
            if not key or not s.get("ndvi_series"):
                continue
            ornek_sayisi[key] = ornek_sayisi.get(key, 0) + 1
            for m, v in series_to_monthly(s["ndvi_series"]).items():
                toplam.setdefault(key, {}).setdefault(m, []).append(v)

        from catalog_registry import COLLECTION as CATALOG_COLLECTION
        guncellenen, atlanan = [], []
        for key, aylar in toplam.items():
            ornek_ay = sum(len(v) for v in aylar.values())
            n_ornek = ornek_sayisi.get(key, 0)
            # Eşik AYRI ÖRNEK sayısına bakar, ay-gözlem sayısına DEĞİL. Tek bir
            # parselin 12 aylık serisi 12 "gözlem" üretir ama o TEK bir tarladır;
            # ondan türetilen imza genellenebilir değildir. (İlk sürümde bu
            # karıştırılmıştı: 3 örnekle kalibrasyon "başarılı" dedi ama
            # doğruluğu hiç değiştirmedi — ölçüm bunu ortaya çıkardı.)
            if n_ornek < min_samples or len(aylar) < 6:
                atlanan.append({
                    "urun": key, "ornek_sayisi": n_ornek,
                    "sebep": f"yetersiz örnek ({n_ornek} örnek / {len(aylar)} ay; "
                             f"en az {min_samples} örnek ve 6 ay gerekir)",
                })
                continue
            base = SIGNATURE_BY_KEY.get(key, {}).get("aylik_ndvi") or [0.2] * 12
            # Ölçülmeyen aylar kod varsayılanını KORUR — eksik veri yüzünden
            # imzanın o kısmı sıfırlanmasın.
            curve = [round(sum(aylar[m]) / len(aylar[m]), 3) if m in aylar else base[m - 1]
                     for m in range(1, 13)]
            await db[CATALOG_COLLECTION].update_one(
                {"catalog_key": "crop_signatures", "key": key},
                {"$set": {"catalog_key": "crop_signatures", "key": key,
                          "aylik_ndvi": curve, "is_active": True,
                          "kalibre_edildi": True,
                          "kalibrasyon_ornek_sayisi": ornek_ay,
                          "id": str(uuid.uuid4()),
                          "updated_at": datetime.now(timezone.utc).isoformat(),
                          "updated_by": user.get("email")}},
                upsert=True)
            guncellenen.append({"urun": key, "ornek_sayisi": n_ornek,
                                "olculen_ay": len(aylar), "gozlem": ornek_ay})

        await log_audit(db, user, "calibrate", "crop_signatures", "-", None,
                        {"guncellenen": guncellenen}, request)
        return {"status": "calibrated", "guncellenen": guncellenen, "atlanan": atlanan,
                "not": "Kod varsayılanları korunur; her kalem 'Varsayılana Döndür' "
                       "ile geri alınabilir (Form Yönetimi > Sabit Katalogları)."}
