"""
=====================================================================
Toprax — Geometri Topoloji Doğrulaması (Denetim düzeltmesi, 2026-07-24)
=====================================================================
Denetim bulgusu: kullanıcı haritada parsel çizerken/bölerken kendi
kendini kesen (self-intersecting) poligonlar oluşturabiliyordu — bu,
$geoIntersects sorgularını ve uydu NDVI kırpma işlemlerini bozuyor.

SAF PYTHON — shapely BİLİNÇLİ olarak kullanılmadı (yeni bağımlılık
Karar Protokolü gereği kullanıcı onayı ister; parsel ring'leri küçük
olduğundan O(n²) segment-kesişim testi fazlasıyla yeterli).

Kullanım: `errors = validate_geometry(geom)` — hata yoksa boş liste,
varsa Türkçe hata mesajları. Çağıran taraf 400 fırlatır.
"""
from typing import Any, Dict, List, Optional


def _segments_properly_intersect(p1, p2, p3, p4) -> bool:
    """İki doğru parçasının (p1-p2, p3-p4) 'gerçek' kesişimi — uç nokta
    paylaşımı (ardışık kenarlar) kesişim SAYILMAZ."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = cross(p3, p4, p1)
    d2 = cross(p3, p4, p2)
    d3 = cross(p1, p2, p3)
    d4 = cross(p1, p2, p4)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
       ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    return False


def _validate_ring(ring: List[List[float]]) -> List[str]:
    errors: List[str] = []
    if not isinstance(ring, list) or len(ring) < 4:
        errors.append("Poligon halkası en az 4 nokta içermeli (kapanış noktası dahil)")
        return errors
    for pt in ring:
        if (not isinstance(pt, (list, tuple)) or len(pt) < 2 or
                not all(isinstance(c, (int, float)) for c in pt[:2])):
            errors.append("Geçersiz koordinat — [boylam, enlem] sayı çifti bekleniyor")
            return errors
        lng, lat = pt[0], pt[1]
        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
            errors.append(f"Koordinat aralık dışı: [{lng}, {lat}]")
            return errors
    if ring[0][:2] != ring[-1][:2]:
        errors.append("Poligon halkası kapalı değil — ilk ve son nokta aynı olmalı")
        return errors

    # Self-intersection: komşu olmayan kenar çiftleri arası gerçek kesişim.
    # Kapanış noktası tekrarını at, kenar listesi kur.
    pts = [tuple(p[:2]) for p in ring[:-1]]
    n = len(pts)
    if n < 3:
        errors.append("Poligon en az 3 farklı köşe içermeli")
        return errors
    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            # Komşu kenarlar (ve ilk-son kenar çifti) uç nokta paylaşır — atla.
            if abs(i - j) <= 1 or (i == 0 and j == n - 1):
                continue
            a1, a2 = edges[i]
            b1, b2 = edges[j]
            if _segments_properly_intersect(a1, a2, b1, b2):
                errors.append(
                    "Parsel geometrisi kendisiyle kesişiyor (self-intersection) — "
                    "çizimi düzeltin, kenarlar birbirinin üzerinden geçmemeli"
                )
                return errors
    return errors


def validate_geometry(geometry: Optional[Dict[str, Any]]) -> List[str]:
    """GeoJSON Polygon/MultiPolygon topoloji doğrulaması. Geometri None ise
    (geometrisiz parsel kaydına izin var) boş liste döner."""
    if not geometry:
        return []
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        rings = coords or []
    elif gtype == "MultiPolygon":
        rings = [ring for poly in (coords or []) for ring in poly]
    else:
        # Diğer tipler (Point vb.) bu doğrulamanın konusu değil — çağıran
        # taraf tip kısıtını kendisi koyar (örn. admin_areas bulk-import).
        return []
    errors: List[str] = []
    for ring in rings:
        errors.extend(_validate_ring(ring))
        if errors:
            break
    return errors
