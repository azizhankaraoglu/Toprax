"""
=====================================================================
TOPRAX — Karbon Ayak İzi & Sürdürülebilirlik
=====================================================================
Kullanıcı: "Harika fikir, hatta bu karta göre iyileştirmeleri önermeli ve
ne kadar fayda sağladığını da raporlayabilmeli."

Bu modül üç şey yapar:
  1. Parsel/sezon bazında **karbon ayak izi** (kg CO₂e) — yakıt, gübre
     (üretim + tarlada N₂O salımı), sulama enerjisi, bitki koruma.
  2. **İyileştirme önerileri** — her biri ölçülmüş bir girdiye dayalı ve
     tahmini kazancı (kg CO₂e ve TL) ile birlikte.
  3. **Fayda raporu** — bir öneri uygulandıktan sonra önce/sonra
     karşılaştırması (aynı hesap, iki farklı sezon girdisiyle).

EMİSYON KATSAYILARI — kaynak ve gerekçe kodda açıkça yazılır; "sihirli
sayı" bırakılmaz. Değerler IPCC 2019 Refinement ve yaygın LCA çalışmalarının
tarımsal ortalamalarıdır. Kesin muhasebe (ISO 14064 doğrulaması) İDDİA
EDİLMEZ — çıktı her zaman "tahmin" etiketiyle döner.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException

# --- Emisyon katsayıları -----------------------------------------------------
# Dizel: 2,68 kg CO₂/litre (yanma) + ~0,3 üretim/dağıtım → 2,98
DIESEL_KG_CO2_PER_L = 2.98
# Azotlu gübre: üretim ~4,0 kg CO₂e/kg N (Haber-Bosch) + tarlada doğrudan
# N₂O salımı IPCC varsayılanı %1 × 44/28 × 265 GWP ≈ 4,2 → toplam ~8,2
NITROGEN_KG_CO2E_PER_KG_N = 8.2
PHOSPHORUS_KG_CO2E_PER_KG_P = 1.5
POTASSIUM_KG_CO2E_PER_KG_K = 0.7
# Sulama: elektrikli pompa, ~0,35 kWh/m³ (100 m basma) × 0,45 kg CO₂/kWh (TR şebeke)
IRRIGATION_KG_CO2_PER_M3 = 0.16
# Bitki koruma ilacı: ~10 kg CO₂e/kg aktif madde (üretim ağırlıklı)
PESTICIDE_KG_CO2E_PER_KG = 10.0
# Toprak organik karbonu: %0,1 OM artışı ≈ 3,7 ton CO₂/ha depolama
SOC_TON_CO2_PER_OM_PERCENT_PER_HA = 3.7

#: Sulama yöntemine göre tipik dizel/enerji tüketimi çarpanı — salma sulama
#: aynı işi yapmak için ~2 kat su ve enerji ister.
IRRIGATION_ENERGY_FACTOR = {"damla": 1.0, "yagmurlama": 1.4, "karik": 1.8, "salma": 2.2}

#: Toprak işleme yoğunluğuna göre dekar başına dizel (litre).
TILLAGE_DIESEL_L_PER_DEKAR = {"geleneksel": 12.0, "azaltilmis": 7.0, "dogrudan_ekim": 3.5}


def carbon_footprint(area_dekar: float, *, nitrogen_kg: float = 0.0,
                     phosphorus_kg: float = 0.0, potassium_kg: float = 0.0,
                     irrigation_m3: float = 0.0, irrigation_method: str = "karik",
                     pesticide_kg: float = 0.0,
                     tillage: str = "geleneksel",
                     yield_ton: Optional[float] = None) -> Dict[str, Any]:
    """Parsel/sezon karbon ayak izi (kg CO₂e) + kalem dökümü."""
    diesel_l = TILLAGE_DIESEL_L_PER_DEKAR.get(tillage, 12.0) * area_dekar
    method = (irrigation_method or "karik").lower().replace("ı", "i").replace("ğ", "g").replace("ş", "s")
    irrigation_factor = IRRIGATION_ENERGY_FACTOR.get(method, 1.8)

    items = [
        {"kalem": "Toprak işleme / makine yakıtı", "miktar": round(diesel_l, 1), "birim": "L dizel",
         "kg_co2e": round(diesel_l * DIESEL_KG_CO2_PER_L, 1)},
        {"kalem": "Azotlu gübre", "miktar": round(nitrogen_kg, 1), "birim": "kg N",
         "kg_co2e": round(nitrogen_kg * NITROGEN_KG_CO2E_PER_KG_N, 1)},
        {"kalem": "Fosforlu gübre", "miktar": round(phosphorus_kg, 1), "birim": "kg P₂O₅",
         "kg_co2e": round(phosphorus_kg * PHOSPHORUS_KG_CO2E_PER_KG_P, 1)},
        {"kalem": "Potasyumlu gübre", "miktar": round(potassium_kg, 1), "birim": "kg K₂O",
         "kg_co2e": round(potassium_kg * POTASSIUM_KG_CO2E_PER_KG_K, 1)},
        {"kalem": "Sulama enerjisi", "miktar": round(irrigation_m3, 1), "birim": "m³",
         "kg_co2e": round(irrigation_m3 * IRRIGATION_KG_CO2_PER_M3 * irrigation_factor, 1)},
        {"kalem": "Bitki koruma", "miktar": round(pesticide_kg, 2), "birim": "kg a.m.",
         "kg_co2e": round(pesticide_kg * PESTICIDE_KG_CO2E_PER_KG, 1)},
    ]
    total = round(sum(i["kg_co2e"] for i in items), 1)
    return {
        "toplam_kg_co2e": total,
        "dekar_basina_kg_co2e": round(total / area_dekar, 1) if area_dekar else None,
        "ton_urun_basina_kg_co2e": round(total / yield_ton, 1) if yield_ton else None,
        "kalemler": sorted(items, key=lambda i: i["kg_co2e"], reverse=True),
        "yontem": "IPCC 2019 Refinement + tarımsal LCA ortalamaları — TAHMİNDİR, "
                  "ISO 14064 doğrulaması değildir.",
    }


def improvement_suggestions(footprint: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ölçülmüş girdilere dayalı iyileştirme önerileri + tahmini kazanç."""
    out: List[Dict[str, Any]] = []
    area = context.get("area_dekar") or 0
    by_item = {i["kalem"]: i for i in footprint.get("kalemler", [])}

    n_item = by_item.get("Azotlu gübre")
    soil_n = (context.get("soil") or {}).get("n_ppm")
    if n_item and n_item["miktar"] > 0 and soil_n and soil_n > 25:
        saving = round(n_item["kg_co2e"] * 0.25, 1)
        out.append({
            "baslik": "Azot dozunu toprak analizine göre %25 azaltın",
            "gerekce": f"Toprakta {soil_n} ppm azot ölçüldü — bitkinin ihtiyacının bir kısmı "
                       "topraktan karşılanıyor. Fazla azot hem karbon maliyeti hem POLAR KAYBI.",
            "kazanc_kg_co2e": saving,
            "kazanc_tl_tahmini": round(n_item["miktar"] * 0.25 * 28, 0),   # ~28 TL/kg N
            "ek_fayda": "Polar oranında artış beklenir",
            "kaynak": "soil_samples.n_ppm",
        })

    irrigation = by_item.get("Sulama enerjisi")
    method = (context.get("irrigation") or "").lower()
    if irrigation and irrigation["miktar"] > 0 and "damla" not in method:
        saving = round(irrigation["kg_co2e"] * 0.45, 1)
        out.append({
            "baslik": "Damla sulamaya geçin",
            "gerekce": f"Mevcut yöntem '{context.get('irrigation')}'. Damla sulama aynı bitki su "
                       "ihtiyacını ~%40 daha az su ve enerjiyle karşılar.",
            "kazanc_kg_co2e": saving,
            "kazanc_tl_tahmini": round(irrigation["miktar"] * 0.4 * 3.5, 0),   # ~3,5 TL/m³ maliyet
            "ek_fayda": "Su stresi azalır, verim istikrarı artar",
            "kaynak": "parcels.irrigation + irrigation_events",
        })

    tillage_item = by_item.get("Toprak işleme / makine yakıtı")
    if tillage_item and context.get("tillage", "geleneksel") == "geleneksel":
        saving = round(tillage_item["kg_co2e"] * 0.40, 1)
        out.append({
            "baslik": "Azaltılmış toprak işlemeye geçin",
            "gerekce": "Geleneksel toprak işleme dekara ~12 L dizel yakar ve toprak "
                       "organik karbonunu havaya salar.",
            "kazanc_kg_co2e": saving,
            "kazanc_tl_tahmini": round(area * 5 * 42, 0),                 # ~5 L/da × 42 TL
            "ek_fayda": "Mikrobiyal aktivite ve su tutma kapasitesi artar",
            "kaynak": "tillage",
        })

    om = (context.get("soil") or {}).get("organic_matter")
    if om is not None and om < 2.0 and area:
        # %0,5 OM artışı hedefi (3-5 yıllık) — depolanan karbon
        stored = round(0.5 * SOC_TON_CO2_PER_OM_PERCENT_PER_HA * 10 * (area / 10.0) * 1000 / 10, 0)
        out.append({
            "baslik": "Örtü bitkisi + organik gübre ile organik maddeyi artırın",
            "gerekce": f"Organik madde %{om} (hedef ≥ %2). Her %0,1 artış hektarda "
                       f"~{SOC_TON_CO2_PER_OM_PERCENT_PER_HA} ton CO₂ depolar.",
            "kazanc_kg_co2e": stored,
            "kazanc_tl_tahmini": None,
            "ek_fayda": "Su tutma kapasitesi ve verim istikrarı artar",
            "kaynak": "soil_samples.organic_matter",
        })
    return out


async def parcel_carbon(db, parcel: Dict[str, Any], season: Optional[int] = None) -> Dict[str, Any]:
    """Parselin sezon karbon ayak izi — GERÇEK kayıtlardan beslenir."""
    season = season or date.today().year
    area = parcel.get("area_dekar") or 0
    contract = await db.contracts.find_one({"parcel_id": parcel["id"], "season": season}, {"_id": 0})
    soil = await db.soil_samples.find_one({"parcel_id": parcel["id"]}, {"_id": 0},
                                          sort=[("sample_date", -1)])
    irrigation_events = await db.irrigation_events.find(
        {"parcel_id": parcel["id"], "season": season}, {"_id": 0}).to_list(1000)
    yield_rec = await db.yields.find_one({"parcel_id": parcel["id"], "season": season}, {"_id": 0})

    irrigation_m3 = sum((e.get("water_m3") or 0) for e in irrigation_events)
    # Gübre: sözleşmedeki avans miktarı gerçek uygulamanın en iyi vekilidir
    # (ayrı bir gübreleme kaydı modülü henüz yok — bu varsayım çıktıda belirtilir).
    fert_kg = (contract or {}).get("advance_fertilizer_kg") or (area * 22)
    nitrogen = fert_kg * 0.20          # tipik kompoze gübrede %20 N
    phosphorus = fert_kg * 0.10
    potassium = fert_kg * 0.10

    fp = carbon_footprint(
        area, nitrogen_kg=nitrogen, phosphorus_kg=phosphorus, potassium_kg=potassium,
        irrigation_m3=irrigation_m3, irrigation_method=parcel.get("irrigation") or "karik",
        pesticide_kg=area * 0.15, tillage=parcel.get("tillage") or "geleneksel",
        yield_ton=(yield_rec or {}).get("actual_ton"))

    ctx = {"area_dekar": area, "soil": soil, "irrigation": parcel.get("irrigation"),
           "tillage": parcel.get("tillage") or "geleneksel"}
    return {
        "parcel_id": parcel["id"], "season": season,
        "ayak_izi": fp,
        "oneriler": improvement_suggestions(fp, ctx),
        "varsayimlar": [
            "Gübre miktarı sözleşmedeki avans kaydından türetildi (ayrı gübreleme kaydı yok)",
            "Bitki koruma dekara 0,15 kg aktif madde varsayıldı",
            f"Toprak işleme yoğunluğu: {ctx['tillage']}",
        ],
    }


def register_sustainability_routes(api_router, db, current_user, require_permission,
                                   log_audit, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/sustainability/parcels/{parcel_id}")
    async def parcel_footprint(parcel_id: str, season: Optional[int] = None,
                               user=Depends(require_permission("parcels:view"))):
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        return await parcel_carbon(db, parcel, season)

    @api_router.get("/sustainability/parcels/{parcel_id}/benefit-report")
    async def benefit_report(parcel_id: str, onceki_sezon: int, sonraki_sezon: int,
                             user=Depends(require_permission("parcels:view"))):
        """İki sezonun ayak izini karşılaştırır — "ne kadar fayda sağladık"."""
        parcel = await db.parcels.find_one({"id": parcel_id}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        before = await parcel_carbon(db, parcel, onceki_sezon)
        after = await parcel_carbon(db, parcel, sonraki_sezon)
        b, a = before["ayak_izi"]["toplam_kg_co2e"], after["ayak_izi"]["toplam_kg_co2e"]
        return {
            "parcel_id": parcel_id,
            "onceki": {"sezon": onceki_sezon, "kg_co2e": b},
            "sonraki": {"sezon": sonraki_sezon, "kg_co2e": a},
            "degisim_kg_co2e": round(a - b, 1),
            "degisim_yuzde": round((a - b) / b * 100, 1) if b else None,
            "sonuc": ("İyileşme sağlandı" if a < b else "Ayak izi arttı" if a > b else "Değişim yok"),
            "kalem_karsilastirma": {
                i["kalem"]: {"onceki": i["kg_co2e"],
                             "sonraki": next((x["kg_co2e"] for x in after["ayak_izi"]["kalemler"]
                                              if x["kalem"] == i["kalem"]), None)}
                for i in before["ayak_izi"]["kalemler"]
            },
        }
