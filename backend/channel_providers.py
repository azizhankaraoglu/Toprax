"""
=====================================================================
Toprax — Kanal Provider Soyutlaması (IT-25 / FAZ 9 Communication Hub)
=====================================================================
`satellite_provider.py`'deki ABC + factory kalıbının AYNISI: gerçek bir
SMS/E-posta/WhatsApp/Push/Sesli Arama sağlayıcısı (Netgsm/Twilio/SMTP/
Meta Cloud API/Firebase/bir IVR servisi) entegrasyonu ileride Integration
Hub kapsamında yapılacak. O gün geldiğinde SADECE yeni bir
`ChannelProvider` alt sınıfı eklenip `get_channel_provider()` içinde
seçilmesini sağlayacak şekilde bir arayüz kurulur — çağıran kod
(`communications.py`) DEĞİŞMEZ.

İlk fazda (ROADMAP IT-25 kararı) TÜM kanallar simüle: gerçek SMS/e-posta/
WhatsApp/push/arama YAPILMAZ, sadece "gönderilmiş/teslim edilmiş gibi"
deterministik bir sonuç üretilir. `integrations.py`'deki gerçek SMS/Email
prob'larıyla (Netgsm/Twilio/SMTP) KARIŞTIRILMAMALI — onlar gerçek dış
entegrasyon ayarları, bunlar Comm Hub'ın kendi kanal soyutlamasıdır.
"""
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Optional

CHANNELS = {
    "sms": "SMS",
    "email": "E-Posta",
    "whatsapp": "WhatsApp",
    "push": "Mobil Bildirim (Push)",
    "voice": "Sesli Arama (IVR)",
}


class ChannelProvider(ABC):
    @abstractmethod
    def send(self, recipient: Optional[str], content: str, subject: Optional[str] = None) -> Dict:
        """{"ok": bool, "status": "teslim_edildi"|"basarisiz", "detail": str, "provider_ref": str|None} döner."""
        raise NotImplementedError


class _SimulatedProvider(ChannelProvider):
    """Tüm kanallar için ORTAK simülasyon davranışı: alıcı adresi/numarası
    boşsa başarısız, doluysa her zaman başarılı ("teslim_edildi") döner —
    gerçek bir ağ çağrısı YOK, dev/demo ortamında deterministik davranış."""
    channel_label = "Kanal"

    def send(self, recipient: Optional[str], content: str, subject: Optional[str] = None) -> Dict:
        if not recipient:
            return {
                "ok": False, "status": "basarisiz",
                "detail": f"{self.channel_label} için alıcı adresi/numarası bulunamadı",
                "provider_ref": None,
            }
        return {
            "ok": True, "status": "teslim_edildi",
            "detail": f"[SIMÜLE] {self.channel_label} → {recipient} adresine iletildi",
            "provider_ref": f"sim-{uuid.uuid4().hex[:12]}",
        }


class SimulatedSmsProvider(_SimulatedProvider):
    channel_label = "SMS"


class SimulatedEmailProvider(_SimulatedProvider):
    channel_label = "E-Posta"


class SimulatedWhatsappProvider(_SimulatedProvider):
    channel_label = "WhatsApp"


class SimulatedPushProvider(_SimulatedProvider):
    channel_label = "Mobil Bildirim"


class SimulatedVoiceProvider(_SimulatedProvider):
    channel_label = "Sesli Arama"


_PROVIDERS: Dict[str, ChannelProvider] = {
    "sms": SimulatedSmsProvider(),
    "email": SimulatedEmailProvider(),
    "whatsapp": SimulatedWhatsappProvider(),
    "push": SimulatedPushProvider(),
    "voice": SimulatedVoiceProvider(),
}


def get_channel_provider(channel: str) -> ChannelProvider:
    """Şimdilik her zaman simüle sağlayıcı döner — gerçek sağlayıcı(lar)
    eklendiğinde burada Integration Center config'ine göre seçim yapılacak
    (`satellite_provider.get_satellite_provider()` ile AYNI ileri-uyum notu)."""
    provider = _PROVIDERS.get(channel)
    if provider is None:
        raise ValueError(f"Bilinmeyen kanal: {channel}")
    return provider
