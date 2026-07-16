"""
TOPRAX — Gelecek Uzaktan Algılama sağlayıcıları için İSKELET (prompt:
"iskelet/placeholder yeterli"). Planet/Airbus/UP42 gerçek hesapları
açıldığında bu sınıflar EOSDAProvider deseniyle doldurulur — factory ve
çağıran kod DEĞİŞMEZ (Provider Pattern).
"""
from typing import Dict, List, Optional

from .base import IRemoteSensingProvider
from ..dto import TaskStatus, TaskState


class _NotImplementedProvider(IRemoteSensingProvider):
    capabilities: List[str] = []

    def _todo(self, *_a, **_k):
        raise NotImplementedError(
            f"'{self.name}' sağlayıcısı henüz implemente edilmedi (iskelet). "
            "Gerçek hesap aktive edildiğinde EOSDAProvider deseniyle doldurulacak.")

    def create_field(self, geometry: dict) -> str: self._todo()
    def search_scenes(self, field_id, date_range): self._todo()
    def request_image_download(self, view_id, fmt="png"): self._todo()
    def request_statistics(self, field_id, indices, date_range): self._todo()
    def get_task_status(self, task_id) -> TaskStatus:
        return TaskStatus(task_id=task_id, state=TaskState.FAILED, error="not_implemented")


class PlanetProvider(_NotImplementedProvider):
    name = "planet"


class AirbusProvider(_NotImplementedProvider):
    name = "airbus"


class UP42RSProvider(_NotImplementedProvider):
    name = "up42"
