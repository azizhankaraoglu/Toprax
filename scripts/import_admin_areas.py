#!/usr/bin/env python3
"""
=====================================================================
TOPRAX — İl / İlçe / Mahalle toplu içe aktarma (TEK SEFERLİK)
=====================================================================
Kullanım (konteyner içinde):
    python scripts/import_admin_areas.py <dosya.geojson> --type il
    python scripts/import_admin_areas.py <dosya.geojson> --type ilce
    python scripts/import_admin_areas.py <dosya.geojson> --type mahalle

NEDEN AYRI BİR SCRIPT (UI'daki toplu yükleme dururken):
  Mahalle dosyası ~133 MB ve 60binden fazla kayıt taşıyor. Aradaki katmanların
  hepsinin sınırı var: nginx `client_max_body_size 80M`, `geo_import.py`
  `MAX_UPLOAD_BYTES 70 MB`, ayrıca tek istekte 60bin feature ayrıştırmak
  bellek/zaman aşımı riski. Kullanıcı kararı: "bu tek seferlik bir işlem, bir
  kez yükledikten sonra sadece güncelleme/silme/ekleme yapılacak" — dolayısıyla
  doğru yer HTTP değil, doğrudan veritabanına yazan bu script.

HİYERARŞİ KODLARLA KURULUR (kullanıcının açık talebi):
  il_plaka → ilce_kodu → mahalle_kodu. İsim eşleştirmesi YAPILMAZ; aynı adlı
  ilçeler (ör. "Merkez") ve mahalleler farklı illerde defalarca geçer, isimle
  bağlamak sessizce yanlış ağaç üretirdi.

İDEMPOTENT: aynı dosya iki kez çalıştırılırsa kayıt İKİYE KATLANMAZ — anahtar
(area_type + kod üçlüsü) üzerinden upsert edilir. Bu, `admin_areas.py`'deki
HTTP toplu yükleme ucundan bilinçli bir FARKTIR (o uç idempotent değildir).

Türkçe karakter onarımı: kaynak dosyada bazı adlar çift kodlanmış
("AÄŸri" → "Ağrı", "NevÅŸehir" → "Nevşehir"). Bozulma tespit edilen metin
alanları latin1→utf8 ile geri çevrilir (bkz. _fix_mojibake).
"""
import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
sys.path.insert(0, "/app")

from motor.motor_asyncio import AsyncIOMotorClient          # noqa: E402
from pymongo import UpdateOne                                # noqa: E402
from pymongo.errors import BulkWriteError                    # noqa: E402

from config_service import MONGO_URL, DB_NAME                # noqa: E402
from admin_areas import _clean_geometry, DEMOGRAPHIC_FIELDS  # noqa: E402

CHUNK = 2000            # admin_areas.bulk_import ile AYNI parça boyutu
AREA_TYPES = ("il", "ilce", "mahalle")

#: Bu metin, kaynak dosyadaki çift kodlamanın imzası. "Ã", "Å", "Ä" gibi
#: karakterler Türkçe metinde doğal olarak GEÇMEZ; görüldüklerinde metin
#: utf-8 baytlarının latin1 sanılarak okunmuş halidir.
_MOJIBAKE_MARKERS = ("Ã", "Å", "Ä", "Â", "Ð", "Þ", "ð", "þ")

#: Bozuk bir dizinin DEVAM karakterleri — utf-8 baytlarının cp1252 karşılıkları.
#: Onarım bu kümedeki ardışık karakterleri tek bir "bozuk parça" sayar.
_MOJIBAKE_CONT = set(
    "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ "
    "¡¢£¤¥¦§¨©ª«¬­®¯°±²³´µ¶·¸¹º»¼½¾¿"
    "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞß"
    "àáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ"
)


#: KURTARILAMAYAN bozulmalar — kaynak dosyada "Ş"nin ikinci baytı (0x9E)
#: tamamen kayıp olduğu için kod çözümüyle geri getirilemez; bilgi dosyada
#: YOK. Bilinen iki il adı ve türevleri açıkça eşlenir. (Onarım, alt dizgi
#: olarak da uygulanır: "Åanliurfa" hem `il_adi`nde hem `display_name`
#: içinde geçiyor.)
_UNRECOVERABLE = {
    "Åirnak": "Şırnak",
    "Åanliurfa": "Şanlıurfa",
    "Åanlÿurfa": "Şanlıurfa",
}


def _apply_known_fixes(text: str) -> str:
    for bad, good in _UNRECOVERABLE.items():
        if bad in text:
            text = text.replace(bad, good)
    return text


def _repair_runs(text: str) -> str:
    """Karışık metinde SADECE bozuk parçaları onarır, sağlam parçalara dokunmaz."""
    out: List[str] = []
    i = 0
    while i < len(text):
        if text[i] in _MOJIBAKE_MARKERS:
            j = i
            while j < len(text) and text[j] in _MOJIBAKE_CONT:
                j += 1
            run = text[i:j]
            fixed = run
            for enc in ("cp1252", "latin1"):
                try:
                    candidate = run.encode(enc).decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
                if not any(m in candidate for m in _MOJIBAKE_MARKERS):
                    fixed = candidate
                    break
            out.append(fixed)
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _fix_mojibake(value: Any) -> Any:
    """Çift kodlanmış metni onarır; onaramıyorsa DEĞİŞTİRMEDEN döner.

    Sessizce bozmamak için iki güvence var: (1) yalnızca yukarıdaki imza
    karakterlerini içeren metinlere dokunulur, (2) dönüşüm başarısız olursa
    (UnicodeError) orijinal değer korunur.

    ⚠️ ÖNCE cp1252, SONRA latin1 denenir — sıra ÖNEMLİ. Kaynak dosyadaki
    bozulma Windows-1252 kaynaklı: "Ağrı" → "AÄŸri" dizisindeki "Ÿ" (U+0178)
    latin1'de YOKTUR (latin1 yalnızca U+00FF'e kadar), dolayısıyla latin1 ile
    onarım denemesi `UnicodeEncodeError` verip metni OLDUĞU GİBİ bırakıyordu.
    Canlıda görülen sonuç: adı Türkçe harf içeren 18 il onarılamadı, plakaları
    çözülemedi ve 81 il veritabanında 64 kayda düştü.
    """
    if not isinstance(value, str) or not any(m in value for m in _MOJIBAKE_MARKERS):
        return value
    # Bayt kaybı yaşamış bilinen adlar önce elle düzeltilir (kod çözümü bunları
    # kurtaramaz — bkz. _UNRECOVERABLE).
    value = _apply_known_fixes(value)
    if not any(m in value for m in _MOJIBAKE_MARKERS):
        return value
    # Önce metnin TAMAMINI onarmayı dene (saf bozuk metinler için en temizi).
    for enc in ("cp1252", "latin1"):
        try:
            repaired = value.encode(enc).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if not any(m in repaired for m in _MOJIBAKE_MARKERS):
            return repaired
    # KARIŞIK metin: kaynak dosyada aynı dize hem düzgün hem bozuk parça
    # taşıyabiliyor — canlıda görüldü: "Marmaraereğlisi, TekirdaÄŸ" ("ğ" doğru,
    # "ğ" bozuk). Böyle bir dizeyi bütün olarak cp1252'ye kodlamak imkânsız
    # ("ğ" cp1252'de YOK), bu yüzden tüm onarım başarısız olup metin bozuk
    # kalıyordu. Çözüm: yalnızca BOZUK parçaları (mojibake alfabesindeki
    # ardışık karakter dizilerini) tek tek onarmak.
    return _repair_runs(value)


# =====================================================================
# PLAKA ONARIMI — kaynak dosyanın en kritik veri kalitesi sorunu
# =====================================================================
# Kaynak dosyalarda 22 ilin `il_plaka` değeri 0: tam olarak adında Türkçe'ye
# özgü harf bulunan iller (Ağrı, Düzce, Eskişehir, Elazığ, Çanakkale, Çankırı,
# …). Üretici script, adı bozuk kodlanmış (mojibake) illerin plakasını
# çözememiş ve 0 yazmış.
#
# Bu, sadece "eksik bir kolon" değil — hiyerarşi il_plaka üzerinden kurulduğu
# için: (1) 81 il birbirinin üzerine yazılıp 60'a düşüyor, (2) o illerin
# ilçe/mahalleleri yanlış ile bağlanıyor. Bu yüzden içe aktarımın ilk adımı
# adı onarmak (mojibake) ve plakayı RESMİ tablodan yeniden türetmek.
TR_IL_PLAKA = {
    "adana": 1, "adiyaman": 2, "afyonkarahisar": 3, "agri": 4, "amasya": 5,
    "ankara": 6, "antalya": 7, "artvin": 8, "aydin": 9, "balikesir": 10,
    "bilecik": 11, "bingol": 12, "bitlis": 13, "bolu": 14, "burdur": 15,
    "bursa": 16, "canakkale": 17, "cankiri": 18, "corum": 19, "denizli": 20,
    "diyarbakir": 21, "edirne": 22, "elazig": 23, "erzincan": 24, "erzurum": 25,
    "eskisehir": 26, "gaziantep": 27, "giresun": 28, "gumushane": 29, "hakkari": 30,
    "hatay": 31, "isparta": 32, "mersin": 33, "istanbul": 34, "izmir": 35,
    "kars": 36, "kastamonu": 37, "kayseri": 38, "kirklareli": 39, "kirsehir": 40,
    "kocaeli": 41, "konya": 42, "kutahya": 43, "malatya": 44, "manisa": 45,
    "kahramanmaras": 46, "mardin": 47, "mugla": 48, "mus": 49, "nevsehir": 50,
    "nigde": 51, "ordu": 52, "rize": 53, "sakarya": 54, "samsun": 55,
    "siirt": 56, "sinop": 57, "sivas": 58, "tekirdag": 59, "tokat": 60,
    "trabzon": 61, "tunceli": 62, "sanliurfa": 63, "usak": 64, "van": 65,
    "yozgat": 66, "zonguldak": 67, "aksaray": 68, "bayburt": 69, "karaman": 70,
    "kirikkale": 71, "batman": 72, "sirnak": 73, "bartin": 74, "ardahan": 75,
    "igdir": 76, "yalova": 77, "karabuk": 78, "kilis": 79, "osmaniye": 80,
    "duzce": 81,
    # Yaygın alternatif yazımlar (kaynak dosya bazılarını böyle veriyor).
    "afyon": 3, "icel": 33, "maras": 46, "urfa": 63, "antep": 27,
    # ONARILAMAYAN iki ad: kaynak dosyada "Ş" harfinin ikinci baytı (0x9E)
    # tamamen KAYIP — "Şırnak" → "Åirnak", "Şanlıurfa" → "Åanliurfa".
    # Kod çözümüyle geri getirilemez (bilgi dosyada yok), bu yüzden bozuk
    # yazımları doğrudan eşleştiriyoruz.
    "åirnak": 73, "åanliurfa": 63,
}

_TR_LOWER = str.maketrans("İIŞĞÜÖÇÂÎÛ", "iisguocaiu")


def _norm_il(name: str) -> str:
    """İl adını plaka tablosunda aranabilir hale getirir.

    Python'un `.lower()`'ı "İ"yi "i̇" (i + birleşik nokta) yapar; bu, alttaki
    sözlükte eşleşmeyi bozar — bu yüzden ÖNCE translate, SONRA lower
    (field_definitions.py'deki `_slugify_tr` düzeltmesiyle AYNI ders).
    """
    s = (name or "").translate(_TR_LOWER).lower()
    s = s.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
    s = s.replace("ü", "u").replace("ö", "o").replace("ç", "c")
    return "".join(ch for ch in s if ch.isalnum())


def _repair_plaka(mapped: Dict[str, Any]) -> Dict[str, Any]:
    """`il_plaka` eksik/0 ise il adından resmî plakayı türetir."""
    plaka = mapped.get("il_plaka")
    if plaka and plaka > 0:
        return mapped
    guess = TR_IL_PLAKA.get(_norm_il(mapped.get("il_adi") or ""))
    if guess:
        mapped["il_plaka"] = guess
    return mapped


def _iter_features(path: str) -> Iterable[Dict[str, Any]]:
    """GeoJSON'u AKIŞ HALİNDE okur — 133 MB'lık dosyayı tek seferde belleğe
    almadan feature feature üretir.

    Neden elle ayrıştırma: `ijson` bu projenin bağımlılıklarında YOK ve Karar
    Protokolü gereği yeni bağımlılık eklenmiyor. Kaynak dosyalar (QGIS/ogr2ogr
    çıktısı) her feature'ı KENDİ SATIRINA yazdığı için satır bazlı okuma
    yeterli ve güvenli; yine de satır bir feature'a ayrıştırılamazsa süslü
    parantez sayarak biriktiren bir yedek yol var.
    """
    buf = ""
    depth = 0
    in_features = False
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if not in_features:
                if '"features"' in line:
                    in_features = True
                    line = line.split('"features"', 1)[1]
                    line = line.split("[", 1)[1] if "[" in line else ""
                else:
                    continue
            for ch in line:
                if ch == "{":
                    depth += 1
                if depth > 0:
                    buf += ch
                if ch == "}":
                    depth -= 1
                    if depth == 0 and buf.strip():
                        try:
                            yield json.loads(buf)
                        except json.JSONDecodeError:
                            pass
                        buf = ""


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


#: Sayısal alanlar — kaynak dosyada bazıları metin olarak gelebiliyor.
_INT_FIELDS = {"il_plaka", "ilce_kodu", "mahalle_kodu", "nufus_toplam", "hane_sayisi",
               "kayitli_cks_ciftci_sayisi", "traktor_sayisi",
               "kucukbas_hayvan_sayisi", "buyukbas_hayvan_sayisi"}


def _map_properties(props: Dict[str, Any]) -> Dict[str, Any]:
    """Kaynak `properties` → AdminAreaDemographics alanları.

    Yalnızca modelde TANIMLI alanlar aktarılır (dosyaya sonradan eklenen
    bilinmeyen bir alan sessizce dokümana sızmasın — konvansiyon #8).
    """
    out: Dict[str, Any] = {}
    for key in DEMOGRAPHIC_FIELDS:
        if key not in props:
            continue
        val = props.get(key)
        if val is None or val == "":
            continue
        if key in _INT_FIELDS:
            out[key] = _to_int(val)
        elif isinstance(val, (int, float)):
            out[key] = _to_float(val)
        else:
            out[key] = _fix_mojibake(str(val).strip())
    # Ad onarımı ÖNCE, plaka türetimi SONRA — plaka, onarılmış addan aranır.
    return _repair_plaka(out)


def _display_name(area_type: str, mapped: Dict[str, Any]) -> str:
    """Kaydın `name` alanı — seviyeye göre kendi ad kolonundan."""
    if area_type == "il":
        return mapped.get("il_adi") or mapped.get("display_name") or "(adsız il)"
    if area_type == "ilce":
        return mapped.get("ilce_adi") or mapped.get("display_name") or "(adsız ilçe)"
    return mapped.get("mahalle_adi") or mapped.get("display_name") or "(adsız mahalle)"


def _identity_filter(area_type: str, mapped: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """İdempotentlik anahtarı — KODLARDAN kurulur (isimden DEĞİL)."""
    plaka = mapped.get("il_plaka")
    if area_type == "il":
        if plaka is None:
            return None
        return {"area_type": "il", "il_plaka": plaka}
    if area_type == "ilce":
        if plaka is None or mapped.get("ilce_kodu") is None:
            return None
        return {"area_type": "ilce", "il_plaka": plaka, "ilce_kodu": mapped["ilce_kodu"]}
    if plaka is None or mapped.get("mahalle_kodu") is None:
        return None
    return {"area_type": "mahalle", "il_plaka": plaka,
            "ilce_kodu": mapped.get("ilce_kodu"), "mahalle_kodu": mapped["mahalle_kodu"]}


async def _parent_index(db, area_type: str) -> Dict[Any, str]:
    """Üst seviyenin (kod → admin_areas.id) haritası.

    il → yok, ilce → il haritası, mahalle → (il_plaka, ilce_kodu) haritası.
    Bir kez kurulup bellekte tutulur (60bin mahalle için 60bin ayrı sorgu
    yerine tek tarama).
    """
    if area_type == "il":
        return {}
    if area_type == "ilce":
        idx = {}
        async for a in db.admin_areas.find({"area_type": "il"}, {"_id": 0, "id": 1, "il_plaka": 1}):
            if a.get("il_plaka") is not None:
                idx[a["il_plaka"]] = a["id"]
        return idx
    idx = {}
    async for a in db.admin_areas.find({"area_type": "ilce"},
                                       {"_id": 0, "id": 1, "il_plaka": 1, "ilce_kodu": 1}):
        if a.get("il_plaka") is not None and a.get("ilce_kodu") is not None:
            idx[(a["il_plaka"], a["ilce_kodu"])] = a["id"]
    return idx


def _parent_id_for(area_type: str, mapped: Dict[str, Any], parents: Dict[Any, str]) -> Optional[str]:
    if area_type == "ilce":
        return parents.get(mapped.get("il_plaka"))
    if area_type == "mahalle":
        return parents.get((mapped.get("il_plaka"), mapped.get("ilce_kodu")))
    return None


async def run(path: str, area_type: str, tenant_id: Optional[str], dry_run: bool) -> None:
    if area_type not in AREA_TYPES:
        raise SystemExit(f"--type {area_type} geçersiz (il|ilce|mahalle)")
    if not os.path.exists(path):
        raise SystemExit(f"Dosya yok: {path}")

    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    if tenant_id is None:
        t = await db.tenants.find_one({}, {"_id": 0, "id": 1, "name": 1})
        tenant_id = t["id"] if t else None
        print(f"tenant: {t.get('name') if t else '(yok)'}")

    parents = await _parent_index(db, area_type)
    if area_type != "il":
        print(f"üst seviye indeksi: {len(parents)} kayıt")
        if not parents:
            raise SystemExit(f"'{area_type}' için üst seviye bulunamadı — önce üst seviyeyi içe aktarın.")

    now = datetime.now(timezone.utc).isoformat()
    ops: List[UpdateOne] = []
    total = written = skipped_no_key = orphan = invalid_geom = 0

    async def flush():
        nonlocal ops, written, invalid_geom
        if not ops or dry_run:
            ops = []
            return
        try:
            res = await db.admin_areas.bulk_write(ops, ordered=False)
            written += (res.upserted_count or 0) + (res.modified_count or 0)
        except BulkWriteError as e:
            # 2dsphere indeksi kurtarılamayan geometrileri reddeder; SADECE o
            # kayıtlar atlanır, parti çökmez (admin_areas.py'nin AYNI kararı).
            ok = e.details.get("nUpserted", 0) + e.details.get("nModified", 0)
            written += ok
            invalid_geom += len(e.details.get("writeErrors", []))
        ops = []

    for feat in _iter_features(path):
        total += 1
        props = feat.get("properties") or {}
        mapped = _map_properties(props)
        key = _identity_filter(area_type, mapped)
        if not key:
            skipped_no_key += 1
            continue
        parent_id = _parent_id_for(area_type, mapped, parents)
        if area_type != "il" and not parent_id:
            orphan += 1
            continue

        doc = {
            **mapped,
            "name": _display_name(area_type, mapped),
            "area_type": area_type,
            "parent_id": parent_id,
            "geometry": _clean_geometry(feat.get("geometry")),
            "tenant_id": tenant_id,
            "is_active": True,
            "updated_at": now,
        }
        ops.append(UpdateOne(key, {"$set": doc,
                                   "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
                             upsert=True))
        if len(ops) >= CHUNK:
            await flush()
            print(f"  … {total} feature işlendi", flush=True)

    await flush()
    print(f"\n=== {area_type.upper()} içe aktarma tamamlandı ===")
    print(f"  okunan feature      : {total}")
    print(f"  yazılan/güncellenen : {written}{' (DRY RUN — yazılmadı)' if dry_run else ''}")
    if skipped_no_key:
        print(f"  kod alanı eksik     : {skipped_no_key} (atlandı)")
    if orphan:
        print(f"  üstü bulunamadı     : {orphan} (atlandı)")
    if invalid_geom:
        print(f"  geometri geçersiz   : {invalid_geom} (atlandı)")
    print(f"  toplam kayıt (db)   : {await db.admin_areas.count_documents({'area_type': area_type})}")


def main():
    ap = argparse.ArgumentParser(description="TOPRAX idari alan toplu içe aktarma")
    ap.add_argument("path", help="GeoJSON dosya yolu")
    ap.add_argument("--type", required=True, choices=AREA_TYPES)
    ap.add_argument("--tenant", default=None, help="tenant_id (verilmezse ilk tenant)")
    ap.add_argument("--dry-run", action="store_true", help="yazmadan sadece say")
    args = ap.parse_args()
    asyncio.run(run(args.path, args.type, args.tenant, args.dry_run))


if __name__ == "__main__":
    main()
