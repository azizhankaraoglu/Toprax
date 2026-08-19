"""
=====================================================================
TOPRAX — Sezon Karar Takvimi (ekim öncesinden hasada karar desteği)
=====================================================================
Kullanıcının 10. maddesi: "Elimizdeki tüm verilerle ekim planlamasından
(güneş dahil), ekimi, gübreden ilaca, sulamadan hasata kadar bir şablon
çıkarıp çiftçilere doğru karar destek mekanizmalığı yapmak."

NASIL ÇALIŞIR
-------------
1. **Fenolojik aşama** ürünün ekim tarihinden ve büyüme derece-gün (GDD)
   birikiminden hesaplanır — takvimden DEĞİL. Aynı takvim gününde soğuk
   geçen bir sezonda bitki daha geridedir; GDD bunu yakalar.
2. Her aşamanın **kontrol listesi** vardır; her kontrol, sistemdeki GERÇEK
   bir ölçümü sorgular (toprak analizi, uydu indeksi, güneş/gölge, su
   bütçesi, toprak biyolojisi, hava tahmini, kök sayısı).
3. Çıktı **karar kartları**: ne yapılmalı, ne zaman, NEDEN (hangi ölçüme
   dayanarak) ve hangi güvenle. Ölçüm yoksa karar üretilmez — yerine
   "şu ölçüm eksik" uyarısı çıkar (sayı uydurulmaz).
4. Kabul edilen karar mevcut modüllere yazılır (Saha Görevi / sulama /
   ekim kaydı) — YENİ bir görev sistemi icat edilmez.

Bu modül kendi kural dilini İCAT ETMEZ: agronomy.py'nin kural motoru
"bu parselde bu ürün ekilir mi" sorusunu yanıtlar; burası "ekildikten sonra
sezon boyunca ne yapılmalı" sorusunu yanıtlar. İkisi farklı zaman
ölçeklerinde çalışır ve birbirinin çıktısını tüketir.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

# =====================================================================
# FENOLOJİ — GDD tabanlı aşama tanımları
# =====================================================================
# Şeker pancarı için GDD eşikleri (taban 3 °C). Kaynak: yaygın pancar
# fenolojisi (çıkış ~130 GDD, 8 yaprak ~450, örtü kapanması ~900,
# kök büyümesi ~1600, şeker birikimi ~2100, hasat olgunluğu ~2400).
PHENOLOGY = {
    "pancar": [
        {"key": "hazirlik", "label": "Ekim Öncesi Hazırlık", "gdd_min": None, "gdd_max": 0,
         "aciklama": "Toprak hazırlığı, analiz, çeşit ve tohum kararı"},
        {"key": "ekim", "label": "Ekim", "gdd_min": 0, "gdd_max": 130,
         "aciklama": "Ekim ve çıkış öncesi dönem"},
        {"key": "cikis", "label": "Çıkış ve Fide", "gdd_min": 130, "gdd_max": 450,
         "aciklama": "Çıkış, seyreltme, ilk yabancı ot mücadelesi"},
        {"key": "yaprak_gelisimi", "label": "Yaprak Gelişimi", "gdd_min": 450, "gdd_max": 900,
         "aciklama": "Hızlı yaprak büyümesi, azot ihtiyacının zirvesi"},
        {"key": "ortu_kapanmasi", "label": "Örtü Kapanması", "gdd_min": 900, "gdd_max": 1600,
         "aciklama": "Sıra araları kapanır, su tüketimi zirveye çıkar"},
        {"key": "kok_buyumesi", "label": "Kök Büyümesi", "gdd_min": 1600, "gdd_max": 2100,
         "aciklama": "Kök kütlesi artışı; azot azaltılır, potasyum önem kazanır"},
        {"key": "seker_birikimi", "label": "Şeker Birikimi", "gdd_min": 2100, "gdd_max": 2400,
         "aciklama": "Yaprak yaşlanır, şeker köke taşınır — su kesme dönemi"},
        {"key": "hasat", "label": "Hasat", "gdd_min": 2400, "gdd_max": None,
         "aciklama": "Söküm olgunluğu"},
    ],
}
DEFAULT_PHENOLOGY_KEY = "pancar"


def stage_for_gdd(gdd: Optional[float], crop_key: str = DEFAULT_PHENOLOGY_KEY,
                  planted: bool = True) -> Dict[str, Any]:
    """GDD birikiminden fenolojik aşama."""
    stages = PHENOLOGY.get(crop_key, PHENOLOGY[DEFAULT_PHENOLOGY_KEY])
    if not planted:
        return stages[0]
    if gdd is None:
        return stages[1]
    for st in stages:
        lo = st["gdd_min"]
        hi = st["gdd_max"]
        if lo is None:
            continue
        if gdd >= lo and (hi is None or gdd < hi):
            return st
    return stages[-1]


# =====================================================================
# KARAR ÜRETİCİLER
# =====================================================================
# Her üretici: (context) -> karar kartı listesi. Kart şeması:
#   {konu, baslik, aciklama, gerekce[], aciliyet, onerilen_tarih,
#    guven, eylem{tip, payload}, kaynak_olcumler[]}
#
# `aciliyet`: acil | yakin | planla | bilgi
# `eylem.tip`: saha_gorevi | sulama_kaydi | ekim_kaydi | analiz_iste | yok

def _card(konu: str, baslik: str, aciklama: str, gerekce: List[str], aciliyet: str,
          guven: float, kaynaklar: List[str], tarih: Optional[str] = None,
          eylem: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "konu": konu, "baslik": baslik, "aciklama": aciklama,
        "gerekce": gerekce, "aciliyet": aciliyet,
        "onerilen_tarih": tarih or date.today().isoformat(),
        "guven": round(guven, 2),
        "kaynak_olcumler": kaynaklar,
        "eylem": eylem or {"tip": "yok"},
    }


def decide_soil(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Toprak analizi ve gübreleme kararları."""
    out = []
    soil = ctx.get("soil")
    stage = ctx["stage"]["key"]
    if not soil:
        out.append(_card(
            "toprak", "Toprak analizi yaptırın",
            "Bu parselde kayıtlı toprak analizi yok. Gübreleme, kireçleme ve su "
            "bütçesi hesapları analiz olmadan tahmine dayanır.",
            ["Parselde hiç toprak analizi kaydı bulunamadı"],
            "acil" if stage in ("hazirlik", "ekim") else "planla",
            0.95, ["soil_samples"],
            eylem={"tip": "saha_gorevi", "payload": {"task_type": "Toprak Numunesi"}}))
        return out

    ph = soil.get("ph")
    if ph is not None:
        if ph < 6.0:
            out.append(_card(
                "toprak", "Kireçleme gerekli",
                f"Toprak pH değeri {ph} — şeker pancarı için ideal aralık 6,5-7,5. "
                "Asitli toprakta kök gelişimi ve şeker oranı düşer.",
                [f"Toprak analizi pH = {ph}"], "planla", 0.9, ["soil_samples.ph"]))
        elif ph > 8.2:
            out.append(_card(
                "toprak", "Yüksek pH — mikro besin alımı riskli",
                f"pH {ph}: demir, çinko ve mangan alımı kısıtlanabilir. Yapraktan "
                "mikro besin takviyesi planlanmalı.",
                [f"Toprak analizi pH = {ph}"], "bilgi", 0.8, ["soil_samples.ph"]))

    om = soil.get("organic_matter")
    if om is not None and om < 1.5:
        out.append(_card(
            "toprak", "Organik madde düşük",
            f"Organik madde %{om}. Çiftlik gübresi, yeşil gübre veya sap-saman "
            "toprağa karıştırma planlanmalı; su tutma kapasitesi ve mikrobiyal "
            "canlılık doğrudan buna bağlı.",
            [f"Organik madde = %{om} (hedef ≥ %2)"], "planla", 0.85,
            ["soil_samples.organic_matter"]))

    n = soil.get("n_ppm")
    if n is not None and stage in ("kok_buyumesi", "seker_birikimi") and n > 30:
        out.append(_card(
            "gubreleme", "Azotu kesin",
            f"Toprakta {n} ppm azot var ve bitki kök/şeker dönemine girdi. Bu "
            "dönemde azot vermek yaprağı büyütür, POLAR ORANINI DÜŞÜRÜR.",
            [f"Toprak azotu = {n} ppm", f"Fenolojik aşama: {ctx['stage']['label']}"],
            "acil", 0.9, ["soil_samples.n_ppm", "fenoloji"]))

    k = soil.get("k_ppm")
    if k is not None and k < 200 and stage in ("yaprak_gelisimi", "ortu_kapanmasi"):
        out.append(_card(
            "gubreleme", "Potasyum takviyesi yapın",
            f"Toprak potasyumu {k} ppm (hedef ≥ 250). Potasyum şekerin yapraktan "
            "köke taşınmasını sağlar; eksikliği doğrudan polar kaybıdır.",
            [f"Toprak K = {k} ppm"], "yakin", 0.85, ["soil_samples.k_ppm"]))
    return out


def decide_water(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Su bütçesinden sulama kararı."""
    water = ctx.get("water")
    if not water or not water.get("available"):
        return []
    rec = water.get("oneri") or {}
    stage = ctx["stage"]["key"]
    out = []

    if stage == "seker_birikimi":
        out.append(_card(
            "sulama", "Hasat öncesi suyu kesin",
            "Bitki şeker birikimi dönemine girdi. Son 3-4 haftada su kesmek "
            "polar oranını yükseltir; sulamaya devam etmek şekeri seyreltir.",
            [f"Fenolojik aşama: {ctx['stage']['label']}"], "yakin", 0.85,
            ["fenoloji", "water_budget"]))
        return out

    if rec.get("sulama_gerekli"):
        gerekce = [
            f"Toprak su açığı {water['kapasite']['guncel_acik_mm']} mm "
            f"(kritik eşik {water['kapasite']['raw_mm']} mm)",
            f"Son 30 gün yağış {water['hava_ozeti'].get('yagis_son_30_gun_mm')} mm, "
            f"buharlaşma {water['hava_ozeti'].get('et0_son_30_gun_mm')} mm",
        ]
        randiman_pct = int((rec.get("randiman") or 0) * 100)
        out.append(_card(
            "sulama", f"Sulama yapın — {rec.get('brut_ihtiyac_m3')} m³",
            f"Net {rec.get('net_ihtiyac_mm')} mm su gerekiyor; sulama randımanı "
            f"%{randiman_pct} ile brüt {rec.get('brut_ihtiyac_mm')} mm "
            f"({rec.get('brut_ihtiyac_m3')} m³) uygulanmalı.",
            gerekce, "acil", 0.9,
            ["water_budget", "open-meteo", "soil_samples"],
            eylem={"tip": "sulama_kaydi", "payload": {"water_m3": rec.get("brut_ihtiyac_m3")}}))
    elif rec.get("beklenen_stres_tarihi"):
        out.append(_card(
            "sulama", "Sulamayı planlayın",
            f"Tahmine göre {rec['beklenen_stres_tarihi']} tarihinde su stresi "
            "başlıyor. Sulama o güne planlanmalı.",
            [f"Tahmini stres tarihi: {rec['beklenen_stres_tarihi']}",
             f"Güncel doluluk %{water['oneri'].get('doluluk_yuzde')}"],
            "yakin", 0.8, ["water_budget", "open-meteo"],
            tarih=rec["beklenen_stres_tarihi"]))
    return out


def decide_satellite(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Uydu indekslerinden bitki sağlığı kararları."""
    idx = ctx.get("indices") or {}
    out = []
    if not idx:
        out.append(_card(
            "uydu", "Uydu analizi çalıştırın",
            "Bu parsel için uydu ölçümü yok. Bitki sağlığı, su stresi ve "
            "olgunlaşma takibi uydu indeksleri olmadan yapılamaz.",
            ["remote_sensing kaydı bulunamadı"], "planla", 0.9, ["remote_sensing"],
            eylem={"tip": "uydu_analizi", "payload": {}}))
        return out

    ndvi = idx.get("ndvi")
    msi = idx.get("msi")
    ndre = idx.get("ndre")
    stage = ctx["stage"]["key"]

    if ndvi is not None and stage in ("yaprak_gelisimi", "ortu_kapanmasi") and ndvi < 0.55:
        out.append(_card(
            "bitki_sagligi", "Bitki gelişimi zayıf",
            f"NDVI {ndvi} — bu aşamada 0,65 üzeri beklenir. Besin eksikliği, su "
            "stresi veya hastalık olabilir; yerinde kontrol gerekli.",
            [f"NDVI = {ndvi}", f"Aşama: {ctx['stage']['label']}"], "yakin", 0.75,
            ["remote_sensing.ndvi"],
            eylem={"tip": "saha_gorevi", "payload": {"task_type": "Ekim Kontrolü"}}))

    if msi is not None and msi > 1.3:
        out.append(_card(
            "su_stresi", "Uydu su stresi gösteriyor",
            f"Nem stresi indeksi (MSI) {msi} — 1,3 üzeri su stresi işaretidir. "
            "Su bütçesi hesabıyla birlikte değerlendirin.",
            [f"MSI = {msi}"], "yakin", 0.7, ["remote_sensing.msi"]))

    if ndre is not None and stage in ("yaprak_gelisimi",) and ndre < 0.25:
        out.append(_card(
            "gubreleme", "Azot durumu düşük görünüyor",
            f"NDRE {ndre} — yaprak gelişimi döneminde düşük klorofil/azot "
            "göstergesi. Yaprak analizi ile teyit edip üst gübre planlayın.",
            [f"NDRE = {ndre}"], "yakin", 0.7, ["remote_sensing.ndre"]))
    return out


def decide_sun(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Güneş/gölge analizinden kararlar."""
    solar = ctx.get("solar") or {}
    if not solar.get("available"):
        return []
    out = []
    yeterlilik = solar.get("yeterlilik") or {}
    if yeterlilik.get("durum") == "yetersiz":
        out.append(_card(
            "gunes", "Parsel yeterli güneş almıyor",
            f"Günlük etkin güneşlenme {yeterlilik.get('olculen_saat')} saat; bu ürün "
            f"için {yeterlilik.get('gerekli_saat')} saat gerekir "
            f"(karşılanma %{yeterlilik.get('karsilanma_yuzde')}). Gölgeli parsellerde "
            "verim ve şeker oranı düşer — ürün seçimi gözden geçirilmeli.",
            [f"Etkin güneşlenme: {yeterlilik.get('olculen_saat')} saat/gün",
             f"Bakı: {(solar.get('arazi') or {}).get('baki')}",
             f"Ortalama gölge oranı: %{solar.get('ortalama_golge_orani_yuzde')}"],
            "bilgi", 0.8, ["solar.copernicus_dem"]))
    aspect = (solar.get("arazi") or {}).get("baki")
    slope = (solar.get("arazi") or {}).get("egim_yuzde")
    if slope is not None and slope > 8:
        out.append(_card(
            "arazi", "Eğim yüksek — erozyon ve sulama riski",
            f"Parsel eğimi %{slope}. Karık/salma sulamada su yüzeyden akar, "
            "üst toprak taşınır. Damla sulama ve eş yükselti ekimi önerilir.",
            [f"Eğim = %{slope}", f"Bakı = {aspect}"], "bilgi", 0.85,
            ["solar.copernicus_dem"]))
    return out


def decide_biology(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Toprak biyolojisinden kararlar."""
    bio = ctx.get("biology") or {}
    if not bio:
        return []
    out = []
    if bio.get("kist_nematodu_var"):
        out.append(_card(
            "hastalik", "Pancar kist nematodu tespit edildi",
            "Bu parselde Heterodera schachtii tespit edilmiş. En az 3-4 yıl "
            "pancar ekilmemeli; dayanıklı çeşit veya tuzak bitki (yağ turpu) "
            "ile popülasyon düşürülmeli.",
            ["Toprak biyolojisi kaydında kist nematodu pozitif"], "acil", 0.95,
            ["soil_biology"]))
    skor = bio.get("toprak_sagligi_skoru")
    if skor is not None and skor < 40:
        out.append(_card(
            "toprak", "Toprak biyolojik sağlığı zayıf",
            f"Toprak sağlığı skoru {skor}/100. Organik madde takviyesi, azaltılmış "
            "toprak işleme ve örtü bitkisi ile mikrobiyal aktivite artırılmalı.",
            [f"Toprak sağlığı skoru = {skor}"], "planla", 0.8, ["soil_biology"]))
    return out


def decide_harvest(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Olgunlaşma/söküm kararları."""
    harvest = ctx.get("harvest") or {}
    window = harvest.get("sokum_penceresi") or {}
    if not window.get("available"):
        return []
    out = []
    idx = window.get("olgunlasma_endeksi")
    if idx is not None and idx >= 80:
        out.append(_card(
            "hasat", "Söküm olgunluğuna ulaşıldı",
            f"Olgunlaşma endeksi {idx}/100. Beklenen polar "
            f"%{window.get('beklenen_polar')} "
            f"({window.get('polar_araligi')}). Söküm penceresi "
            f"{window.get('onerilen_baslangic')} – {window.get('onerilen_bitis')}.",
            [f"Olgunlaşma endeksi = {idx}",
             f"Polar tahmini = %{window.get('beklenen_polar')}"] + (window.get("engeller") or []),
            "acil", 0.85, ["remote_sensing", "polar_engine"],
            tarih=window.get("onerilen_baslangic"),
            eylem={"tip": "saha_gorevi", "payload": {"task_type": "Hasat Kontrolü"}}))
    elif idx is not None:
        out.append(_card(
            "hasat", "Söküm zamanı yaklaşıyor",
            window.get("oneri", ""),
            [f"Olgunlaşma endeksi = {idx}",
             f"Tahmini olgunluk: {window.get('tahmini_olgunluk_tarihi')}"],
            "planla", 0.7, ["remote_sensing", "polar_engine"],
            tarih=window.get("tahmini_olgunluk_tarihi")))
    return out


def decide_stand(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Kök sayısı / çıkış düzgünlüğü kararları."""
    stand = ctx.get("stand") or {}
    if not stand:
        return []
    out = []
    uniformity = stand.get("cikis_duzgunlugu_yuzde")
    if uniformity is not None and uniformity < 80 and ctx["stage"]["key"] in ("cikis", "yaprak_gelisimi"):
        out.append(_card(
            "ekim", "Çıkış düzgünlüğü düşük",
            f"Hedef sıklığın %{uniformity}'ine ulaşılmış. Boşluklar verimi doğrudan "
            "düşürür; boşluk haritası çıkarılıp gerekirse tamamlama ekimi "
            "değerlendirilmeli.",
            [f"Hesaplanan bitki/dekar: {stand.get('hesaplanan_bitki_dekar')}",
             f"Hedef: {stand.get('hedef_bitki_dekar')}"],
            "yakin", 0.75, ["plantings", "crop_stand"],
            eylem={"tip": "saha_gorevi", "payload": {"task_type": "Ekim Kontrolü"}}))
    return out


DECIDERS = [decide_soil, decide_water, decide_satellite, decide_sun,
            decide_biology, decide_stand, decide_harvest]


# =====================================================================
# BAĞLAM TOPLAMA + PLAN ÜRETİMİ
# =====================================================================

async def build_context(db, parcel: Dict[str, Any], season: int,
                        crop_key: str = "pancar") -> Dict[str, Any]:
    """Tüm ölçüm kaynaklarını TEK bir bağlamda toplar."""
    from weather import get_parcel_weather, accumulate_gdd, base_temp_for
    from water_budget import analyze_parcel_water
    from polar_engine import analyze_parcel_harvest
    from crop_stand import compute_stand
    from soil_biology import biology_signals
    from remote_sensing.solar import solar_signals

    planting = await db.plantings.find_one({"parcel_id": parcel["id"], "season": season},
                                           {"_id": 0}, sort=[("season", -1)])
    soil = await db.soil_samples.find_one({"parcel_id": parcel["id"]}, {"_id": 0},
                                          sort=[("sample_date", -1)])
    bio_rec = await db.soil_biology.find_one({"parcel_id": parcel["id"], "is_active": {"$ne": False}},
                                             {"_id": 0}, sort=[("sample_date", -1)])
    weather = await get_parcel_weather(db, parcel, crop_key)

    gdd = None
    if planting and planting.get("planting_date") and weather.get("available"):
        days = [d for d in weather["daily"] if d["date"] >= planting["planting_date"]]
        gdd = accumulate_gdd(days, base_temp_for(crop_key))

    stage = stage_for_gdd(gdd, crop_key, planted=bool(planting))
    water = await analyze_parcel_water(db, parcel, crop_key, season)
    harvest = await analyze_parcel_harvest(db, parcel, season, crop_key) \
        if stage["key"] in ("kok_buyumesi", "seker_birikimi", "hasat") else {}

    return {
        "parcel": parcel,
        "season": season,
        "crop": crop_key,
        "planting": planting,
        "soil": soil,
        "biology": biology_signals(bio_rec),
        "solar": parcel.get("solar") or {},
        "indices": (parcel.get("remote_sensing") or {}).get("last_indices") or {},
        "weather": weather,
        "water": water,
        "harvest": harvest,
        "stand": compute_stand(planting, parcel.get("area_dekar"), crop_key) if planting else {},
        "gdd": gdd,
        "stage": stage,
    }


async def build_season_plan(db, parcel: Dict[str, Any], season: Optional[int] = None,
                            crop_key: str = "pancar") -> Dict[str, Any]:
    """Parselin sezon karar takvimi."""
    season = season or date.today().year
    ctx = await build_context(db, parcel, season, crop_key)

    cards: List[Dict[str, Any]] = []
    for decider in DECIDERS:
        try:
            cards.extend(decider(ctx))
        except Exception as e:  # noqa: BLE001
            # TEK bir karar üreticisinin hatası TÜM takvimi düşürmemeli.
            cards.append(_card("sistem", "Bir karar kuralı çalıştırılamadı", str(e)[:200],
                               [f"Üretici: {decider.__name__}"], "bilgi", 0.0, []))

    oncelik = {"acil": 0, "yakin": 1, "planla": 2, "bilgi": 3}
    cards.sort(key=lambda c: (oncelik.get(c["aciliyet"], 9), c["onerilen_tarih"]))

    from confidence import build_badge, states_from_context
    varsayimlar = (ctx.get("water") or {}).get("varsayimlar") or []
    guven = build_badge(states_from_context(ctx), varsayimlar)

    stages = PHENOLOGY.get(crop_key, PHENOLOGY[DEFAULT_PHENOLOGY_KEY])
    return {
        "veri_guveni": guven,
        "parcel_id": parcel["id"],
        "parcel_name": parcel.get("name"),
        "season": season,
        "crop": crop_key,
        "gdd_birikimi": ctx["gdd"],
        "asama": ctx["stage"],
        "asamalar": stages,
        "kararlar": cards,
        "ozet": {
            "acil": sum(1 for c in cards if c["aciliyet"] == "acil"),
            "yakin": sum(1 for c in cards if c["aciliyet"] == "yakin"),
            "planla": sum(1 for c in cards if c["aciliyet"] == "planla"),
            "toplam": len(cards),
        },
        "veri_durumu": {
            "toprak_analizi": bool(ctx.get("soil")),
            "uydu_olcumu": bool(ctx.get("indices")),
            "gunes_analizi": bool((ctx.get("solar") or {}).get("available")),
            "toprak_biyolojisi": bool((ctx.get("biology") or {}).get("toprak_sagligi_skoru")),
            "hava_verisi": bool((ctx.get("weather") or {}).get("available")),
            "ekim_kaydi": bool(ctx.get("planting")),
        },
    }


# =====================================================================
# HTTP YÜZEYİ
# =====================================================================

class AcceptDecision(BaseModel):
    parcel_id: str
    karar: Dict[str, Any]
    assigned_to: Optional[str] = None
    planned_date: Optional[str] = None


def register_season_planner_routes(api_router, db, current_user, require_permission,
                                   log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    def _now():
        return datetime.now(timezone.utc).isoformat()

    @api_router.get("/season-planner/parcels/{parcel_id}")
    async def parcel_plan(parcel_id: str, season: Optional[int] = None, crop: str = "pancar",
                          user=Depends(require_permission("parcels:view"))):
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        return await build_season_plan(db, parcel, season, crop)

    @api_router.get("/season-planner/phenology")
    async def phenology(crop: str = "pancar", user=Depends(current_user)):
        return {"crop": crop, "asamalar": PHENOLOGY.get(crop, PHENOLOGY[DEFAULT_PHENOLOGY_KEY])}

    @api_router.post("/season-planner/accept")
    async def accept_decision(body: AcceptDecision, request: Request,
                              user=Depends(require_permission("field_ops:manage"))):
        """Kabul edilen kararı MEVCUT modüllere yazar.

        Yeni bir "karar kaydı" koleksiyonu icat edilmez: kabul edilen karar
        ne ise o modülün gerçek kaydı olur (saha görevi, sulama kaydı). Böylece
        takip, bildirim ve raporlama zaten çalışan mekanizmalardan yürür.
        """
        parcel = await db.parcels.find_one({"id": body.parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        karar = body.karar or {}
        eylem = karar.get("eylem") or {}
        tip = eylem.get("tip")
        result: Dict[str, Any] = {"tip": tip}

        if tip == "saha_gorevi":
            from field_ops import create_field_task_from_rule
            task_type_name = (eylem.get("payload") or {}).get("task_type")
            tt = await db.task_types.find_one({"name": task_type_name, "is_active": {"$ne": False}},
                                              {"_id": 0, "id": 1})
            if not tt:
                raise HTTPException(400, f"'{task_type_name}' görev tipi tanımlı değil — "
                                         "Görev Tipleri ekranından ekleyin")
            if not body.assigned_to:
                raise HTTPException(400, "Görev ataması için personel seçilmelidir")
            # İmza `field_ops.create_field_task_from_rule` ile birebir: bu
            # fonksiyon `POST /tasks` ile AYNI doküman şemasını üretir
            # (IT-24'te otomasyon motoru için çıkarılmıştı, burada da
            # HTTP context'i olmayan bir çağrı olduğu için aynısı kullanılır).
            task = await create_field_task_from_rule(
                db, task_type_id=tt["id"], assigned_to=body.assigned_to,
                farmer_id=parcel.get("farmer_id"), parcel_id=body.parcel_id,
                priority="yuksek" if karar.get("aciliyet") == "acil" else "normal",
                planned_date=body.planned_date or karar.get("onerilen_tarih"),
                created_by="sezon karar takvimi")
            result["field_task"] = task
        elif tip == "sulama_kaydi":
            doc = {
                "id": str(uuid.uuid4()), "parcel_id": body.parcel_id,
                "farmer_id": parcel.get("farmer_id"),
                "date": body.planned_date or date.today().isoformat(),
                "water_m3": (eylem.get("payload") or {}).get("water_m3"),
                "method": parcel.get("irrigation"),
                "kaynak": "sezon_karar_takvimi",
                "created_at": _now(),
            }
            await db.irrigation_events.insert_one(dict(doc))
            doc.pop("_id", None)
            result["irrigation_event"] = doc
        elif tip == "uydu_analizi":
            from remote_sensing.tasks import create_task
            from remote_sensing.indices import ALL_INDEX_CODES
            await create_task(db, parcel_id=body.parcel_id, task_type="statistics",
                              indices=list(ALL_INDEX_CODES), trigger="season_planner", priority=80)
            result["queued"] = True
        else:
            raise HTTPException(400, f"Bu karar için otomatik eylem yok (tip={tip})")

        await log_audit(db, user, action="accept_decision", entity="season_planner",
                        entity_id=body.parcel_id,
                        new_value={"konu": karar.get("konu"), "tip": tip}, request=request)
        return {"ok": True, **result}
