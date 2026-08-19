"""
=====================================================================
TOPRAX — Toprak Biyolojisi (canlı mikroorganizma envanteri + sağlık skoru)
=====================================================================
Kullanıcı isteği: "Toprak içindeki canlı mikroorganizmaların yer aldığı yeni
bir alan — hangi tarlada hangi canlı organizmalar var, manuel girilecek
şekilde, canlılık oranları ve gerekli tüm alanlar."

MODEL KARARI — neden AYRI koleksiyon (soil_samples'a kolon eklemek yerine):
  1. Biyolojik analiz FARKLI bir laboratuvar sürecidir; kimyasal analizden
     (pH/N/P/K) ayrı zamanda, ayrı fiyatla, çoğu zaman ayrı kurumda yapılır.
     Aynı satıra sıkıştırmak "kimyasal var, biyolojik yok" durumunu
     temsil edilemez hale getirirdi.
  2. Organizma listesi 1'e-ÇOK bir ilişkidir (bir örnekte birden fazla tür).
     CLAUDE.md konvansiyon #8 JSON blob'u yasaklıyor; ama IT-04'ün dosya
     istisnasındaki gerekçe burada da geçerli: gerçek ilişkisel veri, kolon
     değil kayıt olur. Bu yüzden organizmalar `soil_biology_organisms`
     koleksiyonunda AYRI satırlardır.

SKOR: `karne_engine.py`'nin ağırlıklı-bileşen deseniyle AYNI — ölçülmemiş
bileşen NÖTR SAYILMAZ, hesaptan çıkarılır ve kalan ağırlıklar yeniden
normalize edilir (veri yoksa uydurma puan verilmez).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

# =====================================================================
# ORGANİZMA KATALOĞU (kod-seviyesi registry — PERMISSION_CATALOG kalıbı)
# =====================================================================
# Şeker pancarı üretiminde pratik önemi olan organizmalar. `etki`:
#   faydali  → varlığı iyi, skora ARTI
#   zararli  → varlığı kötü, skora EKSİ (bazıları engelleyici)
#   notr     → gösterge (biyolojik aktivite işareti)
ORGANISM_CATALOG: List[Dict[str, Any]] = [
    # --- Faydalı bakteriler / mantarlar ---
    {"key": "rhizobium", "label": "Rhizobium (azot bağlayıcı)", "grup": "bakteri", "etki": "faydali",
     "aciklama": "Baklagil köklerinde ortak yaşar, havadan azot bağlar. Münavebede baklagil geçmişinin göstergesi."},
    {"key": "azotobacter", "label": "Azotobacter (serbest azot bağlayıcı)", "grup": "bakteri", "etki": "faydali",
     "aciklama": "Serbest yaşayan azot bağlayıcı; organik maddesi yüksek topraklarda bulunur."},
    {"key": "azospirillum", "label": "Azospirillum", "grup": "bakteri", "etki": "faydali",
     "aciklama": "Kök bölgesinde azot bağlar ve kök gelişimini uyarır."},
    {"key": "bacillus_subtilis", "label": "Bacillus subtilis", "grup": "bakteri", "etki": "faydali",
     "aciklama": "Kök patojenlerine karşı biyolojik mücadele ajanı; fosfor çözünürlüğünü artırır."},
    {"key": "pseudomonas_fluorescens", "label": "Pseudomonas fluorescens", "grup": "bakteri", "etki": "faydali",
     "aciklama": "Siderofor üretir, patojen mantarları baskılar."},
    {"key": "trichoderma", "label": "Trichoderma spp.", "grup": "mantar", "etki": "faydali",
     "aciklama": "Rhizoctonia/Fusarium gibi kök çürüklüğü etmenlerine karşı antagonist."},
    {"key": "mikoriza", "label": "Mikorizal mantarlar (AMF)", "grup": "mantar", "etki": "faydali",
     "aciklama": "Kök yüzeyini genişletir; fosfor ve su alımını artırır. Pancarda kolonizasyon düşüktür ama toprak sağlığı göstergesidir."},
    # --- Zararlılar / patojenler ---
    {"key": "heterodera_schachtii", "label": "Pancar Kist Nematodu (Heterodera schachtii)",
     "grup": "nematod", "etki": "zararli", "engelleyici": True,
     "aciklama": "Şeker pancarının en yıkıcı toprak kaynaklı zararlısı. Tespit edilen parselde en az 3-4 yıl pancar ekilmemeli."},
    {"key": "rhizoctonia_solani", "label": "Rhizoctonia solani (kök çürüklüğü)", "grup": "mantar", "etki": "zararli",
     "aciklama": "Kök ve kök boğazı çürüklüğü; sıcak-nemli koşullarda verim kaybı büyük."},
    {"key": "fusarium", "label": "Fusarium spp.", "grup": "mantar", "etki": "zararli",
     "aciklama": "Solgunluk ve kök çürüklüğü etmeni."},
    {"key": "pythium", "label": "Pythium spp.", "grup": "mantar", "etki": "zararli",
     "aciklama": "Fide kök yanıklığı (damping-off) — çıkış boşluklarının başlıca sebebi."},
    {"key": "cercospora", "label": "Cercospora beticola (yaprak lekesi)", "grup": "mantar", "etki": "zararli",
     "aciklama": "Yaprak lekesi hastalığı; yaprak alanını düşürerek polar oranını doğrudan azaltır."},
    {"key": "sclerotium", "label": "Sclerotium rolfsii", "grup": "mantar", "etki": "zararli",
     "aciklama": "Kök boğazı çürüklüğü; sıcak bölgelerde görülür."},
    {"key": "meloidogyne", "label": "Kök-ur Nematodu (Meloidogyne spp.)", "grup": "nematod", "etki": "zararli",
     "aciklama": "Köklerde ur oluşturur, su/besin alımını bozar."},
    # --- Gösterge canlılar ---
    {"key": "solucan", "label": "Toprak solucanı", "grup": "makrofauna", "etki": "faydali",
     "aciklama": "Toprak yapısı, havalanma ve organik madde döngüsünün en iyi saha göstergesi."},
    {"key": "aktinomiset", "label": "Aktinomisetler", "grup": "bakteri", "etki": "notr",
     "aciklama": "Organik madde ayrıştırıcı; toprağın 'yağmur sonrası kokusunu' verir."},
    {"key": "serbest_nematod", "label": "Serbest yaşayan nematodlar", "grup": "nematod", "etki": "notr",
     "aciklama": "Bakteri/mantar yiyen nematodlar — besin döngüsünün göstergesi, zararlı DEĞİL."},
    {"key": "protozoa", "label": "Protozoalar", "grup": "mikrofauna", "etki": "notr",
     "aciklama": "Bakteri popülasyonunu düzenler, azot mineralizasyonuna katkı verir."},
]
ORGANISM_BY_KEY = {o["key"]: o for o in ORGANISM_CATALOG}

#: Ölçüm alanlarının sağlıklı aralıkları — skor bu eşiklerden hesaplanır.
#: (alan, etiket, birim, düşük eşiği, yüksek/hedef eşiği, ağırlık)
MEASUREMENT_SPEC: List[Dict[str, Any]] = [
    {"key": "mikrobiyal_biyokutle_c", "label": "Mikrobiyal Biyokütle Karbonu", "birim": "mg/kg",
     "dusuk": 150, "hedef": 400, "agirlik": 20,
     "aciklama": "Topraktaki canlı mikrobiyal kütlenin doğrudan ölçüsü; toprak sağlığının en güçlü tek göstergesi."},
    {"key": "bazal_solunum", "label": "Bazal Solunum (CO₂)", "birim": "mg CO₂/kg/gün",
     "dusuk": 10, "hedef": 40, "agirlik": 15,
     "aciklama": "Mikrobiyal aktivitenin hızı — 'toprak nefes alıyor mu'."},
    {"key": "organik_madde_yuzde", "label": "Organik Madde", "birim": "%",
     "dusuk": 1.0, "hedef": 3.0, "agirlik": 20,
     "aciklama": "Tüm toprak canlılığının enerji kaynağı. Konya ovasında tipik değerler %1'in altındadır."},
    {"key": "solucan_sayisi_m2", "label": "Solucan Sayısı", "birim": "adet/m²",
     "dusuk": 30, "hedef": 150, "agirlik": 10,
     "aciklama": "Sahada sayılabilir; 100+ sağlıklı toprak işareti."},
    {"key": "mikoriza_kolonizasyon_yuzde", "label": "Mikoriza Kolonizasyonu", "birim": "%",
     "dusuk": 10, "hedef": 45, "agirlik": 10,
     "aciklama": "Kök örneğinde mikorizal yapı oranı."},
    {"key": "dehidrogenaz_aktivitesi", "label": "Dehidrogenaz Aktivitesi", "birim": "µg TPF/g/24s",
     "dusuk": 20, "hedef": 120, "agirlik": 8,
     "aciklama": "Genel mikrobiyal solunum enzimi."},
    {"key": "ureaz_aktivitesi", "label": "Üreaz Aktivitesi", "birim": "µg NH₄-N/g/2s",
     "dusuk": 20, "hedef": 100, "agirlik": 6,
     "aciklama": "Azot mineralizasyon kapasitesi."},
    {"key": "fosfataz_aktivitesi", "label": "Fosfataz Aktivitesi", "birim": "µg PNP/g/s",
     "dusuk": 100, "hedef": 500, "agirlik": 6,
     "aciklama": "Organik fosforu bitkiye açma kapasitesi."},
    {"key": "mantar_bakteri_orani", "label": "Mantar/Bakteri Oranı", "birim": "oran",
     "dusuk": 0.1, "hedef": 0.5, "agirlik": 5,
     "aciklama": "Tarla bitkilerinde 0,2-0,5 ideal kabul edilir; çok düşük değer yoğun toprak işlemenin izidir."},
]
MEASUREMENT_BY_KEY = {m["key"]: m for m in MEASUREMENT_SPEC}


class OrganismEntry(BaseModel):
    organism_key: str
    tespit_edildi: bool = True
    yogunluk: Optional[str] = None          # dusuk | orta | yuksek
    sayim_degeri: Optional[float] = None    # kob/g, adet/100 cm³ vb. (birim organizmaya bağlı)
    sayim_birimi: Optional[str] = None
    not_: Optional[str] = Field(default=None, alias="not")

    model_config = {"populate_by_name": True}


class SoilBiologyCreate(BaseModel):
    parcel_id: str
    sample_date: str                        # YYYY-MM-DD
    laboratuvar: Optional[str] = None
    derinlik_cm: Optional[int] = 30
    # Ölçümler (hepsi opsiyonel — laboratuvarın yaptığı kadarı girilir)
    mikrobiyal_biyokutle_c: Optional[float] = None
    bazal_solunum: Optional[float] = None
    organik_madde_yuzde: Optional[float] = None
    solucan_sayisi_m2: Optional[float] = None
    mikoriza_kolonizasyon_yuzde: Optional[float] = None
    dehidrogenaz_aktivitesi: Optional[float] = None
    ureaz_aktivitesi: Optional[float] = None
    fosfataz_aktivitesi: Optional[float] = None
    mantar_bakteri_orani: Optional[float] = None
    toplam_bakteri_kob_g: Optional[float] = None
    toplam_mantar_kob_g: Optional[float] = None
    c_n_orani: Optional[float] = None
    notlar: Optional[str] = None
    organizmalar: List[OrganismEntry] = Field(default_factory=list)


# =====================================================================
# SAF HESAP — DB'siz, test edilebilir
# =====================================================================

def score_measurement(key: str, value: Optional[float]) -> Optional[float]:
    """Tek ölçümün 0-100 puanı. Ölçülmemişse None (nötr 50 DEĞİL)."""
    spec = MEASUREMENT_BY_KEY.get(key)
    if spec is None or value is None:
        return None
    low, target = spec["dusuk"], spec["hedef"]
    if value <= low:
        return 0.0 if value <= low * 0.5 else round((value - low * 0.5) / (low * 0.5) * 40, 1)
    if value >= target:
        return 100.0
    return round(40 + (value - low) / (target - low) * 60, 1)


def soil_health_score(measurements: Dict[str, Optional[float]],
                      organisms: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Ağırlıklı toprak sağlığı skoru + gerekçe.

    ÖLÇÜLMEYEN BİLEŞEN HESABA GİRMEZ; kalan ağırlıklar yeniden normalize
    edilir (karne_engine.py ile AYNI ilke). Böylece tek bir ölçümle girilen
    bir örnek "eksik veri yüzünden düşük puan" almaz — ama `kapsam_yuzde`
    alanında kaç ağırlık biriminin gerçekten ölçüldüğü açıkça bildirilir.
    """
    parts, total_w, got_w = [], 0.0, 0.0
    for spec in MEASUREMENT_SPEC:
        total_w += spec["agirlik"]
        val = measurements.get(spec["key"])
        s = score_measurement(spec["key"], val)
        if s is None:
            continue
        got_w += spec["agirlik"]
        parts.append({"alan": spec["key"], "label": spec["label"], "deger": val,
                      "birim": spec["birim"], "puan": s, "agirlik": spec["agirlik"]})

    base = round(sum(p["puan"] * p["agirlik"] for p in parts) / got_w, 1) if got_w else None

    # Organizma etkisi: patojenler puanı düşürür, faydalılar yükseltir.
    org_delta, org_notes, blocking = 0.0, [], []
    for row in (organisms or []):
        meta = ORGANISM_BY_KEY.get(row.get("organism_key"))
        if not meta or not row.get("tespit_edildi"):
            continue
        yog = (row.get("yogunluk") or "orta").lower()
        magnitude = {"dusuk": 1.0, "orta": 2.0, "yuksek": 3.0}.get(yog, 2.0)
        if meta["etki"] == "faydali":
            org_delta += 1.5 * magnitude
            org_notes.append(f"+ {meta['label']} ({yog})")
        elif meta["etki"] == "zararli":
            org_delta -= 3.0 * magnitude
            org_notes.append(f"− {meta['label']} ({yog})")
            if meta.get("engelleyici"):
                blocking.append(meta["label"])

    final = None if base is None else round(max(0.0, min(100.0, base + org_delta)), 1)
    return {
        "skor": final,
        "olcum_skoru": base,
        "organizma_etkisi": round(org_delta, 1),
        "kapsam_yuzde": round(got_w / total_w * 100, 1) if total_w else 0.0,
        "bilesenler": parts,
        "organizma_notlari": org_notes,
        "engelleyici_organizmalar": blocking,
        "sinif": None if final is None else (
            "çok iyi" if final >= 80 else "iyi" if final >= 60 else
            "orta" if final >= 40 else "zayıf"),
    }


def biology_signals(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Kural motoruna verilecek sinyaller (agronomy.SIGNAL_CATALOG'a bağlanır)."""
    if not record:
        return {"toprak_sagligi_skoru": None, "mikrobiyal_biyokutle": None,
                "kist_nematodu_var": None, "patojen_sayisi": None, "solucan_sayisi_m2": None}
    orgs = record.get("organizmalar") or []
    pathogens = [o for o in orgs if o.get("tespit_edildi")
                 and (ORGANISM_BY_KEY.get(o.get("organism_key")) or {}).get("etki") == "zararli"]
    return {
        "toprak_sagligi_skoru": (record.get("saglik_skoru") or {}).get("skor"),
        "mikrobiyal_biyokutle": record.get("mikrobiyal_biyokutle_c"),
        "kist_nematodu_var": 1 if any(o.get("organism_key") == "heterodera_schachtii"
                                      and o.get("tespit_edildi") for o in orgs) else 0,
        "patojen_sayisi": len(pathogens),
        "solucan_sayisi_m2": record.get("solucan_sayisi_m2"),
    }


# =====================================================================
# HTTP YÜZEYİ
# =====================================================================

def register_soil_biology_routes(api_router, db, current_user, require_permission,
                                 log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    def _now():
        return datetime.now(timezone.utc).isoformat()

    @api_router.get("/soil-biology/catalog")
    async def catalog(user=Depends(current_user)):
        """Organizma kataloğu + ölçüm alanları — form ekranı bunu tüketir,
        etiketleri/açıklamaları HARDCODE ETMEZ (tek kaynak ilkesi)."""
        return {"organizmalar": ORGANISM_CATALOG, "olcumler": MEASUREMENT_SPEC}

    @api_router.get("/soil-biology")
    async def list_records(parcel_id: Optional[str] = None, limit: int = 100,
                           user=Depends(require_permission("soil:view"))):
        filt: Dict[str, Any] = {"is_active": {"$ne": False}}
        if parcel_id:
            filt["parcel_id"] = parcel_id
        return await db.soil_biology.find(filt, {"_id": 0}).sort(
            [("sample_date", -1)]).limit(min(limit, 500)).to_list(500)

    @api_router.get("/soil-biology/{record_id}")
    async def get_record(record_id: str, user=Depends(require_permission("soil:view"))):
        rec = await db.soil_biology.find_one({"id": record_id}, {"_id": 0})
        if not rec:
            raise HTTPException(404, "Kayıt bulunamadı")
        return rec

    @api_router.post("/soil-biology")
    async def create_record(body: SoilBiologyCreate, request: Request,
                            user=Depends(require_permission("soil:manage"))):
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0, "id": 1, "farmer_id": 1})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        unknown = [o.organism_key for o in body.organizmalar if o.organism_key not in ORGANISM_BY_KEY]
        if unknown:
            raise HTTPException(400, f"Bilinmeyen organizma: {', '.join(unknown)}")

        doc = body.model_dump(by_alias=True)
        organisms = doc.pop("organizmalar", [])
        measurements = {k: doc.get(k) for k in MEASUREMENT_BY_KEY}
        score = soil_health_score(measurements, organisms)

        doc.update({
            "id": str(uuid.uuid4()),
            "farmer_id": parcel.get("farmer_id"),
            "organizmalar": organisms,
            "saglik_skoru": score,
            "is_active": True,
            "created_at": _now(),
            "created_by": user.get("id") if isinstance(user, dict) else None,
        })
        await db.soil_biology.insert_one(dict(doc))
        doc.pop("_id", None)

        # Parselde hızlı erişim için özet (kural motoru her seferinde
        # koleksiyonu taramasın — remote_sensing.last_indices ile AYNI desen).
        await db.parcels.update_one({"id": body.parcel_id}, {"$set": {
            "soil_biology": {
                "son_kayit_id": doc["id"], "son_tarih": body.sample_date,
                "skor": score.get("skor"), "sinif": score.get("sinif"),
                "engelleyici_organizmalar": score.get("engelleyici_organizmalar"),
            }
        }})
        await log_audit(db, user, action="create", entity="soil_biology",
                        entity_id=doc["id"], new_value={"parcel_id": body.parcel_id,
                                                        "skor": score.get("skor")}, request=request)
        return doc

    @api_router.delete("/soil-biology/{record_id}")
    async def delete_record(record_id: str, request: Request,
                            user=Depends(require_permission("soil:manage"))):
        res = await db.soil_biology.update_one({"id": record_id}, {"$set": {"is_active": False}})
        if res.matched_count == 0:
            raise HTTPException(404, "Kayıt bulunamadı")
        await log_audit(db, user, action="delete", entity="soil_biology",
                        entity_id=record_id, request=request)
        return {"ok": True}

    @api_router.post("/soil-biology/score-preview")
    async def score_preview(body: Dict[str, Any], user=Depends(require_permission("soil:view"))):
        """Kaydetmeden skor önizleme — form doldurulurken canlı gösterilir
        (reconciliation.py'nin 'simulation' zarfıyla AYNI felsefe: yazmaz)."""
        measurements = {k: body.get(k) for k in MEASUREMENT_BY_KEY}
        return {"preview": True, **soil_health_score(measurements, body.get("organizmalar") or [])}
