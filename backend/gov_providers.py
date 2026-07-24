"""
=====================================================================
Toprax — Resmi Sistem Entegrasyonları: MERNİS + TAKBİS (Denetim Faz 3)
=====================================================================
`satellite_provider.py`/`channel_providers.py` ile AYNI ABC+factory kalıbı:
gerçek KPS (Kimlik Paylaşımı Sistemi) / TAKBİS erişimi kurumsal sözleşme
gerektirir (bu iki resmi servis genel API-key ile açılmaz) — bu yüzden
DEMO sağlayıcı deterministik/gerçek-algoritmalı sahte veri üretir, GERÇEK
sağlayıcı ise config'te kimlik bilgisi (kullanıcı adı/şifre/servis URL'i)
girilip `mock_mode` kapatılınca devreye girer (`integrations.py`'nin
MOCK_CAPABLE_TYPES deseni — eosda/sentinel_hub ile BİREBİR aynı).

İki ayrı yetenek:
  - IdentityProvider  : TC kimlik doğrulama (MERNİS/KPS)
  - CadastreProvider  : il/ilçe/ada/parsel → tapu bilgisi sorgusu (TAKBİS)

Gerçek sağlayıcılar SOAP tabanlıdır (KPS `TCKimlikNoDogrula`, TAKBİS'in
kurumsal servisleri) — `zeep` gibi ağır bir SOAP kütüphanesi EKLENMEDİ
(Karar Protokolü: yeni bağımlılık kullanıcı onayı ister, bu iterasyon
`requests` + elle XML zarfı ile SOAP 1.1 isteği kurar, aynı `geo_import.py`
felsefesiyle "sadece ihtiyaç kadar bağımlılık").
"""
import re
import zlib
import requests
from abc import ABC, abstractmethod
from typing import Dict
from xml.etree import ElementTree as ET


# =====================================================================
#                       TC KİMLİK NO CHECKSUM
# =====================================================================

def validate_tc_checksum(tc_no: str) -> bool:
    """Gerçek TC Kimlik No algoritması (11 haneli, resmi formül) — demo
    sağlayıcı bunu kullanarak "gerçekçi ama gerçek KPS'e gitmeyen" bir
    doğrulama yapar; gerçek sağlayıcıda da ilk-aşama biçim kontrolü olarak
    kullanılır (KPS'e anlamsız bir istek göndermemek için)."""
    if not tc_no or not re.fullmatch(r"\d{11}", tc_no):
        return False
    digits = [int(c) for c in tc_no]
    if digits[0] == 0:
        return False
    odd_sum = sum(digits[0:9:2])   # 1,3,5,7,9. haneler (0-index: 0,2,4,6,8)
    even_sum = sum(digits[1:8:2])  # 2,4,6,8. haneler (0-index: 1,3,5,7)
    d10 = ((odd_sum * 7) - even_sum) % 10
    d11 = (sum(digits[0:10])) % 10
    return d10 == digits[9] and d11 == digits[10]


# =====================================================================
#                       IDENTITY (MERNİS/KPS) PROVIDER
# =====================================================================

class IdentityProvider(ABC):
    @abstractmethod
    def verify(self, tc_no: str, ad: str, soyad: str, dogum_yili: int) -> Dict:
        """{"verified": bool, "detail": str} döner."""
        raise NotImplementedError


class DemoMernisProvider(IdentityProvider):
    """Gerçek KPS'e gitmez — TC checksum'ı GERÇEK algoritmayla doğrular
    (rastgele bir TC no'nun checksum'ı geçme ihtimali ~%1, bu yüzden
    'demo' olsa da tamamen anlamsız değildir); ad/soyad/doğum yılı
    eşleşmesi CRC32-tohumlu deterministik bir "veritabanı" simülasyonuyla
    kontrol edilir (aynı girdi HER ZAMAN aynı sonucu üretir — DemoSatelliteProvider
    ile AYNI teknik: satellite_provider.py)."""

    def verify(self, tc_no: str, ad: str, soyad: str, dogum_yili: int) -> Dict:
        if not validate_tc_checksum(tc_no):
            return {"verified": False, "detail": "TC Kimlik No formatı/checksum geçersiz (demo mod)."}
        seed = zlib.crc32(f"{tc_no}|{ad.strip().lower()}|{soyad.strip().lower()}|{dogum_yili}".encode("utf-8"))
        # Deterministik: aynı 4 alan HER ZAMAN aynı sonucu üretir. Alanlardan
        # biri (ör. yanlış soyad) değişirse checksum aynı olsa bile seed
        # değişir ve doğrulama muhtemelen başarısız olur — gerçek bir eşleşme
        # kontrolü İZLENİMİ verir (rastgele DEĞİL, girdiye bağlı).
        ok = (seed % 100) < 92  # %92 "eşleşti" — demo ortamında makul bir başarı oranı
        detail = ("Kimlik bilgileri MERNİS demo veri tabanıyla eşleşti."
                  if ok else "Kimlik bilgileri eşleşmedi (ad/soyad/doğum yılını kontrol edin) — demo mod.")
        return {"verified": ok, "detail": detail}


class RealMernisProvider(IdentityProvider):
    """KPS (Kimlik Paylaşımı Sistemi) `TCKimlikNoDogrula` SOAP 1.1 servisi.
    Kurumsal VPN/sözleşme gerektirir — `service_url`/`username`/`password`
    God Mode > Ayarlar > Entegrasyonlar'dan girilir."""

    def __init__(self, service_url: str, username: str, password: str, timeout: int = 10):
        self._url = service_url
        self._username = username
        self._password = password
        self._timeout = timeout

    def verify(self, tc_no: str, ad: str, soyad: str, dogum_yili: int) -> Dict:
        if not validate_tc_checksum(tc_no):
            return {"verified": False, "detail": "TC Kimlik No formatı/checksum geçersiz."}
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <TCKimlikNoDogrula xmlns="http://tckimlik.nvi.gov.tr/WS">
      <TCKimlikNo>{tc_no}</TCKimlikNo>
      <Ad>{ad}</Ad>
      <Soyad>{soyad}</Soyad>
      <DogumYili>{dogum_yili}</DogumYili>
    </TCKimlikNoDogrula>
  </soap:Body>
</soap:Envelope>"""
        try:
            resp = requests.post(
                self._url,
                data=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "http://tckimlik.nvi.gov.tr/WS/TCKimlikNoDogrula",
                },
                auth=(self._username, self._password),
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                return {"verified": False, "detail": f"MERNİS servis hatası: HTTP {resp.status_code}"}
            root = ET.fromstring(resp.content)
            result_text = None
            for el in root.iter():
                if el.tag.endswith("TCKimlikNoDogrulaResult"):
                    result_text = (el.text or "").strip().lower()
                    break
            ok = result_text == "true"
            return {"verified": ok, "detail": "MERNİS doğrulaması tamamlandı." if ok else "MERNİS: kimlik bilgileri eşleşmedi."}
        except Exception as e:  # noqa: BLE001
            return {"verified": False, "detail": f"MERNİS bağlantı hatası: {e}"}


# =====================================================================
#                       CADASTRE (TAKBİS) PROVIDER
# =====================================================================

class CadastreProvider(ABC):
    @abstractmethod
    def query(self, il: str, ilce: str, ada: str, parsel: str) -> Dict:
        """{"found": bool, "malik": str, "alan_m2": float, "nitelik": str,
        "tapu_tarihi": str, "detail": str} döner."""
        raise NotImplementedError


_DEMO_MALIKLER = ["Ahmet Yılmaz", "Mehmet Demir", "Ayşe Kaya", "Fatma Şahin", "Ali Çelik", "Hatice Arslan"]
_DEMO_NITELIKLER = ["Tarla", "Bahçe", "Sulu Tarla", "Kuru Tarla", "Mera"]


class DemoTakbisProvider(CadastreProvider):
    """Gerçek TAKBİS'e gitmez — il/ilçe/ada/parsel dörtlüsünden CRC32-tohumlu
    deterministik bir tapu kaydı üretir (satellite_provider.DemoSatelliteProvider
    ile AYNI teknik)."""

    def query(self, il: str, ilce: str, ada: str, parsel: str) -> Dict:
        if not (il and ilce and ada and parsel):
            return {"found": False, "detail": "İl/ilçe/ada/parsel bilgilerinin tümü gerekli."}
        seed = zlib.crc32(f"{il.strip().lower()}|{ilce.strip().lower()}|{ada}|{parsel}".encode("utf-8"))
        malik = _DEMO_MALIKLER[seed % len(_DEMO_MALIKLER)]
        nitelik = _DEMO_NITELIKLER[(seed >> 4) % len(_DEMO_NITELIKLER)]
        alan_m2 = 1500 + (seed % 85000)  # 1.500 - 86.500 m² arası deterministik
        yil = 1998 + (seed % 27)
        return {
            "found": True,
            "malik": malik,
            "alan_m2": float(alan_m2),
            "nitelik": nitelik,
            "tapu_tarihi": f"{yil}-{(seed % 12) + 1:02d}-{(seed % 28) + 1:02d}",
            "detail": "[DEMO MOD] TAKBİS demo veri tabanından üretildi — gerçek tapu kaydı değildir.",
        }


class RealTakbisProvider(CadastreProvider):
    """Kurumsal TAKBİS Parsel Sorgu servisi — `service_url`/`username`/
    `password` üzerinden SOAP/REST (kurumun sağladığı sözleşmeye göre
    değişir; burada genel bir requests+XML zarfı kurulur, gerçek kurumun
    WSDL'i ile birebir alan eşlemesi kurulum sırasında ayarlanır)."""

    def __init__(self, service_url: str, username: str, password: str, timeout: int = 10):
        self._url = service_url
        self._username = username
        self._password = password
        self._timeout = timeout

    def query(self, il: str, ilce: str, ada: str, parsel: str) -> Dict:
        if not (il and ilce and ada and parsel):
            return {"found": False, "detail": "İl/ilçe/ada/parsel bilgilerinin tümü gerekli."}
        try:
            resp = requests.get(
                self._url,
                params={"il": il, "ilce": ilce, "ada": ada, "parsel": parsel},
                auth=(self._username, self._password),
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                return {"found": False, "detail": f"TAKBİS servis hatası: HTTP {resp.status_code}"}
            data = resp.json()
            return {
                "found": bool(data.get("malik")),
                "malik": data.get("malik"),
                "alan_m2": data.get("alan_m2"),
                "nitelik": data.get("nitelik"),
                "tapu_tarihi": data.get("tapu_tarihi"),
                "detail": "TAKBİS sorgusu tamamlandı.",
            }
        except Exception as e:  # noqa: BLE001
            return {"found": False, "detail": f"TAKBİS bağlantı hatası: {e}"}


# =====================================================================
#                       FACTORY (integrations.py config'inden)
# =====================================================================

async def get_identity_provider(db) -> IdentityProvider:
    """`integrations` koleksiyonundaki `mernis` dokümanına göre demo/gerçek
    sağlayıcı seçer — `satellite_provider.get_satellite_provider()` ile
    AYNI ileri-uyum notu: yeni bir sağlayıcı eklenirse SADECE burası değişir."""
    doc = await db.integrations.find_one({"type": "mernis"}, {"_id": 0})
    cfg = (doc or {}).get("config", {}) or {}
    enabled = bool(doc and doc.get("enabled"))
    has_creds = bool(cfg.get("username") and cfg.get("password") and cfg.get("service_url"))
    mock_mode = cfg.get("mock_mode", True)
    if enabled and has_creds and not mock_mode:
        from config_service import INTEGRATION_TIMEOUT_SECONDS
        timeout = doc.get("timeout_seconds") or INTEGRATION_TIMEOUT_SECONDS
        return RealMernisProvider(cfg["service_url"], cfg["username"], cfg["password"], timeout)
    return DemoMernisProvider()


async def get_cadastre_provider(db) -> CadastreProvider:
    doc = await db.integrations.find_one({"type": "takbis"}, {"_id": 0})
    cfg = (doc or {}).get("config", {}) or {}
    enabled = bool(doc and doc.get("enabled"))
    has_creds = bool(cfg.get("username") and cfg.get("password") and cfg.get("service_url"))
    mock_mode = cfg.get("mock_mode", True)
    if enabled and has_creds and not mock_mode:
        from config_service import INTEGRATION_TIMEOUT_SECONDS
        timeout = doc.get("timeout_seconds") or INTEGRATION_TIMEOUT_SECONDS
        return RealTakbisProvider(cfg["service_url"], cfg["username"], cfg["password"], timeout)
    return DemoTakbisProvider()
