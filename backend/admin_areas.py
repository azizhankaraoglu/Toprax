"""
=====================================================================
Toprax — İdari Alanlar + Demografi + Layer v1 (IT-13.6)
=====================================================================
İl/İlçe/Mahalle sınır geometrilerini (GeoJSON Polygon/MultiPolygon)
saklar. Sınır verisi SİSTEME GÖMÜLMEZ/SEED EDİLMEZ — kullanıcı
IT-13.5'in Geo Dosya İçe Aktarma akışıyla (geo_import.py) kendi SHP/
GeoJSON/KML/DXF dosyasını yükleyip haritada onaylar; tekli onay
`PUT /admin-areas/{id}` (`geometry` alanı) ile, TOPLU onay ise bu
modülün kendi `POST /admin-areas/bulk-import` ucuyla yapılır (tek
SHP'den çok sayıda idari alan — ad/tip alan eşleştirmesiyle).

"IT-01.5 lookup'larıyla tek kaynak ilkesi": il/ilçe İSİMLERİ zaten
field_definitions.py'nin `seed_il_ilce_lookup`'ıyla lookup_groups/
lookup_values'da tutuluyor (bkz. CLAUDE.md "İl/İlçe lookup verisi").
Bu modül o isimleri TEKRAR YAZMAZ — `lookup_value_id` alanıyla ilgili
lookup_value'ya REFERANS verir (isim orada tek yerde yönetilir).
`name` alanı sadece lookup'ta karşılığı olmayan seviyeler (mahalle,
veya lookup dışı özel bölgeler) için serbestçe girilir.

Demografi (nüfus/tarım alanı/tahmini çiftçi sayısı) convention #8
gereği gerçek tipli Pydantic kolonlarıdır (JSON blob YASAK) — bu
modülde SABİT tanımlıdır ama field_definitions (module="admin_areas")
üzerinden zorunlu/görünür/sıra davranışı yönetilir, tıpkı Farmer'ın
19 ek alanı gibi.
"""
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from pymongo.errors import BulkWriteError

AREA_TYPES = ("il", "ilce", "mahalle")
MAX_SIMPLIFY_POINTS = 300  # Layer v1 harita performansı için — sadece LİSTE/harita yanıtına uygulanır


def _simplify_ring(ring: List[List[float]], max_points: int) -> List[List[float]]:
    """Basit nokta atlama (decimation) — Douglas-Peucker DEĞİL, yeni bir
    kütüphane (shapely vb.) gerektirmeden 'haritada gösterim için yeterince
    hafif' bir sadeleştirme sağlar. İlk/son nokta (kapanış) her zaman kalır."""
    n = len(ring)
    if n <= max_points:
        return ring
    step = math.ceil(n / max_points)
    simplified = ring[::step]
    if simplified[-1] != ring[-1]:
        simplified.append(ring[-1])
    return simplified


def _simplify_geometry(geometry: Optional[Dict[str, Any]], max_points: int = MAX_SIMPLIFY_POINTS) -> Optional[Dict[str, Any]]:
    if not geometry:
        return geometry
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        return {"type": "Polygon", "coordinates": [_simplify_ring(ring, max_points) for ring in coords]}
    if gtype == "MultiPolygon":
        return {"type": "MultiPolygon", "coordinates": [[_simplify_ring(ring, max_points) for ring in poly] for poly in coords]}
    return geometry


def _dedupe_ring(ring: List[List[float]]) -> List[List[float]]:
    """Art arda gelen BİREBİR AYNI köşe noktalarını kaldırır. Gerçek TUIK/il-
    ilçe shapefile'larında (örn. 2026-07-25'te canlıda görülen "Hasankeyf"
    ilçesi) bu tür yinelenen köşeler sık rastlanan bir veri kalitesi
    sorunudur — MongoDB'nin 2dsphere indeksi "Loop is not valid ... Duplicate
    vertices" diyerek KAYDIN TAMAMINI reddediyordu (bkz. bulk_import_admin_
    areas). Sadece bitişik/aynı noktaları siler, halkanın şeklini değiştirmez."""
    if not ring:
        return ring
    cleaned = [ring[0]]
    for pt in ring[1:]:
        if pt != cleaned[-1]:
            cleaned.append(pt)
    return cleaned


def _clean_geometry(geometry: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Toplu içe aktarmadan gelen ham geometriyi MongoDB'nin 2dsphere
    indeksine yazılabilir hale getirir (bkz. _dedupe_ring)."""
    if not geometry:
        return geometry
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        return {**geometry, "coordinates": [_dedupe_ring(r) for r in coords]}
    if gtype == "MultiPolygon":
        return {**geometry, "coordinates": [[_dedupe_ring(r) for r in poly] for poly in coords]}
    return geometry


# =====================================================================
# #6 — SORUMLU KİŞİ (PORTFÖY) ÇÖZÜMLEYİCİ — köy bazlı MİRAS
# =====================================================================
# Karar (kullanıcı): parselin/çiftçinin hangi köye ait olduğu **İSİMLE**
# eşleştirilir (geometrik $geoIntersects DEĞİL) — parsel.village / parsel.mahalle
# veya çiftçi.village adı, `area_type="mahalle"` bir idari alanın adıyla
# (büyük/küçük harf ve boşluk duyarsız) karşılaştırılır. O idari alanın
# `responsible_user_id`'si o köydeki TÜM parsel/çiftçilere MİRAS kalır.

def _norm_name(v) -> str:
    return str(v or "").strip().lower()


async def find_area_for_village(db, village_name: str) -> Optional[Dict[str, Any]]:
    """Köy/mahalle ADINA göre idari alanı bulur (isimle eşleştirme kararı)."""
    name = _norm_name(village_name)
    if not name:
        return None
    areas = await db.admin_areas.find(
        {"area_type": "mahalle", "is_active": {"$ne": False}}, {"_id": 0}).to_list(5000)
    for a in areas:
        if _norm_name(a.get("name")) == name:
            return a
    return None


async def resolve_responsible(db, village_name: str) -> Optional[Dict[str, Any]]:
    """Köy adından SORUMLU personeli çözer. Dönen: {user_id, full_name, email,
    role, source_area_id, source_area_name} veya None (köy yok / sorumlu atanmamış)."""
    area = await find_area_for_village(db, village_name)
    if not area:
        return None
    uid = area.get("responsible_user_id")
    if not uid:
        return None
    u = await db.users.find_one({"id": uid}, {"_id": 0, "password": 0, "totp_secret": 0})
    if not u:
        return None
    return {
        "user_id": uid,
        "full_name": u.get("full_name") or u.get("email"),
        "email": u.get("email"),
        "role": u.get("role"),
        "source_area_id": area.get("id"),
        "source_area_name": area.get("name"),
    }


class AdminAreaDemographics(BaseModel):
    """İdari alanın demografik/tarımsal profili (2026-08-18).

    Kaynak: kullanıcının sağladığı `turkiye_iller/ilceler/mahalleler.geojson`
    dosyalarının `properties` bloğu. CLAUDE.md konvansiyon #8 gereği JSON blob
    DEĞİL, tipli alanlar — bu sayede Query Engine'de filtrelenebilir,
    SmartDataGrid'de kolon olur, harita popup'ında gösterilebilir ve ileride
    karar motoruna sinyal olarak bağlanabilir (ör. ilçe bazlı baskın ürün).

    ÜÇ SEVİYE TEK MODELDE: il dosyası ~18, ilçe/mahalle ~30 alan taşıyor ve
    kümeler büyük ölçüde ÖRTÜŞÜYOR. Seviye başına ayrı model açmak, ortak
    alanları (nüfus, gelir, CKS çiftçi sayısı, ürün/hayvan) üç kez tekrarlamak
    demekti; hepsi Optional olduğu için tek modelde toplandılar — bir seviyede
    olmayan alan basitçe None kalır.
    """
    # --- Kimlik/kod alanları (hiyerarşi bu KODLARLA kurulur, isimle DEĞİL) ---
    il_plaka: Optional[int] = None
    il_adi: Optional[str] = None
    ilce_kodu: Optional[int] = None
    ilce_adi: Optional[str] = None
    mahalle_kodu: Optional[int] = None
    mahalle_adi: Optional[str] = None
    display_name: Optional[str] = None
    bolge_adi: Optional[str] = None
    # --- Demografi ---
    nufus_toplam: Optional[int] = None
    hane_sayisi: Optional[int] = None
    hane_kisi_sayisi: Optional[float] = None
    kirsal_nufus_orani_yuzde: Optional[float] = None       # sadece il dosyasında
    kirsalsal_yerlesim: Optional[str] = None               # ilçe/mahalle: yerleşim sınıfı
    yas_0_17_yuzde: Optional[float] = None
    yas_18_49_yuzde: Optional[float] = None
    yas_50_64_yuzde: Optional[float] = None
    yas_65_ustu_yuzde: Optional[float] = None
    egitim_ilkokul_yuzde: Optional[float] = None
    egitim_orta_lise_yuzde: Optional[float] = None
    egitim_yuksekogretim_yuzde: Optional[float] = None
    hane_aylik_gelir_tl: Optional[float] = None
    gelir_seviyesi_grubu: Optional[str] = None
    # --- Tarımsal profil ---
    kayitli_cks_ciftci_sayisi: Optional[int] = None
    ciftci_yas_ortalamasi: Optional[float] = None
    kadin_ciftci_orani_yuzde: Optional[float] = None
    tarimsal_istihdam_orani_yuzde: Optional[float] = None
    islenen_tarim_arazisi_dekar: Optional[float] = None
    traktor_sayisi: Optional[int] = None
    baskin_urun_grubu: Optional[str] = None
    birinci_ana_urun: Optional[str] = None
    birinci_urun_rekolte_ton: Optional[float] = None
    ikinci_ana_urun: Optional[str] = None
    ikinci_urun_rekolte_ton: Optional[float] = None
    ucuncu_ana_urun: Optional[str] = None
    ucuncu_urun_rekolte_ton: Optional[float] = None
    kucukbas_hayvan_sayisi: Optional[int] = None
    buyukbas_hayvan_sayisi: Optional[int] = None


#: Demografi alanlarının makine-okunur listesi — import script'i, field_
#: definitions seed'i ve harita popup'ı AYNI listeden beslenir (tek kaynak).
DEMOGRAPHIC_FIELDS = list(AdminAreaDemographics.model_fields.keys())

#: Harita popup'ında gösterilecek ÖZET alanlar (hepsi değil — popup küçük).
#: Detayın tamamı Drawer'daki "Genel Bilgiler" bölümünde görünür.
POPUP_FIELDS = [
    "display_name", "nufus_toplam", "hane_sayisi", "kayitli_cks_ciftci_sayisi",
    "islenen_tarim_arazisi_dekar", "baskin_urun_grubu", "birinci_ana_urun",
    "hane_aylik_gelir_tl", "buyukbas_hayvan_sayisi", "kucukbas_hayvan_sayisi",
]

#: Türkçe etiketler — field_definitions seed'i ve popup bu sözlükten okur.
DEMOGRAPHIC_LABELS = {
    "il_plaka": "İl Plaka", "il_adi": "İl", "ilce_kodu": "İlçe Kodu", "ilce_adi": "İlçe",
    "mahalle_kodu": "Mahalle Kodu", "mahalle_adi": "Mahalle", "display_name": "Tam Ad",
    "bolge_adi": "Bölge",
    "nufus_toplam": "Toplam Nüfus", "hane_sayisi": "Hane Sayısı",
    "hane_kisi_sayisi": "Hane Başına Kişi", "kirsal_nufus_orani_yuzde": "Kırsal Nüfus Oranı (%)",
    "kirsalsal_yerlesim": "Yerleşim Sınıfı",
    "yas_0_17_yuzde": "Yaş 0-17 (%)", "yas_18_49_yuzde": "Yaş 18-49 (%)",
    "yas_50_64_yuzde": "Yaş 50-64 (%)", "yas_65_ustu_yuzde": "Yaş 65+ (%)",
    "egitim_ilkokul_yuzde": "Eğitim: İlkokul (%)", "egitim_orta_lise_yuzde": "Eğitim: Orta/Lise (%)",
    "egitim_yuksekogretim_yuzde": "Eğitim: Yükseköğretim (%)",
    "hane_aylik_gelir_tl": "Hane Aylık Gelir (TL)", "gelir_seviyesi_grubu": "Gelir Seviyesi",
    "kayitli_cks_ciftci_sayisi": "Kayıtlı ÇKS Çiftçi Sayısı",
    "ciftci_yas_ortalamasi": "Çiftçi Yaş Ortalaması",
    "kadin_ciftci_orani_yuzde": "Kadın Çiftçi Oranı (%)",
    "tarimsal_istihdam_orani_yuzde": "Tarımsal İstihdam Oranı (%)",
    "islenen_tarim_arazisi_dekar": "İşlenen Tarım Arazisi (dekar)",
    "traktor_sayisi": "Traktör Sayısı", "baskin_urun_grubu": "Baskın Ürün Grubu",
    "birinci_ana_urun": "1. Ana Ürün", "birinci_urun_rekolte_ton": "1. Ürün Rekolte (ton)",
    "ikinci_ana_urun": "2. Ana Ürün", "ikinci_urun_rekolte_ton": "2. Ürün Rekolte (ton)",
    "ucuncu_ana_urun": "3. Ana Ürün", "ucuncu_urun_rekolte_ton": "3. Ürün Rekolte (ton)",
    "kucukbas_hayvan_sayisi": "Küçükbaş Hayvan Sayısı",
    "buyukbas_hayvan_sayisi": "Büyükbaş Hayvan Sayısı",
}


class AdminAreaCreate(AdminAreaDemographics):
    name: str
    area_type: str                                   # il | ilce | mahalle
    parent_id: Optional[str] = None                  # üst idari alan (admin_areas.id)
    lookup_value_id: Optional[str] = None             # IT-01.5 tek kaynak ilkesi — il/ilçe lookup_value referansı
    geometry: Optional[Dict[str, Any]] = None          # GeoJSON Polygon/MultiPolygon
    # ============ B1 (portföy) — köy/mahalle SORUMLUSU ============
    # Bir köye/mahalleye atanan sorumlu personel (users.id). O alandaki çiftçi
    # ve parseller bu sorumluyu DEVRALIR (köy bazlı miras — bkz. #6). Boş olabilir.
    responsible_user_id: Optional[str] = None

    # ============ IT-13.6 — Demografi (field_definitions module="admin_areas") ============
    population: Optional[int] = None
    agricultural_area_dekar: Optional[float] = None
    farmer_count_est: Optional[int] = None


class AdminAreaUpdate(AdminAreaDemographics):
    name: Optional[str] = None
    area_type: Optional[str] = None
    parent_id: Optional[str] = None
    lookup_value_id: Optional[str] = None
    responsible_user_id: Optional[str] = None
    geometry: Optional[Dict[str, Any]] = None
    population: Optional[int] = None
    agricultural_area_dekar: Optional[float] = None
    farmer_count_est: Optional[int] = None
    is_active: Optional[bool] = None


class BulkImportRequest(BaseModel):
    area_type: str                                    # bu importtaki TÜM feature'lar aynı tip (il/ilçe/mahalle)
    name_field: str                                    # SHP/DXF attribute'larından hangisi "ad" (ör. "ad", "ILCE_ADI")
    parent_id: Optional[str] = None                    # opsiyonel — hepsi aynı üst alana bağlanacaksa
    features: List[Dict[str, Any]] = []                 # geo_import.py'nin /geo-import/parse çıktısı (features listesi)


class BulkDeleteRequest(BaseModel):
    area_ids: List[str]


def register_admin_area_routes(api_router, db, current_user, require_permission, log_audit, require_feature=None):
    # God Mode Modül Yönetimi — "admin_areas" flag'i kapatılınca liste 403 döner.
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/admin-areas/meta")
    async def admin_area_meta(user=Depends(current_user), _feat=Depends(require_feature("admin_areas"))):
        return {"area_types": [{"key": t, "label": {"il": "İl", "ilce": "İlçe", "mahalle": "Mahalle"}[t]} for t in AREA_TYPES]}

    @api_router.get("/admin-areas")
    async def list_admin_areas(
        area_type: Optional[str] = None, parent_id: Optional[str] = None,
        bbox: Optional[str] = None, limit: int = 1500,
        q: Optional[str] = None, geometry: bool = True,
        user=Depends(require_permission("admin_areas:view")),
        _feat=Depends(require_feature("admin_areas")),
    ):
        """Liste/harita katmanı yanıtı — geometri Layer v1 performansı için sadeleştirilir.

        **`bbox` (2026-08-19)** — "minLon,minLat,maxLon,maxLat". Gerçek
        il/ilçe/mahalle verisi yüklendikten sonra bu koleksiyonda 51 BİNDEN
        fazla kayıt var; eski hâlde uç, ada göre sıralayıp ilk 2000'i
        döndürüyordu — yani haritada hangi bölgeye bakılırsa bakılsın
        alfabenin başındaki ilgisiz mahalleler geliyor, kullanıcının
        ekranında "3-5 poligon" görünüyordu (canlıda bildirildi).
        Artık harita görünür alanını gönderiyor, sunucu yalnızca o alanla
        KESİŞEN sınırları veriyor (2dsphere indeksi zaten mevcut).
        """
        query: Dict[str, Any] = {"is_active": {"$ne": False}}
        if area_type:
            query["area_type"] = area_type
        if parent_id:
            query["parent_id"] = parent_id
        if bbox:
            try:
                min_lon, min_lat, max_lon, max_lat = [float(v) for v in bbox.split(",")]
            except (ValueError, AttributeError):
                raise HTTPException(400, "bbox biçimi: minLon,minLat,maxLon,maxLat")
            query["geometry"] = {"$geoIntersects": {"$geometry": {
                "type": "Polygon",
                "coordinates": [[[min_lon, min_lat], [max_lon, min_lat],
                                 [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]],
            }}}
        # `q` (2026-08-19) — ada göre arama. Bu koleksiyonda 51 binden fazla
        # kayıt var; üst-alan seçici gibi ekranlar eskiden parametresiz
        # `GET /admin-areas` çağırıp DOĞAL SIRADAKİ ilk 1500 kaydı alıyordu —
        # yani listede "sadece birkaç il görünüyor" şikâyeti. Artık seçici
        # hem seviyeye hem aramaya göre daraltılmış istek atıyor.
        if q and len(q.strip()) >= 1:
            query["name"] = {"$regex": re.escape(q.strip()), "$options": "i"}

        # `geometry=false` — seçici/dropdown gibi SADECE ad-id isteyen
        # tüketiciler sınır poligonlarını indirmemeli (bir il poligonu
        # binlerce köşe taşıyabiliyor; 1500 kayıtta bu megabaytlar demek).
        projection = {"_id": 0} if geometry else {"_id": 0, "geometry": 0}
        cursor = db.admin_areas.find(query, projection)
        if not bbox:
            cursor = cursor.sort("name", 1)
        docs = await cursor.limit(max(1, min(limit, 3000))).to_list(3000)
        if geometry:
            for d in docs:
                d["geometry"] = _simplify_geometry(d.get("geometry"))
        return docs

    @api_router.get("/admin-areas/at")
    async def admin_areas_at_point(lon: float, lat: float,
                                   user=Depends(require_permission("admin_areas:view")),
                                   _feat=Depends(require_feature("admin_areas"))):
        """Bir NOKTAYA düşen il / ilçe / mahalle üçlüsü.

        Haritada bir parsele VEYA boş bir alana tıklandığında açılan popup
        bunu çağırır: kullanıcı il/ilçe/mahalle/parsel bağlantılarından
        birine tıklayıp o kaydın detayına gider (2026-08-19 kullanıcı isteği).

        Eşleştirme GERÇEK SINIRLA ($geoIntersects) yapılır — parselin
        `il`/`ilce` metin alanlarıyla DEĞİL: o alanlar içe aktarma sırasında
        yazılır ve sınır düzeltmelerinden sonra bayatlayabilir.
        """
        point = {"type": "Point", "coordinates": [lon, lat]}
        out: Dict[str, Any] = {}
        for t in AREA_TYPES:
            doc = await db.admin_areas.find_one(
                {"area_type": t, "geometry": {"$geoIntersects": {"$geometry": point}}},
                {"_id": 0, "id": 1, "name": 1, "area_type": 1, "nufus_toplam": 1,
                 "kayitli_cks_ciftci_sayisi": 1, "islenen_tarim_arazisi_dekar": 1,
                 "baskin_urun_grubu": 1})
            out[t] = doc
        return out

    @api_router.get("/admin-areas/counts")
    async def admin_area_counts(user=Depends(require_permission("admin_areas:view")),
                                _feat=Depends(require_feature("admin_areas"))):
        """Seviye başına kayıt sayısı — katman seçicisi "Mahalle (50.130)" gibi
        gösterip kullanıcıya verinin gerçekten yüklü olduğunu bildirir."""
        out = {}
        for t in AREA_TYPES:
            out[t] = await db.admin_areas.count_documents({"area_type": t, "is_active": {"$ne": False}})
        return out

    @api_router.get("/admin-areas/{area_id}")
    async def get_admin_area(area_id: str, user=Depends(require_permission("admin_areas:view")),
                              _feat=Depends(require_feature("admin_areas"))):
        """Tam hassasiyetli geometri — düzenleme/onay ekranı için sadeleştirilmez."""
        doc = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        if not doc:
            raise HTTPException(404, "İdari alan bulunamadı")
        return doc

    @api_router.post("/admin-areas")
    async def create_admin_area(body: AdminAreaCreate, request: Request, user=Depends(require_permission("admin_areas:manage")),
                                 _feat=Depends(require_feature("admin_areas"))):
        if body.area_type not in AREA_TYPES:
            raise HTTPException(400, f"Geçersiz alan tipi: {body.area_type}. Geçerli değerler: {AREA_TYPES}")
        if body.parent_id and not await db.admin_areas.find_one({"id": body.parent_id}, {"_id": 0}):
            raise HTTPException(404, "Üst idari alan bulunamadı")
        doc = body.model_dump()
        doc["id"] = str(uuid.uuid4())
        doc["is_active"] = True
        doc["created_by"] = user.get("full_name") or user.get("email")
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.admin_areas.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="admin_area", entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/admin-areas/{area_id}")
    async def update_admin_area(area_id: str, body: AdminAreaUpdate, request: Request, user=Depends(require_permission("admin_areas:manage")),
                                 _feat=Depends(require_feature("admin_areas"))):
        old = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "İdari alan bulunamadı")
        if body.area_type is not None and body.area_type not in AREA_TYPES:
            raise HTTPException(400, f"Geçersiz alan tipi: {body.area_type}. Geçerli değerler: {AREA_TYPES}")
        if body.parent_id and not await db.admin_areas.find_one({"id": body.parent_id}, {"_id": 0}):
            raise HTTPException(404, "Üst idari alan bulunamadı")
        # responsible_user_id="" → sorumluyu KALDIR (None'a çevir; boş string saklanmaz).
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "responsible_user_id" in updates and updates["responsible_user_id"] == "":
            updates["responsible_user_id"] = None
        if not updates:
            raise HTTPException(400, "Güncellenecek alan yok")
        await db.admin_areas.update_one({"id": area_id}, {"$set": updates})
        new = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="admin_area", entity_id=area_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/admin-areas/{area_id}")
    async def delete_admin_area(area_id: str, request: Request, user=Depends(require_permission("admin_areas:manage")),
                                 _feat=Depends(require_feature("admin_areas"))):
        """Soft delete — convention #3, alt idari alanlar/geçmiş referanslar bozulmasın diye."""
        old = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "İdari alan bulunamadı")
        await db.admin_areas.update_one({"id": area_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="delete", entity="admin_area", entity_id=area_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # SON HAL #7 — toplu silme (grid'de çoklu seçim + tek çağrı). Tekli
    # DELETE ile AYNI soft-delete davranışı; bulunamayan id'ler sessizce
    # atlanır (kullanıcı zaten seçtiği satırların var olduğunu bilir).
    @api_router.post("/admin-areas/bulk-delete")
    async def bulk_delete_admin_areas(body: BulkDeleteRequest, request: Request,
                                       user=Depends(require_permission("admin_areas:manage")),
                                       _feat=Depends(require_feature("admin_areas"))):
        deleted = 0
        for area_id in body.area_ids:
            old = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
            if not old:
                continue
            await db.admin_areas.update_one({"id": area_id}, {"$set": {"is_active": False}})
            await log_audit(db, user, action="delete", entity="admin_area", entity_id=area_id, old_value=old, request=request)
            deleted += 1
        return {"status": "deactivated", "deleted_count": deleted}

    @api_router.get("/portfolio/{user_id}")
    async def user_portfolio(user_id: str, user=Depends(require_permission("admin_areas:view")),
                              _feat=Depends(require_feature("admin_areas"))):
        """#6 — Bir personelin PORTFÖYÜ: sorumlu olduğu köyler + o köylerdeki
        (isimle eşleşen) çiftçi/parsel özeti. Sorumluluk köy seviyesindedir,
        parsel/çiftçi bunu devralır."""
        areas = await db.admin_areas.find(
            {"responsible_user_id": user_id, "is_active": {"$ne": False}}, {"_id": 0}).to_list(1000)
        names = {_norm_name(a.get("name")) for a in areas if a.get("name")}
        if not names:
            return {"user_id": user_id, "areas": [], "farmer_count": 0, "parcel_count": 0,
                    "total_area_dekar": 0, "parcels": [], "farmers": []}

        parcels = await db.parcels.find(
            {"is_active": {"$ne": False}},
            {"_id": 0, "id": 1, "name": 1, "parcel_code": 1, "village": 1, "mahalle": 1,
             "area_dekar": 1, "ekim_durumu": 1, "farmer_id": 1}).to_list(20000)
        farmers = await db.farmers.find(
            {"is_active": {"$ne": False}},
            {"_id": 0, "id": 1, "full_name": 1, "member_no": 1, "village": 1, "phone": 1}).to_list(20000)

        my_parcels = [p for p in parcels
                      if _norm_name(p.get("village")) in names or _norm_name(p.get("mahalle")) in names]
        my_farmers = [f for f in farmers if _norm_name(f.get("village")) in names]
        return {
            "user_id": user_id,
            "areas": [{"id": a.get("id"), "name": a.get("name"), "area_type": a.get("area_type")} for a in areas],
            "farmer_count": len(my_farmers),
            "parcel_count": len(my_parcels),
            "total_area_dekar": round(sum(p.get("area_dekar") or 0 for p in my_parcels), 1),
            "ekili_parcels": sum(1 for p in my_parcels if p.get("ekim_durumu") == "ekili"),
            "parcels": my_parcels[:200],
            "farmers": my_farmers[:200],
        }

    @api_router.post("/admin-areas/bulk-import")
    async def bulk_import_admin_areas(body: BulkImportRequest, request: Request, user=Depends(require_permission("admin_areas:manage")),
                                       _feat=Depends(require_feature("admin_areas"))):
        """
        Tek bir SHP/GeoJSON/KML dosyasından ayrıştırılmış (geo_import.py
        /geo-import/parse ÇIKTISI, henüz hiçbir yere kaydedilmemiş)
        birden fazla feature'ı toplu idari alan kaydına çevirir. Idempotent
        DEĞİLDİR — aynı dosya iki kez içe aktarılırsa iki kez kayıt oluşur
        (kullanıcı önizleme ekranında bunu görüp bilinçli onaylar).
        """
        if body.area_type not in AREA_TYPES:
            raise HTTPException(400, f"Geçersiz alan tipi: {body.area_type}. Geçerli değerler: {AREA_TYPES}")
        if not body.features:
            raise HTTPException(400, "İçe aktarılacak feature bulunamadı")

        # Denetim düzeltmesi (2026-07-24) — bu döngü ÖNCEDEN her feature için
        # AYRI bir `await db.admin_areas.insert_one(doc)` yapıyordu; ~60.000
        # mahalle gibi büyük bir toplu içe aktarmada bu, 60.000 SIRALI
        # network round-trip'i demektir (dakikalarca sürer, nginx/proxy
        # timeout'una takılır — "hata veriyor" şikayetinin İKİNCİ kök nedeni,
        # birincisi nginx'in client_max_body_size'ıydı, bkz. Dockerfile.
        # frontend). Şimdi TÜM dokümanlar önce bellekte toplanır, sonra
        # `insert_many` ile PARÇALAR (chunk) halinde tek seferde yazılır —
        # aynı sonucu saniyeler içinde verir.
        created = []
        # Denetim STAB-B1 (2026-07-24): Point/LineString feature'lar eskiden
        # SESSİZCE atlanıyordu — kullanıcı `ilceler.geojson` gibi nokta bazlı
        # bir dosya yükleyince "0 kayıt" görüp nedenini anlayamıyordu. Artık
        # atlanan tip başına sayılıp yanıtta Türkçe uyarı dönülür.
        skipped_by_type: Dict[str, int] = {}
        docs = []
        for f in body.features:
            geom = f.get("geometry")
            if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
                gtype = (geom or {}).get("type") or "geometrisiz"
                skipped_by_type[gtype] = skipped_by_type.get(gtype, 0) + 1
                continue  # idari sınır için Point/LineString atlanır
            name = (f.get("properties") or {}).get(body.name_field) or "(adsız)"
            docs.append({
                "id": str(uuid.uuid4()), "name": str(name), "area_type": body.area_type,
                "parent_id": body.parent_id, "lookup_value_id": None, "geometry": _clean_geometry(geom),
                "population": None, "agricultural_area_dekar": None, "farmer_count_est": None,
                "is_active": True, "created_by": user.get("full_name") or user.get("email"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        # Denetim düzeltmesi (2026-07-25) — canlıda gerçek "ilçe" dosyasıyla
        # bulundu: _clean_geometry bitişik yinelenen köşeleri temizler ama
        # bazı kaynak dosyalarda BAŞKA geçersizlikler de olabilir (self-
        # intersection vb.) — bunlar MongoDB'nin 2dsphere indeksinde
        # `BulkWriteError` fırlatır. ESKİDEN bu, TÜM isteği 500 Internal
        # Server Error ile çökertiyordu (kullanıcıya "sunucuda hata" olarak
        # görünüyordu) ve `ordered` varsayılanı (True) o ANA KADAR chunk
        # içinde başarıyla eklenmiş kayıtları da yarım bırakıyordu.
        # `ordered=False` ile MongoDB chunk'taki TÜM geçerli kayıtları yazar,
        # sadece geçersiz olanları atlar; hangi kayıtların atlandığını
        # `writeErrors[].index`'ten çözüp kullanıcıya Türkçe isim listesiyle
        # bildiriyoruz.
        CHUNK = 2000
        geo_error_names: List[str] = []
        for i in range(0, len(docs), CHUNK):
            chunk = docs[i:i + CHUNK]
            try:
                await db.admin_areas.insert_many(chunk, ordered=False)
                created.extend(chunk)
            except BulkWriteError as e:
                failed_idx = {err["index"] for err in e.details.get("writeErrors", [])}
                for idx, d in enumerate(chunk):
                    if idx in failed_idx:
                        geo_error_names.append(d["name"])
                    else:
                        created.append(d)
        for d in created:
            d.pop("_id", None)

        warnings = [
            f"{cnt} kayıt '{gtype}' tipinde olduğu için atlandı — idari sınır için "
            f"Polygon/MultiPolygon geometrisi gerekir"
            for gtype, cnt in skipped_by_type.items()
        ]
        if geo_error_names:
            preview = ", ".join(geo_error_names[:10]) + ("…" if len(geo_error_names) > 10 else "")
            warnings.append(
                f"{len(geo_error_names)} kayıt geçersiz/kendisiyle kesişen geometri nedeniyle "
                f"atlandı (kaynak dosyadaki sınır verisi hatalı): {preview}"
            )
        if not created and warnings:
            warnings.append(
                "Hiçbir kayıt içe aktarılamadı. Nokta (Point) bazlı bir dosya yüklediyseniz "
                "sınır (poligon) içeren bir kaynak dosya kullanın."
            )
        await log_audit(db, user, action="create", entity="admin_area", entity_id="bulk_import",
                         new_value={"count": len(created), "area_type": body.area_type,
                                    "skipped": skipped_by_type}, request=request)
        return {"status": "imported", "count": len(created), "warnings": warnings}

    @api_router.get("/admin-areas/{area_id}/summary")
    async def admin_area_summary(area_id: str, user=Depends(require_permission("admin_areas:view")),
                                  _feat=Depends(require_feature("admin_areas"))):
        """
        O idari alanın sınırı İÇİNDEKİ çiftçi/parselleri döner —
        Mongo'nun $geoIntersects'i (2dsphere index, bkz. server.py başlangıç
        index'leri) ile GERÇEK geometrik kesişim hesaplanır, village/region
        eşleştirmesi gibi kaba bir yaklaşıklık DEĞİLDİR.
        """
        area = await db.admin_areas.find_one({"id": area_id}, {"_id": 0})
        if not area:
            raise HTTPException(404, "İdari alan bulunamadı")
        if not area.get("geometry"):
            return {"area": area, "parcel_count": 0, "farmer_count": 0, "parcels": []}

        parcels = await db.parcels.find(
            {"geometry": {"$geoIntersects": {"$geometry": area["geometry"]}}}, {"_id": 0}
        ).to_list(2000)
        farmer_ids = {p["farmer_id"] for p in parcels if p.get("farmer_id")}
        return {
            "area": area,
            "parcel_count": len(parcels),
            "farmer_count": len(farmer_ids),
            "parcels": [{"id": p["id"], "name": p.get("name"), "parcel_code": p.get("parcel_code")} for p in parcels],
        }
