"""
TOPRAX Remote Sensing (Uzaktan Algılama) paketi — FAZ 9.5 / IT-28.1
nihai spesifikasyonu (REMOTE-SENSING-EOSDA-PROMPT.md).

Karar 1: `satellite_provider.py`'yi (IT-17) KIRMAZ — EOSDA onun yeni bir
alt sınıfı gibi eklenir. FAZ 18 AI Engine (IT-47-53) bu modülün ürettiği
görüntü/istatistik/gözlem verisini TÜKETİR, kendi veri kaynağını icat etmez.
"""
from .services import register_remote_sensing_routes
from .providers import get_remote_sensing_provider

__all__ = ["register_remote_sensing_routes", "get_remote_sensing_provider"]
