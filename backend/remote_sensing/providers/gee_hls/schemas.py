"""GEE/HLS — Pydantic modelleri. Bu modül SADECE veri şekli içerir, iş
mantığı YOK (dto.py ile aynı disiplin)."""
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class AnalyzeFieldRequest(BaseModel):
    # Kullanıcının literal spesifikasyonu: "polygon: Tarla sınırlarını
    # içeren GeoJSON formatında Polygon (veya koordinat dizisi)." — her iki
    # şekli de kabul edilir (bkz. service.py _extract_ring): ya doğrudan
    # [[lon,lat],...] koordinat dizisi, ya da {"type":"Polygon","coordinates":[[...]]}.
    polygon: Any
    start_date: str
    end_date: str


class AnalyzeFieldMeta(BaseModel):
    requested_area_ha: float
    buffer_applied: str = "30 meters"


class NdviPoint(BaseModel):
    date: str
    ndvi: float


class AnalyzeFieldResponse(BaseModel):
    status: str = "success"
    meta: AnalyzeFieldMeta
    latest_image_url: str
    ndvi_history: List[NdviPoint] = Field(default_factory=list)
