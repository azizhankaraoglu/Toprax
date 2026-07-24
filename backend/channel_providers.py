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
    """Simüle sağlayıcı döner — geriye dönük uyumluluk için korunur.
    Entegrasyon config'ine göre GERÇEK sağlayıcı seçimi için
    `get_channel_provider_for(db, channel)` (async) kullanın."""
    provider = _PROVIDERS.get(channel)
    if provider is None:
        raise ValueError(f"Bilinmeyen kanal: {channel}")
    return provider


# =====================================================================
# GERÇEK SAĞLAYICILAR (Denetim A14, 2026-07-24)
# =====================================================================
# Asıl HTTP/SMTP gönderim mantığı integrations.py'de zaten vardı
# (`_probe_sms_send` — mesaj parametreli, /test ucu için yazılmıştı) —
# SMS için o fonksiyon DOĞRUDAN yeniden kullanılır (DRY). E-posta
# probe'u konu/gövdeyi sabitlediği için burada parametreli bir SMTP
# gönderimi yazıldı (aynı host/port/tls/login konvansiyonlarıyla).
# WhatsApp/Push/Voice simüle kalır (plan gereği — Meta/Firebase/IVR
# entegrasyonu ayrı bir iş paketi).

class RealSmsProvider(ChannelProvider):
    """Netgsm / Twilio / custom webhook üzerinden GERÇEK SMS gönderimi.
    Sağlayıcı seçimi + kimlik bilgileri `integrations` koleksiyonundaki
    `sms` dokümanından gelir."""

    def __init__(self, provider_name: str, cfg: dict, timeout: int):
        self._provider_name = provider_name
        self._cfg = cfg
        self._timeout = timeout

    def send(self, recipient: Optional[str], content: str, subject: Optional[str] = None) -> Dict:
        if not recipient:
            return {"ok": False, "status": "basarisiz",
                    "detail": "SMS için alıcı numarası bulunamadı", "provider_ref": None}
        from integrations import _probe_sms_send  # döngüsel import yok (integrations bu modülü import etmez)
        ok, detail = _probe_sms_send(self._provider_name, self._cfg, recipient, content, self._timeout)
        return {"ok": ok, "status": "teslim_edildi" if ok else "basarisiz",
                "detail": detail,
                "provider_ref": f"{self._provider_name}-{uuid.uuid4().hex[:12]}" if ok else None}


class SmtpEmailProvider(ChannelProvider):
    """SMTP üzerinden GERÇEK e-posta gönderimi — host/port/use_tls/username/
    password/from_address `integrations` koleksiyonundaki `email`
    dokümanından gelir (integrations._probe_email_send ile AYNI bağlantı
    konvansiyonları; probe konu/gövdeyi sabitlediği için burada parametreli)."""

    def __init__(self, cfg: dict, timeout: int):
        self._cfg = cfg
        self._timeout = timeout

    def send(self, recipient: Optional[str], content: str, subject: Optional[str] = None) -> Dict:
        if not recipient:
            return {"ok": False, "status": "basarisiz",
                    "detail": "E-posta için alıcı adresi bulunamadı", "provider_ref": None}
        import smtplib
        import ssl
        from email.mime.text import MIMEText
        cfg = self._cfg
        try:
            msg = MIMEText(content or "", _charset="utf-8")
            msg["Subject"] = subject or "Toprax Bildirimi"
            msg["From"] = cfg.get("from_address") or cfg.get("username")
            msg["To"] = recipient

            host = cfg.get("host")
            port = int(cfg.get("port", 587))
            use_tls = cfg.get("use_tls", True)
            if use_tls:
                server = smtplib.SMTP(host, port, timeout=self._timeout)
                server.starttls(context=ssl.create_default_context())
            else:
                server = smtplib.SMTP_SSL(host, port, timeout=self._timeout,
                                          context=ssl.create_default_context())
            server.login(cfg.get("username"), cfg.get("password"))
            server.sendmail(msg["From"], [recipient], msg.as_string())
            server.quit()
            return {"ok": True, "status": "teslim_edildi",
                    "detail": f"E-posta {recipient} adresine gönderildi (SMTP)",
                    "provider_ref": f"smtp-{uuid.uuid4().hex[:12]}"}
        except Exception as e:  # noqa: BLE001 — sağlayıcı hatası gönderim kaydına yazılır, istek çökmez
            return {"ok": False, "status": "basarisiz",
                    "detail": f"SMTP hatası: {e}", "provider_ref": None}


async def get_channel_provider_for(db, channel: str) -> ChannelProvider:
    """Entegrasyon-farkındalıklı factory (Denetim A14): `integrations`
    koleksiyonunda o kanal için ETKİN + kimlik bilgisi DOLU bir kayıt
    varsa gerçek sağlayıcı, yoksa simüle döner — çağıran kod
    (`communications.send_via_channel`) sonucu aynı sözleşmeyle alır.
    db parametresi TenantScopedDB'dir; tenant bağlamındaki entegrasyon
    dokümanı okunur (her kurumun kendi SMS/SMTP hesabı olabilir)."""
    if channel not in _PROVIDERS:
        raise ValueError(f"Bilinmeyen kanal: {channel}")
    if channel not in ("sms", "email"):
        return _PROVIDERS[channel]

    try:
        doc = await db.integrations.find_one({"type": channel}, {"_id": 0})
    except Exception:
        doc = None
    if not doc or not doc.get("enabled"):
        return _PROVIDERS[channel]

    from integrations import _has_credentials  # tek gerçek kaynak (DRY)
    from config_service import INTEGRATION_TIMEOUT_SECONDS
    cfg = doc.get("config") or {}
    provider_name = doc.get("provider")
    if not _has_credentials(channel, cfg, provider_name):
        return _PROVIDERS[channel]
    timeout = doc.get("timeout_seconds") or INTEGRATION_TIMEOUT_SECONDS

    if channel == "sms":
        return RealSmsProvider(provider_name or "netgsm", cfg, timeout)
    return SmtpEmailProvider(cfg, timeout)
