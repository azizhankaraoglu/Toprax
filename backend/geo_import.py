"""
=====================================================================
Toprax — Geo Dosya İçe Aktarma (IT-13.5)
=====================================================================
SHP (pyshp) + GeoJSON + KML + KMZ + DXF (ezdxf) dosyalarını ayrıştırıp
WGS84 (EPSG:4326) GeoJSON geometrisine çevirir. NCZ (NetCAD) dosyaları
PARSE EDİLMEZ — tescilli bir format; kullanıcıya NetCAD'den SHP/DXF
export yolu gösterilir (istenirse dosya olduğu gibi genel "Belgeler"
sekmesinden — storage.py — saklanabilir, ayrı bir konudur).

Akış (önizleme + onay — "kullanıcı haritada görüp onaylamadan kayıt
yazılmaz"): `POST /geo-import/parse` SADECE ayrıştırır, HİÇBİR ŞEYİ
VERİTABANINA YAZMAZ. Frontend sonucu haritada gösterip kullanıcıya
onaylatır; onaylanan geometri AYRI bir çağrıyla asıl kayda yazılır —
parsel için zaten var olan `PUT /parcels/{id}` (`geometry` alanı
ParcelUpdate'te mevcut, IT-02'den beri), idari alan için IT-13.6'nın
kendi ucu. Sunucu tarafında bir "preview session" state TUTULMAZ —
frontend React state'inde tutması bu v1 için yeterli, ayrı bir geçici
koleksiyon/TTL yönetimi gerektirmez.
"""
import io
import json
import os
import tempfile
import zipfile
from typing import Any, Dict, List, Optional

import ezdxf
import shapefile
from fastapi import Depends, File, Form, HTTPException, UploadFile
from pyproj import CRS, Transformer

# Türkiye'de sık kullanılan EPSG kodları — frontend dropdown'ı için.
# Kullanıcı bunların dışında herhangi bir sayısal EPSG kodunu da girebilir.
COMMON_EPSG_CODES = [
    {"code": 4326, "label": "WGS84 (EPSG:4326) — zaten coğrafi, dönüşüm gerekmez"},
    {"code": 5253, "label": "ITRF96 / TUREF 3° Dilim 3 (EPSG:5253)"},
    {"code": 5254, "label": "ITRF96 / TUREF 3° Dilim 4 (EPSG:5254)"},
    {"code": 5255, "label": "ITRF96 / TUREF 3° Dilim 5 (EPSG:5255)"},
    {"code": 5256, "label": "ITRF96 / TUREF 3° Dilim 6 (EPSG:5256)"},
    {"code": 5257, "label": "ITRF96 / TUREF 3° Dilim 7 (EPSG:5257)"},
    {"code": 5258, "label": "ITRF96 / TUREF 3° Dilim 8 (EPSG:5258)"},
    {"code": 23036, "label": "ED50 / UTM Zone 36N (EPSG:23036)"},
    {"code": 23037, "label": "ED50 / UTM Zone 37N (EPSG:23037)"},
]

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _transform_coords(coords, transformer):
    """GeoJSON koordinat yapısını (iç içe listeler) recursive dönüştürür."""
    if isinstance(coords[0], (int, float)):
        x, y = transformer.transform(coords[0], coords[1])
        return [x, y]
    return [_transform_coords(c, transformer) for c in coords]


def _get_transformer(source_epsg: Optional[int]):
    if not source_epsg or source_epsg == 4326:
        return None
    return Transformer.from_crs(CRS.from_epsg(source_epsg), CRS.from_epsg(4326), always_xy=True)


def _parse_geojson(content: bytes) -> List[Dict[str, Any]]:
    data = json.loads(content)
    if data.get("type") == "FeatureCollection":
        return [{"geometry": f["geometry"], "properties": f.get("properties") or {}} for f in data["features"]]
    if data.get("type") == "Feature":
        return [{"geometry": data["geometry"], "properties": data.get("properties") or {}}]
    return [{"geometry": data, "properties": {}}]  # çıplak geometry objesi


def _parse_kml(content: bytes) -> List[Dict[str, Any]]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(content)

    def local(tag):
        return tag.split("}")[-1]

    def parse_coord_text(text):
        pts = []
        for chunk in (text or "").strip().replace("\n", " ").replace("\t", " ").split():
            parts = chunk.split(",")
            if len(parts) >= 2:
                pts.append([float(parts[0]), float(parts[1])])
        return pts

    features = []
    for placemark in root.iter():
        if local(placemark.tag) != "Placemark":
            continue
        name = None
        description = None
        geometry = None
        # Placemark'ın öznitelikleri (il/ilçe/mahalle/ada/parsel vb.) — bunlar
        # "parselin içindeki bilgiler"dir; KML'de <ExtendedData> altında ya
        # <Data name="..."><value>..</value></Data> ya da <SchemaData>
        # içinde <SimpleData name="..">..</SimpleData> olarak durur. Buradan
        # okunup properties'e konur; toplu import (server.py import-geojson +
        # _extract_tkgm_fields) bunları doğrudan parsel alanlarına eşler.
        props: Dict[str, Any] = {}
        for child in placemark.iter():
            tag = local(child.tag)
            if tag == "name" and name is None:
                name = (child.text or "").strip() or None
            elif tag == "description" and description is None:
                description = (child.text or "").strip() or None
            elif tag == "Data":
                key = child.get("name")
                if key:
                    val = None
                    for sub in child:
                        if local(sub.tag) == "value":
                            val = (sub.text or "").strip()
                            break
                    if val:
                        props[key] = val
            elif tag == "SimpleData":
                key = child.get("name")
                if key and child.text and child.text.strip():
                    props[key] = child.text.strip()
            elif tag == "Polygon" and geometry is None:
                rings = []
                for boundary in child:
                    if local(boundary.tag) in ("outerBoundaryIs", "innerBoundaryIs"):
                        for ring_el in boundary.iter():
                            if local(ring_el.tag) == "coordinates":
                                rings.append(parse_coord_text(ring_el.text))
                if rings:
                    geometry = {"type": "Polygon", "coordinates": rings}
            elif tag == "LineString" and geometry is None:
                for c in child.iter():
                    if local(c.tag) == "coordinates":
                        geometry = {"type": "LineString", "coordinates": parse_coord_text(c.text)}
            elif tag == "Point" and geometry is None:
                for c in child.iter():
                    if local(c.tag) == "coordinates":
                        pts = parse_coord_text(c.text)
                        if pts:
                            geometry = {"type": "Point", "coordinates": pts[0]}
        if geometry:
            if name and "name" not in props:
                props["name"] = name
            if description and "description" not in props:
                props["description"] = description
            features.append({"geometry": geometry, "properties": props})
    return features


def _parse_kmz(content: bytes) -> List[Dict[str, Any]]:
    """KMZ = içinde bir .kml (genelde doc.kml) barındıran ZIP arşivi.
    Açıp ilk .kml'i bulur ve _parse_kml ile ayrıştırır. KML her zaman WGS84
    (EPSG:4326) olduğundan koordinat dönüşümü GEREKMEZ."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Geçersiz KMZ dosyası (ZIP olarak açılamadı)")
    kml_name = next((n for n in zf.namelist() if n.lower().endswith(".kml")), None)
    if not kml_name:
        raise HTTPException(400, "KMZ içinde .kml dosyası bulunamadı")
    return _parse_kml(zf.read(kml_name))


def _parse_shp_zip(content: bytes, source_epsg: Optional[int]) -> List[Dict[str, Any]]:
    zf = zipfile.ZipFile(io.BytesIO(content))
    lower_to_real = {n.lower(): n for n in zf.namelist()}
    shp_name = next((n for lo, n in lower_to_real.items() if lo.endswith(".shp")), None)
    if not shp_name:
        raise HTTPException(400, "ZIP içinde .shp dosyası bulunamadı")
    base = shp_name.rsplit(".", 1)[0]
    shx_name = lower_to_real.get((base + ".shx").lower())
    dbf_name = lower_to_real.get((base + ".dbf").lower())
    prj_name = lower_to_real.get((base + ".prj").lower())

    shp_io = io.BytesIO(zf.read(shp_name))
    shx_io = io.BytesIO(zf.read(shx_name)) if shx_name else None
    dbf_io = io.BytesIO(zf.read(dbf_name)) if dbf_name else None

    reader = shapefile.Reader(shp=shp_io, shx=shx_io, dbf=dbf_io)

    transformer = None
    if prj_name:
        prj_text = zf.read(prj_name).decode("utf-8", errors="ignore")
        try:
            source_crs = CRS.from_wkt(prj_text)
            if source_crs.to_epsg() != 4326:
                transformer = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)
        except Exception:
            transformer = _get_transformer(source_epsg)
    else:
        if not source_epsg:
            raise HTTPException(400, "SHP dosyasında .prj yok — kaynak koordinat sisteminin EPSG kodunu belirtmelisiniz")
        transformer = _get_transformer(source_epsg)

    features = []
    for sr in reader.shapeRecords():
        geom = dict(sr.shape.__geo_interface__)
        if transformer:
            geom["coordinates"] = _transform_coords(geom["coordinates"], transformer)
        attrs = sr.record.as_dict() if hasattr(sr.record, "as_dict") else {}
        features.append({"geometry": geom, "properties": attrs})
    reader.close()
    return features


def _parse_dxf(content: bytes, source_epsg: Optional[int]) -> List[Dict[str, Any]]:
    if not source_epsg:
        raise HTTPException(400, "DXF dosyasının koordinat referans bilgisi yok — kaynak EPSG kodunu belirtmelisiniz")
    transformer = _get_transformer(source_epsg)

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        doc = ezdxf.readfile(tmp_path)
    finally:
        os.unlink(tmp_path)

    msp = doc.modelspace()
    features = []
    for e in msp:
        dxftype = e.dxftype()
        points, closed = None, False
        if dxftype == "LWPOLYLINE":
            points = [[p[0], p[1]] for p in e.get_points(format="xy")]
            closed = bool(e.closed)
        elif dxftype == "POLYLINE":
            points = [[v.dxf.location.x, v.dxf.location.y] for v in e.vertices]
            closed = bool(e.is_closed)
        if not points or len(points) < 2:
            continue
        if transformer:
            points = [list(transformer.transform(x, y)) for x, y in points]
        if closed and points[0] != points[-1]:
            points = points + [points[0]]
        geometry = {"type": "Polygon", "coordinates": [points]} if closed else {"type": "LineString", "coordinates": points}
        features.append({"geometry": geometry, "properties": {"layer": e.dxf.layer, "dxftype": dxftype}})
    return features


def register_geo_import_routes(api_router, db, current_user, require_permission, log_audit):

    @api_router.get("/geo-import/epsg-codes")
    async def list_common_epsg_codes(user=Depends(current_user)):
        return COMMON_EPSG_CODES

    @api_router.post("/geo-import/parse")
    async def parse_geo_file(
        file: UploadFile = File(...),
        source_epsg: Optional[int] = Form(None),
        user=Depends(require_permission("parcels:import_geojson")),
    ):
        """
        Dosyayı ayrıştırır, WGS84'e çevirir, SONUCU DÖNER — hiçbir şey
        kaydetmez (bkz. modül docstring'i — önizleme + onay akışı).
        """
        filename = (file.filename or "").lower()
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, "Dosya çok büyük (20 MB sınırı)")

        if filename.endswith(".ncz"):
            raise HTTPException(
                415,
                "NCZ (NetCAD) dosyaları desteklenmiyor — tescilli bir format. "
                "NetCAD'den SHP veya DXF olarak dışa aktarıp tekrar yükleyin. "
                "Dosyayı olduğu gibi saklamak isterseniz Belgeler sekmesinden yükleyebilirsiniz.",
            )
        elif filename.endswith(".geojson") or filename.endswith(".json"):
            features = _parse_geojson(content)
        elif filename.endswith(".kml"):
            features = _parse_kml(content)
        elif filename.endswith(".kmz"):
            features = _parse_kmz(content)
        elif filename.endswith(".zip"):
            features = _parse_shp_zip(content, source_epsg)
        elif filename.endswith(".dxf"):
            features = _parse_dxf(content, source_epsg)
        else:
            raise HTTPException(
                400,
                f"Desteklenmeyen dosya türü: {filename or '(adsız)'}. "
                "Desteklenenler: GeoJSON (.geojson/.json), KML (.kml), KMZ (.kmz), "
                "DXF (.dxf), SHP (.shp+.shx+.dbf+.prj içeren .zip)",
            )

        if not features:
            raise HTTPException(400, "Dosyadan hiç geometri okunamadı")

        return {"format": filename.rsplit(".", 1)[-1], "feature_count": len(features), "features": features}
