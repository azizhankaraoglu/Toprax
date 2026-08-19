"""GEE/HLS — Pydantic modelleri. Bu modül SADECE veri şekli içerir, iş
mantığı YOK (dto.py ile aynı disiplin)."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnalyzeFieldRequest(BaseModel):
    # Kullanıcının literal spesifikasyonu: "polygon: Tarla sınırlarını
    # içeren GeoJSON formatında Polygon (veya koordinat dizisi)." — her iki
    # şekli de kabul edilir (bkz. service.py _extract_ring): ya doğrudan
    # [[lon,lat],...] koordinat dizisi, ya da {"type":"Polygon","coordinates":[[...]]}.
    polygon: Any
    start_date: str
    end_date: str
    # 2026-08-18 (çok-indeksli genişletme): verilmezse TÜM katalog (10
    # indeks) hesaplanır. Alan OPSİYONELDİR — Faz 9C'nin literal istek
    # şemasını gönderen eski çağıranlar HİÇ DEĞİŞMEDEN çalışmaya devam
    # eder, sadece yanıtları zenginleşir.
    indices: Optional[List[str]] = None


class ThumbnailRequest(BaseModel):
    """Sayısal seri OLMADAN sadece güncel görüntü isteyen çağıranlar için
    (harita popup'ı / parsel kartı önizlemesi)."""
    polygon: Any
    days: int = 90


class AnalyzeFieldMeta(BaseModel):
    requested_area_ha: float
    buffer_applied: str = "30 meters"
    # Hangi indekslerin istendiği + ölçümlerin GERÇEKTEN hangi uydulardan
    # geldiği (sabit "NASA HLS" etiketi yerine ölçülmüş sensörler).
    indices: List[str] = Field(default_factory=list)
    sensors: List[str] = Field(default_factory=list)
    mock: bool = False


class IndexPoint(BaseModel):
    """Tek bir sahnenin parsel ortalamaları.

    İndeks alanları `Optional` — Landsat (L30) sahnelerinde kırmızı kenar
    bandı OLMADIĞI için NDRE/RECI/CCCI `null` döner. Bu bir eksiklik
    değil, dürüstlüktür: sıfır yazmak "ölçüldü ve sıfır çıktı" demek olurdu.
    """
    date: str
    sensor: Optional[str] = None
    ndvi: Optional[float] = None
    ndre: Optional[float] = None
    reci: Optional[float] = None
    ccci: Optional[float] = None
    ndwi: Optional[float] = None
    msi: Optional[float] = None
    msavi: Optional[float] = None
    savi: Optional[float] = None
    evi: Optional[float] = None
    lai: Optional[float] = None


class AnalyzeFieldResponse(BaseModel):
    status: str = "success"
    meta: AnalyzeFieldMeta
    latest_image_url: Optional[str] = None
    # `ndvi_history` adı LİTERAL sözleşme gereği KORUNUR (Faz 9C şeması);
    # `indices_history` aynı listenin okunabilir adıdır.
    ndvi_history: List[IndexPoint] = Field(default_factory=list)
    indices_history: List[IndexPoint] = Field(default_factory=list)
