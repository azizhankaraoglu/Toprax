"""
=====================================================================
Toprax — Demo Senaryo Oynatıcı (OTURUM-DEVAM-19082026.md madde 10)
=====================================================================
Amaç: satış/demo sunumlarında platformu baştan sona anlatan, gerçek
ekranlara giden adım adım bir "tur". YENİ bir sahte veri kümesi
İCAT ETMEZ/GÖSTERMEZ — sistemdeki GERÇEK, en dolu (parsel + üretim
sezonu + sözleşme + toprak analizi zinciri tam olan) çiftçiyi bulup
adımların içine yerleştirir; öyle bir kayıt yoksa o adım "örnek veri
henüz yok" notuyla dürüstçe atlanır (crop_classification.py'nin "veri
kısıtını sessizce gizleme" ilkesiyle aynı).

`scripts/demo_scenario.py` (repo kökü) bu adımların TAMAMLAYICISI:
sunumdan önce isteğe bağlı çalıştırılan, "DEMO —" önekli/kolayca
tespit edilip silinebilir bir örnek çiftçi/parsel/sezon zinciri
oluşturan BAĞIMSIZ bir script (server import etmez, mevcut REST
API'lere gerçek HTTP isteğiyle bağlanır — postman koleksiyonu
üreticisiyle AYNI "scripts/" klasörü, farklı çalışma şekli: o
introspection yapar, bu gerçek veri yazar). Bilinçli olarak
OTOMATİK ÇALIŞTIRILMAZ (server başlangıcına bağlanmadı) — canlı/
üretim veritabanına yazma işlemi HER ZAMAN elle tetiklenir.

Senaryo adımları kod-seviyesi sabit bir liste (DEMO_STEPS) — yeni bir
"senaryo düzenleyici" ekranı İCAT EDİLMEDİ, ROADMAP'te bu kapsamda
istenmedi.
"""
from fastapi import Depends

DEMO_STEPS = [
    {
        "id": "genel-bakis",
        "title": "1. Kooperatif Genel Bakış",
        "narration": "Dashboard, sözleşme/gerçekleşme/NDVI/alan muhasebesi KPI'larını "
                      "canlı verilerle gösterir — hiçbiri sabit demo sayısı değildir.",
        "route": "/",
    },
    {
        "id": "ciftci",
        "title": "2. Çiftçi Portföyü",
        "narration": "Her çiftçinin 360° görünümü: iletişim bilgileri, parselleri, "
                      "sözleşmeleri, karne skoru ve iletişim geçmişi tek ekranda.",
        "route": "/ciftciler/{farmer_id}",
        "requires": "farmer_id",
    },
    {
        "id": "parsel",
        "title": "3. Parsel ve Harita",
        "narration": "Parsel detayında kadastro bilgisi, toprak/sulama durumu, üretim "
                      "sezonları ve TKGM/harita entegrasyonu bir arada.",
        "route": "/parseller/{parcel_id}",
        "requires": "parcel_id",
    },
    {
        "id": "ekim-karar",
        "title": "4. Ne Ekmeliyim? (Ekim Karar Motoru)",
        "narration": "Toprak analizi, münavebe geçmişi ve uydu verisini birleştirip "
                      "parsel bazlı ekim uygunluk skoru üretir.",
        "route": "/ekim?view=karar-motoru",
    },
    {
        "id": "toprak",
        "title": "5. Toprak Analizleri",
        "narration": "Fiziksel/kimyasal analiz sonuçları + mikro besin elementleri, "
                      "GPS izli mobil numune akışıyla sahadan gelir.",
        "route": "/toprak",
    },
    {
        "id": "uydu",
        "title": "6. Uzaktan Algılama",
        "narration": "NDVI/NDRE/su stresi gibi 9 uydu indeksi ve zaman serisi; veri "
                      "yoksa sistem bunu uydurmaz, dürüstçe 'veri yok' der.",
        "route": "/uzaktan-algilama",
    },
    {
        "id": "saha",
        "title": "7. Saha Operasyonları",
        "narration": "İş emri → görev → ziyaret zinciri; Kanban ve haritadan "
                      "görev atama, checklist tamamlanmadan görev kapanmaz.",
        "route": "/saha-operasyonlari",
    },
    {
        "id": "hasat",
        "title": "8. Hasat ve Kampanya Lojistiği",
        "narration": "Polar oranına göre söküm önceliklendirmesi + fabrika günlük "
                      "kapasitesine göre haftalara yayılan kantar takvimi.",
        "route": "/hasat-lojistigi",
    },
    {
        "id": "ufyd",
        "title": "9. UFYD — Hakediş ve Cari Hesap",
        "narration": "Destek/avans/kesinti/prim zinciri değişmez (immutable) bir "
                      "muhasebe defterinde birikir, hakediş buradan hesaplanır.",
        "route": "/ufyd-dashboard",
    },
    {
        "id": "karne",
        "title": "10. Çiftçi Karnesi",
        "narration": "Kota, verim, sulama ve finans göstergelerinin ağırlıklı "
                      "ortalamasıyla canlı hesaplanan bir performans skoru.",
        "route": "/karne/{farmer_id}",
        "requires": "farmer_id",
    },
]


async def _pick_showcase_farmer(db) -> dict:
    """En 'dolu' hikayeyi anlatan çiftçiyi bulur: aktif/hasatta bir üretim
    sezonu + gerçek bir parseli olan ilk kayıt. Bulunamazsa boş sözlük
    döner — adımlar bunu görüp `requires` alanlı adımları atlar."""
    cycle = await db.production_cycles.find_one(
        {"status": {"$in": ["active", "harvesting", "completed"]}, "farmer_id": {"$ne": None}, "parcel_id": {"$ne": None}},
        {"_id": 0}, sort=[("created_at", -1)],
    )
    if not cycle:
        return {}
    farmer = await db.farmers.find_one({"id": cycle["farmer_id"]}, {"_id": 0, "id": 1, "full_name": 1})
    parcel = await db.parcels.find_one({"id": cycle["parcel_id"]}, {"_id": 0, "id": 1, "name": 1})
    return {
        "farmer_id": farmer["id"] if farmer else None,
        "farmer_name": farmer.get("full_name") if farmer else None,
        "parcel_id": parcel["id"] if parcel else None,
        "parcel_name": parcel.get("name") if parcel else None,
    }


def register_demo_scenario_routes(api_router, db, current_user, require_feature=None):
    require_feature = require_feature or (lambda key: (lambda: True))

    @api_router.get("/demo-scenario/steps")
    async def demo_scenario_steps(user=Depends(current_user), _feat=Depends(require_feature("demo_scenario"))):
        showcase = await _pick_showcase_farmer(db)
        steps = []
        for s in DEMO_STEPS:
            step = {**s}
            requires = step.pop("requires", None)
            if requires and not showcase.get(requires):
                step["available"] = False
                step["route"] = None
                step["narration"] += " (Bu turda örnek kayıt bulunamadığı için bu adım atlanabilir.)"
            else:
                step["available"] = True
                if requires:
                    step["route"] = step["route"].format(**showcase)
            steps.append(step)
        return {"steps": steps, "showcase": showcase}
