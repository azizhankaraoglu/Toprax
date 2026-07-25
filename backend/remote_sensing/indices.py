"""
=====================================================================
TOPRAX — Uzaktan Algılama İndeks Kataloğu (TEK KAYNAK)
=====================================================================
Denetim düzeltmesi (2026-07-25) — kullanıcı NDVI dışında 8 indeks daha
istedi (NDRE, RECI, CCCI, NDWI, MSI, MSAVI, SAVI, EVI, LAI). Bu modül,
`event_bus.EVENT_TYPES` / `PERMISSION_CATALOG` ile AYNI aile — TEK bir
yerde tanımlanan saf veri kataloğu, HTTP/DB bağımlılığı YOK. Provider'lar
(sentinel2.py evalscript üretimi, eosda.py bm_type listesi), base.py
(parse_statistics/detect_anomaly), tasks.py (istatistik depolama),
services.py (AI yorumu/kural metni) ve frontend (grafik etiket/renk/
gruplama — GET /remote-sensing/index-catalog üzerinden) HEPSİ buradan
beslenir; indeks adı/formülü/eşiği ikinci bir yerde TEKRARLANMAZ.

Formül kaynağı — Sentinel-2 L2A bantları (B02=Mavi, B04=Kırmızı,
B05=Red Edge 1, B08=NIR, B11=SWIR1), standart/yaygın literatür
tanımları:
  - NDVI  (B08-B04)/(B08+B04)                    — Rouse 1973
  - NDRE  (B08-B05)/(B08+B05)                     — Barnes 2000
  - RECI  (B08/B05)-1                             — Gitelson 2003 (klorofil)
  - CCCI  (NDRE/NDVI YAKLAŞIK oranı)               — Fitzgerald 2010, YAKLAŞIK
  - NDWI  (B08-B11)/(B08+B11)                     — Gao 1996 (BİTKİ su içeriği;
           McFeeters'ın AÇIK SU NDWI'siyle [B03/B08] KARIŞTIRILMAMALI)
  - MSI   B11/B08                                 — Rock 1986 (nem stresi, düşük=iyi)
  - MSAVI (2*B08+1-sqrt((2*B08+1)^2-8*(B08-B04)))/2 — Qi 1994
  - SAVI  ((B08-B04)/(B08+B04+0.5))*1.5           — Huete 1988 (L=0.5 sabit)
  - EVI   2.5*(B08-B04)/(B08+6*B04-7.5*B02+1)     — Huete 2002
  - LAI   NDVI'den AMPİRİK regresyon — GERÇEK ÖLÇÜM DEĞİL, bkz. estimate_lai()
"""
import math
from enum import Enum
from typing import Dict, List, Optional


class IndexCategory(str, Enum):
    BITKI_SAGLIGI = "bitki_sagligi"   # kanopi/klorofil ailesi
    SU_STRESI = "su_stresi"           # nem/su stresi ailesi
    YAPISAL = "yapisal"               # yapısal (LAI)


# code -> tanım. SIRA ÖNEMLİ DEĞİL (sentinel2.py evalscript'i kendi
# real_codes listesini ayrıca taşır) ama okunabilirlik için NDVI önce.
INDEX_CATALOG: Dict[str, dict] = {
    "ndvi": {
        "label_tr": "NDVI (Bitki Örtüsü İndeksi)", "category": IndexCategory.BITKI_SAGLIGI,
        "bands_required": ["B04", "B08"], "formula_js": "(B08-B04)/(B08+B04+0.0001)",
        "healthy_min": 0.65, "healthy_max": None, "higher_is_better": True, "is_estimated": False,
        "chart_default_visible": True,
        "description_tr": "Bitki yoğunluğu/sağlığı — 0'a yakın çıplak/stresli toprak, 1'e yakın gür bitki örtüsü.",
    },
    "ndre": {
        "label_tr": "NDRE (Red-Edge NDVI)", "category": IndexCategory.BITKI_SAGLIGI,
        "bands_required": ["B05", "B08"], "formula_js": "(B08-B05)/(B08+B05+0.0001)",
        "healthy_min": 0.30, "healthy_max": None, "higher_is_better": True, "is_estimated": False,
        "chart_default_visible": False,
        "description_tr": "Klorofil/azot durumuna NDVI'den daha hassas — geç sezon/örtü kapanmış bitkide ayırt edici.",
    },
    "reci": {
        "label_tr": "RECI (Kırmızı Kenar Klorofil İndeksi)", "category": IndexCategory.BITKI_SAGLIGI,
        "bands_required": ["B05", "B08"], "formula_js": "(B08/(B05+0.0001))-1",
        "healthy_min": 3.0, "healthy_max": None, "higher_is_better": True, "is_estimated": False,
        "chart_default_visible": False,
        "description_tr": "Yaprak klorofil içeriği tahmini — gübreleme/azot kararlarında kullanılır.",
    },
    "ccci": {
        "label_tr": "CCCI (Kanopi Klorofil İçerik İndeksi)", "category": IndexCategory.BITKI_SAGLIGI,
        "bands_required": ["B04", "B05", "B08"],
        "formula_js": "(((B08-B05)/(B08+B05+0.0001)))/(((B08-B04)/(B08+B04+0.0001))+0.0001)",
        "healthy_min": 0.5, "healthy_max": None, "higher_is_better": True, "is_estimated": False,
        "chart_default_visible": False,
        "description_tr": "NDRE/NDVI oranı (YAKLAŞIK formül) — azot stresini biyokütleden ayırt eder.",
    },
    "ndwi": {
        "label_tr": "NDWI (Bitki Su İçeriği)", "category": IndexCategory.SU_STRESI,
        "bands_required": ["B08", "B11"], "formula_js": "(B08-B11)/(B08+B11+0.0001)",
        "healthy_min": 0.05, "healthy_max": None, "higher_is_better": True, "is_estimated": False,
        "chart_default_visible": True,
        "description_tr": "Gao (1996) bitki su içeriği formülü (B08/B11) — açık su NDWI'sinden (McFeeters) FARKLI.",
    },
    "msi": {
        "label_tr": "MSI (Nem Stresi İndeksi)", "category": IndexCategory.SU_STRESI,
        "bands_required": ["B08", "B11"], "formula_js": "B11/(B08+0.0001)",
        "healthy_min": None, "healthy_max": 1.0, "higher_is_better": False, "is_estimated": False,
        "chart_default_visible": True,
        "description_tr": "Düşük=iyi nem, yüksek=stres (SWIR/NIR oranı).",
    },
    "msavi": {
        "label_tr": "MSAVI (Değiştirilmiş Toprak Ayarlı Bitki İndeksi)", "category": IndexCategory.BITKI_SAGLIGI,
        "bands_required": ["B04", "B08"],
        "formula_js": "(2*B08+1-Math.sqrt(Math.pow(2*B08+1,2)-8*(B08-B04)))/2",
        "healthy_min": 0.6, "healthy_max": None, "higher_is_better": True, "is_estimated": False,
        "chart_default_visible": False,
        "description_tr": "Seyrek örtüde toprak arka planı etkisini azaltan NDVI varyantı (erken sezon için daha güvenilir).",
    },
    "savi": {
        "label_tr": "SAVI (Toprak Ayarlı Bitki İndeksi)", "category": IndexCategory.BITKI_SAGLIGI,
        "bands_required": ["B04", "B08"], "formula_js": "((B08-B04)/(B08+B04+0.5))*1.5",
        "healthy_min": 0.5, "healthy_max": None, "higher_is_better": True, "is_estimated": False,
        "chart_default_visible": False,
        "description_tr": "L=0.5 sabit toprak-parlaklık düzeltmesiyle NDVI (Huete 1988).",
    },
    "evi": {
        "label_tr": "EVI (Gelişmiş Bitki İndeksi)", "category": IndexCategory.BITKI_SAGLIGI,
        "bands_required": ["B02", "B04", "B08"],
        "formula_js": "2.5*(B08-B04)/(B08+6*B04-7.5*B02+1+0.0001)",
        "healthy_min": 0.4, "healthy_max": None, "higher_is_better": True, "is_estimated": False,
        "chart_default_visible": False,
        "description_tr": "Atmosfer/toprak düzeltmeli, yüksek biyokütlede NDVI'nin doyum sorununu azaltır.",
    },
    "lai": {
        "label_tr": "LAI (Yaprak Alan İndeksi, tahmini)", "category": IndexCategory.YAPISAL,
        "bands_required": [], "formula_js": None,   # evalscript'te YOK — NDVI'den Python'da türetilir
        "healthy_min": 2.0, "healthy_max": None, "higher_is_better": True, "is_estimated": True,
        "chart_default_visible": False,
        "description_tr": "GERÇEK bir ölçüm DEĞİL — NDVI'den ampirik regresyonla tahmin edilir (bkz. estimate_lai). "
                           "UI'da HER ZAMAN '(tahmini)' etiketiyle gösterilmelidir.",
    },
}

ALL_INDEX_CODES: List[str] = list(INDEX_CATALOG.keys())
CANOPY_CODES: List[str] = [c for c, v in INDEX_CATALOG.items()
                           if v["category"] in (IndexCategory.BITKI_SAGLIGI, IndexCategory.YAPISAL)]
WATER_CODES: List[str] = [c for c, v in INDEX_CATALOG.items() if v["category"] == IndexCategory.SU_STRESI]

# real_codes: evalscript'e giren (LAI hariç) kodlar — sentinel2.py'nin
# _build_stats_evalscript'i bu sırayla kullanır.
EVALSCRIPT_CODES: List[str] = [c for c in ALL_INDEX_CODES if INDEX_CATALOG[c]["formula_js"]]


def estimate_lai(ndvi: Optional[float]) -> Optional[float]:
    """YAKLAŞIK NDVI→LAI ampirik regresyon (lab-grade biyofiziksel geri-çekim
    DEĞİL — gerçek LAI ölçümü saha aletiyle/hiperspektral biyofiziksel işlemci
    gerektirir). a=0.15, b=4.9 sabitleri YER TUTUCUDUR, kalibre edilmedi —
    sonuç UI'da her zaman '(tahmini)' etiketiyle sunulmalıdır."""
    if ndvi is None or ndvi <= 0:
        return 0.0
    return round(0.15 * math.exp(4.9 * min(max(ndvi, 0.0), 0.95)), 2)
