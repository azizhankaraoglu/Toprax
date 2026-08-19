"""
=====================================================================
TOPRAX — Veri Güven Rozeti (ölçülmüş / tahmin / eksik)
=====================================================================
Kod tabanının en eski ilkesi "veri yoksa sayı uydurma"dır (bkz. remote_
sensing'de mock üreticinin silinmesi). Bu modül o ilkeyi KULLANICIYA
GÖRÜNÜR hale getirir: her tavsiyenin yanında hangi girdilerin gerçekten
ölçüldüğü, hangilerinin tahmin/varsayım olduğu ve hangilerinin hiç
bulunmadığı gösterilir.

Kurumsal/kamu ihalelerinde "bu öneri neye dayanıyor" sorusunun denetlenebilir
cevabı budur; teknik olarak da bir tavsiyenin ne kadar ciddiye alınacağını
belirler.
"""
from typing import Any, Dict, List, Optional

#: Girdi durumları — sıralama önem sırasıdır.
OLCULDU = "olculdu"
TAHMIN = "tahmin"
EKSIK = "eksik"

STATUS_LABELS = {
    OLCULDU: "Ölçüldü",
    TAHMIN: "Tahmin/varsayım",
    EKSIK: "Eksik",
}

#: Girdi ağırlıkları — bir tavsiyenin güvenilirliğine katkısı. Toprak analizi
#: ve uydu ölçümü en ağır; iklim normali gibi arka plan verisi daha hafif.
INPUT_WEIGHTS = {
    "toprak_analizi": 25,
    "uydu_olcumu": 20,
    "hava_verisi": 15,
    "sulama_kaydi": 10,
    "ekim_kaydi": 10,
    "gunes_analizi": 8,
    "toprak_biyolojisi": 7,
    "gecmis_verim": 5,
}

INPUT_LABELS = {
    "toprak_analizi": "Toprak analizi",
    "uydu_olcumu": "Uydu ölçümü",
    "hava_verisi": "Hava verisi",
    "sulama_kaydi": "Sulama kayıtları",
    "ekim_kaydi": "Ekim kaydı",
    "gunes_analizi": "Güneş/gölge analizi",
    "toprak_biyolojisi": "Toprak biyolojisi",
    "gecmis_verim": "Geçmiş verim/polar",
}


def build_badge(states: Dict[str, str], varsayimlar: Optional[List[str]] = None) -> Dict[str, Any]:
    """Girdi durumlarından güven rozeti üretir.

    `states`: {"toprak_analizi": "olculdu", "uydu_olcumu": "eksik", ...}
    Bilinmeyen anahtarlar yok sayılır (modüller kendi girdi kümesini verir).
    """
    rows: List[Dict[str, Any]] = []
    total_w = got_w = 0.0
    for key, weight in INPUT_WEIGHTS.items():
        if key not in states:
            continue
        status = states[key]
        total_w += weight
        if status == OLCULDU:
            got_w += weight
        elif status == TAHMIN:
            got_w += weight * 0.5      # varsayım yarım sayılır
        rows.append({"girdi": key, "label": INPUT_LABELS[key],
                     "durum": status, "durum_label": STATUS_LABELS.get(status, status),
                     "agirlik": weight})

    score = round(got_w / total_w * 100, 1) if total_w else 0.0
    if score >= 80:
        seviye, aciklama = "yuksek", "Tavsiye büyük ölçüde ölçülmüş veriye dayanıyor."
    elif score >= 50:
        seviye, aciklama = "orta", "Bazı girdiler eksik veya varsayım — tavsiye yönlendiricidir."
    else:
        seviye, aciklama = "dusuk", "Ölçüm çoğunlukla eksik; tavsiye yalnızca ön fikir verir."

    eksikler = [r["label"] for r in rows if r["durum"] == EKSIK]
    return {
        "skor": score,
        "seviye": seviye,
        "aciklama": aciklama,
        "girdiler": sorted(rows, key=lambda r: r["agirlik"], reverse=True),
        "eksik_girdiler": eksikler,
        "varsayimlar": varsayimlar or [],
        "oneri": (f"Güveni artırmak için: {', '.join(eksikler[:3])} tamamlanmalı."
                  if eksikler else "Tüm temel girdiler mevcut."),
    }


def states_from_context(ctx: Dict[str, Any]) -> Dict[str, str]:
    """Sezon Karar Takvimi bağlamından (season_planner.build_context) girdi
    durumlarını çıkarır — her modül kendi sözlüğünü kurmak zorunda kalmasın."""
    weather = ctx.get("weather") or {}
    water = ctx.get("water") or {}
    solar = ctx.get("solar") or {}
    biology = ctx.get("biology") or {}
    return {
        "toprak_analizi": OLCULDU if ctx.get("soil") else EKSIK,
        "uydu_olcumu": OLCULDU if ctx.get("indices") else EKSIK,
        "hava_verisi": (OLCULDU if weather.get("available") and not weather.get("stale")
                        else TAHMIN if weather.get("available") else EKSIK),
        "sulama_kaydi": (EKSIK if any("sulama kaydı yok" in v.lower()
                                      for v in (water.get("varsayimlar") or []))
                         else OLCULDU if water.get("available") else EKSIK),
        "ekim_kaydi": OLCULDU if ctx.get("planting") else EKSIK,
        "gunes_analizi": OLCULDU if solar.get("available") else EKSIK,
        "toprak_biyolojisi": OLCULDU if biology.get("toprak_sagligi_skoru") is not None else EKSIK,
        "gecmis_verim": OLCULDU if ctx.get("harvest") else EKSIK,
    }
