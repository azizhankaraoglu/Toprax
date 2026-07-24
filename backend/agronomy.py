"""
=====================================================================
TOPRAX — Ekim Planlama Karar Motoru (#10)
=====================================================================
Bir parselde ŞEKER PANCARI ekiminin/sözleşmesinin uygun olup olmadığına,
o parselin GERÇEK geçmişine bakarak karar veren tavsiye motoru. Amaç
kullanıcının koyduğu hedeftir: **polar oranını (şeker kalitesini)
maksimize etmek**.

Neden `ai_engine.py`'den AYRI bir modül:
  `ai_engine.py` (FAZ 18) GÖRÜNTÜ/nesne tanıma bilgi kayıtları + model
  registry'si üzerine kuruludur (hastalık fotoğrafı → tahmin). Bu modül
  ise TABLOSAL/tarımsal sinyalleri (toprak analizi, NDVI serisi, sulama,
  hastalık geçmişi, geçmiş verim & polar) bir KURAL KÜTÜPHANESİNDEN
  geçirip skor üretir. İki farklı problem, iki farklı veri şekli —
  birleştirmek ikisini de bozardı (forms_module ≠ field_definitions
  ayrımıyla AYNI aile, bkz. CLAUDE.md "Bilinen Tuzaklar").

MİMARİ KARARLAR:
  - **Kural kütüphanesi DB'de, kod'da DEĞİL** (`agronomy_rules`) — kullanıcının
    istediği "düzenlenebilir AI bilgi kütüphanesi" budur: ziraat mühendisi
    yeni bir kural ekleyince KOD DEĞİŞMEZ. `automation.py`'nin (IT-24)
    "admin ekrandan kural tanımlar, motor DB'den okur" kalıbıyla AYNI.
  - Kurallar SİNYALLER üzerinde çalışır; sinyal kataloğu (`SIGNAL_CATALOG`)
    kod seviyesindedir (yeni bir sinyal gerçek bir veri kaynağı bağlamayı
    gerektirir — `PERMISSION_CATALOG`/`INTEGRATION_REGISTRY` ile AYNI
    "kod-seviyesi registry" kalıbı).
  - **AI OPSİYONEL, karar DEĞİL.** Skor ve karar HER ZAMAN deterministik
    kurallardan gelir; AI sadece bu bulguları çiftçiye/mühendise anlatan
    bir METİN üretir (`agronomy_prompts`'taki düzenlenebilir şablonla).
    AI yapılandırılmamışsa kural tabanlı metin üretilir — `extras.py`'nin
    AI Copilot fallback'iyle AYNI dürüstlük deseni (`ai_powered: false`).
  - Motor SAF FONKSİYONDUR (`evaluate_rules`) — DB/HTTP'den bağımsız,
    birim-test edilebilir (IT-20 hakediş motoruyla AYNI felsefe).

DÜRÜSTLÜK NOTU (bilinçli sınırlamalar):
  - `kantar_records` parsel taşımaz (farmer bazlı — bkz. CLAUDE.md IT-05
    notu), bu yüzden polar geçmişi `yields` koleksiyonundan okunur (o
    parsel_id taşır). Kantar verisi bu motora DAHİL EDİLMEDİ — yanlış
    eşleştirme yapmaktansa hiç yapılmadı.
  - İklim/hava durumu sinyali YOK (kurulu bir hava servisi yok).
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel


# =====================================================================
# Sinyal Kataloğu — kuralların üzerinde çalışabileceği ölçümler
# =====================================================================
SIGNAL_CATALOG: List[Dict[str, str]] = [
    # --- Toprak ---
    {"key": "toprak_ph", "label": "Toprak pH", "category": "toprak", "type": "number"},
    {"key": "toprak_ec", "label": "Tuzluluk (EC)", "category": "toprak", "type": "number"},
    {"key": "toprak_om", "label": "Organik Madde (%)", "category": "toprak", "type": "number"},
    {"key": "toprak_n", "label": "Azot (ppm)", "category": "toprak", "type": "number"},
    {"key": "toprak_p", "label": "Fosfor (ppm)", "category": "toprak", "type": "number"},
    {"key": "toprak_k", "label": "Potasyum (ppm)", "category": "toprak", "type": "number"},
    {"key": "toprak_analiz_yasi_gun", "label": "Toprak Analizi Yaşı (gün)", "category": "toprak", "type": "number"},
    {"key": "toprak_analiz_var", "label": "Toprak Analizi Var mı (1/0)", "category": "toprak", "type": "number"},
    # --- Uydu ---
    {"key": "ndvi_son", "label": "Son NDVI", "category": "uydu", "type": "number"},
    {"key": "uydu_goruntu_sayisi", "label": "Uydu Ölçüm Sayısı", "category": "uydu", "type": "number"},
    {"key": "ekim_durumu", "label": "Ekim Durumu", "category": "uydu", "type": "text"},
    # --- Su ---
    {"key": "sulama_tipi", "label": "Sulama Tipi", "category": "su", "type": "text"},
    {"key": "sulama_olay_sayisi", "label": "Sulama Kaydı Sayısı", "category": "su", "type": "number"},
    {"key": "toplam_su_m3", "label": "Toplam Su (m³)", "category": "su", "type": "number"},
    # --- Hastalık ---
    {"key": "hastalik_sayisi", "label": "Hastalık Tespiti Sayısı", "category": "hastalik", "type": "number"},
    # --- Geçmiş performans ---
    {"key": "gecmis_yil_sayisi", "label": "Geçmiş Verim Yılı Sayısı", "category": "gecmis", "type": "number"},
    {"key": "ort_polar", "label": "Ortalama Polar (%)", "category": "gecmis", "type": "number"},
    {"key": "son_polar", "label": "Son Yıl Polar (%)", "category": "gecmis", "type": "number"},
    {"key": "ort_verim_ton_dekar", "label": "Ortalama Verim (ton/dekar)", "category": "gecmis", "type": "number"},
    # Denetim düzeltmesi (2026-07-24) — etiketler ÖNCEDEN "Pancar" adını
    # içeriyordu; motor artık parametrik (herhangi bir ürün) olduğundan
    # genel isimlendirmeye çevrildi. Sinyal ANAHTARLARI (ardisik_pancar_yili
    # vb.) DEĞİŞMEDİ — mevcut kural kayıtları bu anahtarı referans alıyor.
    {"key": "munavebe_ihlali", "label": "Münavebe İhlali (1/0)", "category": "gecmis", "type": "number"},
    {"key": "ardisik_pancar_yili", "label": "Ardışık Yıl (Aynı Ürün)", "category": "gecmis", "type": "number"},
]

SIGNAL_KEYS = {s["key"] for s in SIGNAL_CATALOG}

OPERATORS = ["lt", "lte", "gt", "gte", "eq", "ne", "between", "is_null", "is_not_null"]

DECISION_LABELS = {
    "uygun": "Ekim/Sözleşme Uygun",
    "sartli": "Şartlı Uygun — İyileştirme Gerekli",
    "uygun_degil": "Uygun Değil",
}

# Varsayılan bilgi kütüphanesi. Şeker pancarında POLAR (şeker oranı)
# odaklı agronomik gerçeklere dayanır; kullanıcı ekrandan düzenleyebilir.
DEFAULT_RULES: List[Dict[str, Any]] = [
    {"name": "Toprak analizi hiç yok", "category": "toprak", "signal": "toprak_analiz_var",
     "operator": "eq", "value": 0, "score_delta": -30, "is_blocking": False,
     "advice": "Bu parselde hiç toprak analizi yok. Ekim kararından önce numune alınmalı — "
               "gübreleme körlemesine yapılırsa polar oranı düşer."},
    {"name": "Toprak analizi güncel değil (>2 yıl)", "category": "toprak", "signal": "toprak_analiz_yasi_gun",
     "operator": "gt", "value": 730, "score_delta": -12, "is_blocking": False,
     "advice": "Toprak analizi 2 yıldan eski. Yeni sezon öncesi yenilenmeli."},
    {"name": "Asitli toprak (pH < 6.0)", "category": "toprak", "signal": "toprak_ph",
     "operator": "lt", "value": 6.0, "score_delta": -25, "is_blocking": False,
     "advice": "Şeker pancarı nötr-hafif alkali toprak ister. Kireçleme yapılmadan ekim "
               "önerilmez; asitli toprakta kök gelişimi ve polar düşer."},
    {"name": "Aşırı alkali toprak (pH > 8.2)", "category": "toprak", "signal": "toprak_ph",
     "operator": "gt", "value": 8.2, "score_delta": -12, "is_blocking": False,
     "advice": "Yüksek pH mikro besin (Fe, Mn, Zn) alımını kısıtlar — yapraktan takviye planlanmalı."},
    {"name": "Yüksek tuzluluk (EC > 4)", "category": "toprak", "signal": "toprak_ec",
     "operator": "gt", "value": 4.0, "score_delta": -40, "is_blocking": True,
     "advice": "Tuzluluk kritik seviyede. Yıkama/drenaj yapılmadan pancar ekimi önerilmez — "
               "çimlenme ve kök gelişimi ciddi zarar görür."},
    {"name": "Düşük organik madde (< %1.5)", "category": "toprak", "signal": "toprak_om",
     "operator": "lt", "value": 1.5, "score_delta": -15, "is_blocking": False,
     "advice": "Organik madde düşük. Ahır gübresi/yeşil gübre ile toprak yapısı iyileştirilmeli."},
    {"name": "Aşırı azot (N > 60 ppm) — POLAR DÜŞÜRÜR", "category": "toprak", "signal": "toprak_n",
     "operator": "gt", "value": 60, "score_delta": -20, "is_blocking": False,
     "advice": "KRİTİK: Şeker pancarında fazla azot yaprak gelişimini artırır ama ŞEKER ORANINI "
               "(polar) düşürür. Azotlu gübre dozu azaltılmalı, geç dönem azot verilmemeli."},
    {"name": "Düşük potasyum (K < 120 ppm)", "category": "toprak", "signal": "toprak_k",
     "operator": "lt", "value": 120, "score_delta": -15, "is_blocking": False,
     "advice": "Potasyum şeker taşınımı ve polar oranı için belirleyicidir. K'lı gübre planlanmalı."},
    {"name": "Düşük fosfor (P < 10 ppm)", "category": "toprak", "signal": "toprak_p",
     "operator": "lt", "value": 10, "score_delta": -10, "is_blocking": False,
     "advice": "Fosfor eksikliği erken kök gelişimini yavaşlatır — taban gübresi ile verilmeli."},

    {"name": "Münavebe ihlali — ardışık pancar", "category": "gecmis", "signal": "munavebe_ihlali",
     "operator": "eq", "value": 1, "score_delta": -30, "is_blocking": False,
     "advice": "Bu parselde önceki sezon da pancar ekilmiş. Münavebesiz ekim nematod ve kök "
               "hastalıklarını biriktirir, polar belirgin düşer. En az 3 yıllık münavebe önerilir."},
    {"name": "Uzun süreli monokültür (3+ yıl pancar)", "category": "gecmis", "signal": "ardisik_pancar_yili",
     "operator": "gte", "value": 3, "score_delta": -20, "is_blocking": True,
     "advice": "3+ yıl kesintisiz pancar. Toprak yorgunluğu ve nematod baskısı nedeniyle bu sezon "
               "başka ürüne geçilmesi önerilir."},
    {"name": "Geçmiş polar düşük (< %15)", "category": "gecmis", "signal": "ort_polar",
     "operator": "lt", "value": 15.0, "score_delta": -15, "is_blocking": False,
     "advice": "Parselin geçmiş polar ortalaması hedefin altında. Azot yönetimi ve sulama takvimi "
               "gözden geçirilmeli."},
    {"name": "Geçmiş verim düşük (< 4 ton/dekar)", "category": "gecmis", "signal": "ort_verim_ton_dekar",
     "operator": "lt", "value": 4.0, "score_delta": -12, "is_blocking": False,
     "advice": "Verim geçmişi zayıf. Kota/alan planlaması bu gerçek verime göre yapılmalı."},

    {"name": "Sulama altyapısı yok (kuru tarım)", "category": "su", "signal": "sulama_tipi",
     "operator": "eq", "value": "kuru", "score_delta": -35, "is_blocking": False,
     "advice": "Şeker pancarı yüksek su ister. Sulama imkânı olmadan ekim ciddi verim/polar riski taşır."},
    {"name": "Sulama kaydı hiç yok", "category": "su", "signal": "sulama_olay_sayisi",
     "operator": "eq", "value": 0, "score_delta": -8, "is_blocking": False,
     "advice": "Geçmiş sezonda hiç sulama kaydı girilmemiş. Su takibi yapılmıyorsa hasat öncesi "
               "su kesme zamanlaması (polar için kritik) yönetilemez."},

    {"name": "Hastalık geçmişi var", "category": "hastalik", "signal": "hastalik_sayisi",
     "operator": "gte", "value": 1, "score_delta": -15, "is_blocking": False,
     "advice": "Bu parselde daha önce hastalık tespiti yapılmış. Tohum seçiminde dayanıklı çeşit "
               "tercih edilmeli ve ilaçlama takvimi baştan planlanmalı."},
    {"name": "Yoğun hastalık baskısı (3+ tespit)", "category": "hastalik", "signal": "hastalik_sayisi",
     "operator": "gte", "value": 3, "score_delta": -20, "is_blocking": False,
     "advice": "Tekrarlayan hastalık kaydı. Ekim öncesi toprak dezenfeksiyonu/münavebe zorunlu değerlendirilmeli."},

    {"name": "Uydu verisi yok", "category": "uydu", "signal": "uydu_goruntu_sayisi",
     "operator": "eq", "value": 0, "score_delta": -5, "is_blocking": False,
     "advice": "Bu parsel için uydu ölçümü yok. İzleme başlatılırsa sezon içi stres erken görülebilir."},
]

# Denetim düzeltmesi (2026-07-24) — motor parametrik hale getirildi (istek:
# "sadece pancar var, bunu parametrik yap"). `agronomy_crops` — admin'in
# yönetebildiği bitki kataloğu (`support_types`/`task_types` ile AYNI
# `_ensure_*`/idempotent seed ailesi). Her ürünün kendi kural kütüphanesi
# (`agronomy_rules.crop`) ve AI anlatım şablonu (`agronomy_prompts.crop`)
# vardır — SIGNAL_CATALOG (ölçüm kataloğu) ürünler arasında ORTAKTIR,
# değişmez (toprak/uydu/sulama/hastalık/geçmiş verim her üründe aynı
# şekilde ölçülür, sadece KURALLARIN eşiği/skoru ürüne göre değişir).
DEFAULT_CROP = {
    "key": "pancar", "label": "Şeker Pancarı",
    "match_terms": ["pancar", "şeker pancarı", "seker pancari"],
}

# Sistem promptu {urun} yer tutucusu taşır — crop.label ile doldurulur,
# böylece YENİ bir ürün eklendiğinde varsayılan şablon otomatik uyarlanır
# (admin isterse ürüne özel şablonu ekrandan yine düzenleyebilir).
DEFAULT_PROMPT_TEMPLATE = {
    "label": "Ekim Planlama AI Anlatımı",
    "system_prompt": (
        "Sen {urun} üretiminde uzman bir ziraat mühendisisin. Sana bir parselin "
        "toprak, uydu, sulama, hastalık ve geçmiş verim verileri ile kural motorunun "
        "bulguları verilecek. Görevin: çiftçinin anlayacağı sade bir Türkçe ile, bu parselde "
        "bu sezon {urun} ekilmeli mi sorusunu yanıtlamak. Kararı değiştirme, sadece açıkla "
        "ve somut eylem önerileri ver. En fazla 6 madde yaz."
    ),
    "user_template": (
        "Parsel: {parsel_adi} ({il}/{ilce}/{mahalle}, {alan} dekar)\n"
        "Sezon: {sezon}, Çeşit: {cesit}\n"
        "Kural motoru skoru: {skor}/100 — Karar: {karar}\n\n"
        "ÖLÇÜMLER:\n{sinyaller}\n\n"
        "TESPİT EDİLEN SORUNLAR:\n{bulgular}\n\n"
        "Bu parsel için değerlendirmeni yaz."
    ),
}


def _default_prompt_for(crop_label: str) -> Dict[str, str]:
    return {
        "label": DEFAULT_PROMPT_TEMPLATE["label"],
        "system_prompt": DEFAULT_PROMPT_TEMPLATE["system_prompt"].format(urun=crop_label),
        "user_template": DEFAULT_PROMPT_TEMPLATE["user_template"],
    }


DEFAULT_VARIETIES = [
    "Leila", "Bardolino", "Danton", "Esperanza", "Fabiola",
    "Gazelle", "Kaunas", "Modus", "Sabrina", "Vasco",
]


# =====================================================================
# SAF MOTOR — DB/HTTP bağımsız (birim-test edilebilir)
# =====================================================================
def _match(rule: Dict[str, Any], signals: Dict[str, Any]) -> bool:
    """Tek bir kuralın sinyallere uyup uymadığı. Sinyal yoksa (None) SADECE
    is_null eşleşir — eksik veri yanlışlıkla "sorun yok" sayılmaz."""
    sig = signals.get(rule.get("signal"))
    op = rule.get("operator")
    val = rule.get("value")

    if op == "is_null":
        return sig is None
    if op == "is_not_null":
        return sig is not None
    if sig is None:
        return False

    try:
        if op in ("lt", "lte", "gt", "gte", "between"):
            s = float(sig)
            v = float(val)
            if op == "lt":
                return s < v
            if op == "lte":
                return s <= v
            if op == "gt":
                return s > v
            if op == "gte":
                return s >= v
            v2 = float(rule.get("value2"))
            return v <= s <= v2
        # eq/ne — sayı ise sayısal, değilse metin (küçük harf) karşılaştırması
        try:
            same = float(sig) == float(val)
        except (TypeError, ValueError):
            same = str(sig).strip().lower() == str(val).strip().lower()
        return same if op == "eq" else (not same)
    except (TypeError, ValueError):
        return False


def evaluate_rules(rules: List[Dict[str, Any]], signals: Dict[str, Any]) -> Dict[str, Any]:
    """Kural kütüphanesini sinyallere uygular. SAF fonksiyon.
    100 puandan başlar, eşleşen her kuralın score_delta'sı uygulanır."""
    score = 100.0
    matched: List[Dict[str, Any]] = []
    blocking = False

    for r in rules:
        if r.get("is_active") is False:
            continue
        if not _match(r, signals):
            continue
        delta = float(r.get("score_delta") or 0)
        score += delta
        if r.get("is_blocking"):
            blocking = True
        matched.append({
            "id": r.get("id"), "name": r.get("name"), "category": r.get("category"),
            "signal": r.get("signal"), "advice": r.get("advice"),
            "score_delta": delta, "is_blocking": bool(r.get("is_blocking")),
        })

    score = max(0.0, min(100.0, score))
    if blocking:
        decision = "uygun_degil"
    elif score >= 70:
        decision = "uygun"
    elif score >= 45:
        decision = "sartli"
    else:
        decision = "uygun_degil"

    matched.sort(key=lambda m: m["score_delta"])
    return {
        "score": round(score, 1),
        "decision": decision,
        "decision_label": DECISION_LABELS[decision],
        "blocking": blocking,
        "matched_rules": matched,
    }


def register_agronomy_routes(api_router, db, current_user, require_permission, log_audit):

    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # =================================================================
    # Parsel arama (aranabilir combobox) — #10'un ilk isteği
    # =================================================================
    # NOT: Bilinçli olarak `/parcels/search` DEĞİL — server.py'deki
    # `/parcels/{parcel_id}` route'u "search"i bir id sanardı (bkz.
    # CLAUDE.md'nin `/parcels/bulk-update` route-sırası notu). Kendi
    # ad alanımızda açmak bu tuzağı tamamen ortadan kaldırır.
    @api_router.get("/ekim-planlama/parcel-search")
    async def parcel_search(q: str = "", limit: int = 20,
                            user=Depends(require_permission("plantings:view"))):
        """il / ilçe / mahalle / ada / parsel no / parsel adı üzerinden arama."""
        q = (q or "").strip()
        if len(q) < 2:
            return []
        rx = {"$regex": re.escape(q), "$options": "i"}
        filt = {
            "is_active": {"$ne": False},
            "$or": [
                {"name": rx}, {"il": rx}, {"ilce": rx}, {"mahalle": rx},
                {"ada_no": rx}, {"parsel_no_tapu": rx}, {"village": rx},
            ],
        }
        limit = max(1, min(limit, 50))
        docs = await db.parcels.find(filt, {
            "_id": 0, "id": 1, "name": 1, "il": 1, "ilce": 1, "mahalle": 1,
            "ada_no": 1, "parsel_no_tapu": 1, "village": 1, "area_dekar": 1,
            "farmer_id": 1, "ekim_durumu": 1,
        }).limit(limit).to_list(limit)

        farmer_ids = [d.get("farmer_id") for d in docs if d.get("farmer_id")]
        fmap = {}
        if farmer_ids:
            for f in await db.farmers.find({"id": {"$in": farmer_ids}},
                                           {"_id": 0, "id": 1, "full_name": 1}).to_list(200):
                fmap[f["id"]] = f.get("full_name")

        for d in docs:
            d["farmer_name"] = fmap.get(d.get("farmer_id"))
            konum = " / ".join([x for x in [d.get("il"), d.get("ilce"),
                                            d.get("mahalle") or d.get("village")] if x])
            tapu = ""
            if d.get("ada_no") or d.get("parsel_no_tapu"):
                tapu = f" — Ada {d.get('ada_no') or '?'} Parsel {d.get('parsel_no_tapu') or '?'}"
            d["display"] = f"{d.get('name') or 'İsimsiz parsel'}{tapu}" + (f" ({konum})" if konum else "")
        return docs

    # =================================================================
    # Çeşit lookup'ı
    # =================================================================
    @api_router.get("/ekim-planlama/varieties")
    async def list_varieties(crop: str = DEFAULT_CROP["key"],
                             user=Depends(require_permission("plantings:view"))):
        # Denetim düzeltmesi (2026-07-24) — lookup grup anahtarı artık ÜRÜNE
        # göre ("{crop}_cesidi") — her ürün kendi çeşit listesini taşıyabilir.
        grp = await db.lookup_groups.find_one({"key": f"{crop}_cesidi"}, {"_id": 0})
        if not grp:
            return []
        vals = await db.lookup_values.find(
            {"group_id": grp["id"], "is_active": {"$ne": False}}, {"_id": 0}
        ).sort([("order", 1)]).to_list(200)
        return vals

    # =================================================================
    # Bitki kataloğu — parametrik ürün listesi (Denetim düzeltmesi 2026-07-24)
    # =================================================================
    class CropCreate(BaseModel):
        key: str
        label: str
        match_terms: List[str] = []   # boşsa [label.lower()] varsayılır

    class CropUpdate(BaseModel):
        label: Optional[str] = None
        match_terms: Optional[List[str]] = None
        is_active: Optional[bool] = None

    async def _crop_or_404(crop_key: str) -> Dict[str, Any]:
        doc = await db.agronomy_crops.find_one({"key": crop_key, "is_active": {"$ne": False}}, {"_id": 0})
        if not doc:
            raise HTTPException(404, f"Bilinmeyen veya pasif ürün: {crop_key}")
        return doc

    @api_router.get("/agronomy/crops")
    async def list_crops(user=Depends(require_permission("plantings:view"))):
        return await db.agronomy_crops.find(
            {"is_active": {"$ne": False}}, {"_id": 0}).sort([("label", 1)]).to_list(200)

    @api_router.post("/agronomy/crops")
    async def create_crop(body: CropCreate, request: Request,
                          user=Depends(require_permission("agronomy:rules_manage"))):
        key = body.key.strip().lower().replace(" ", "_")
        if not key:
            raise HTTPException(400, "Geçersiz ürün anahtarı")
        existing = await db.agronomy_crops.find_one({"key": key}, {"_id": 0})
        if existing:
            if existing.get("is_active", True):
                raise HTTPException(400, f"'{key}' anahtarlı bir ürün zaten var")
            # Daha önce kaldırılmış (soft-delete) bir ürün YENİDEN eklenmeye
            # çalışılıyor — anahtarı sonsuza dek "kullanılamaz" bırakmak
            # yerine yeniden ETKİNLEŞTİRİLİR (kuralları zaten silinmemişti).
            terms = [t.strip().lower() for t in body.match_terms if t.strip()] or [body.label.strip().lower()]
            await db.agronomy_crops.update_one(
                {"key": key}, {"$set": {"label": body.label, "match_terms": terms, "is_active": True}})
            new = await db.agronomy_crops.find_one({"key": key}, {"_id": 0})
            await log_audit(db, user, action="reactivate", entity="agronomy_crop",
                            entity_id=new["id"], old_value=existing, new_value=new, request=request)
            return new
        doc = {
            "id": str(uuid.uuid4()), "key": key, "label": body.label,
            "match_terms": [t.strip().lower() for t in body.match_terms if t.strip()] or [body.label.strip().lower()],
            "is_active": True, "is_default": False, "created_at": _now(),
        }
        await db.agronomy_crops.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="agronomy_crop",
                        entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/agronomy/crops/{crop_id}")
    async def update_crop(crop_id: str, body: CropUpdate, request: Request,
                          user=Depends(require_permission("agronomy:rules_manage"))):
        old = await db.agronomy_crops.find_one({"id": crop_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Ürün bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if "match_terms" in updates:
            updates["match_terms"] = [t.strip().lower() for t in updates["match_terms"] if t.strip()]
        if updates:
            await db.agronomy_crops.update_one({"id": crop_id}, {"$set": updates})
        new = await db.agronomy_crops.find_one({"id": crop_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="agronomy_crop",
                        entity_id=crop_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/agronomy/crops/{crop_id}")
    async def delete_crop(crop_id: str, request: Request,
                          user=Depends(require_permission("agronomy:rules_manage"))):
        """Soft delete — o ürüne ait kural kütüphanesi/geçmiş analizler
        SİLİNMEZ (convention #3), sadece ürün seçim listesinden kalkar."""
        old = await db.agronomy_crops.find_one({"id": crop_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Ürün bulunamadı")
        await db.agronomy_crops.update_one({"id": crop_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="soft_delete", entity="agronomy_crop",
                        entity_id=crop_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =================================================================
    # Bilgi kütüphanesi (kurallar) — düzenlenebilir, ÜRÜNE göre ayrılır
    # =================================================================
    class RuleCreate(BaseModel):
        name: str
        crop: str = DEFAULT_CROP["key"]
        category: str = "toprak"
        signal: str
        operator: str = "lt"
        value: Optional[Any] = None
        value2: Optional[Any] = None
        score_delta: float = -10
        advice: str = ""
        is_blocking: bool = False
        order: int = 100

    class RuleUpdate(BaseModel):
        name: Optional[str] = None
        crop: Optional[str] = None
        category: Optional[str] = None
        signal: Optional[str] = None
        operator: Optional[str] = None
        value: Optional[Any] = None
        value2: Optional[Any] = None
        score_delta: Optional[float] = None
        advice: Optional[str] = None
        is_blocking: Optional[bool] = None
        order: Optional[int] = None
        is_active: Optional[bool] = None

    def _validate_rule(signal: Optional[str], operator: Optional[str]):
        if signal is not None and signal not in SIGNAL_KEYS:
            raise HTTPException(400, f"Bilinmeyen sinyal: {signal}")
        if operator is not None and operator not in OPERATORS:
            raise HTTPException(400, f"Bilinmeyen operatör: {operator}")

    @api_router.get("/agronomy/signals")
    async def list_signals(user=Depends(require_permission("plantings:view"))):
        return {"signals": SIGNAL_CATALOG, "operators": OPERATORS}

    @api_router.get("/agronomy/rules")
    async def list_rules(crop: str = DEFAULT_CROP["key"],
                         user=Depends(require_permission("plantings:view"))):
        return await db.agronomy_rules.find(
            {"is_active": {"$ne": False}, "crop": crop}, {"_id": 0}
        ).sort([("order", 1)]).to_list(500)

    @api_router.post("/agronomy/rules")
    async def create_rule(body: RuleCreate, request: Request,
                          user=Depends(require_permission("agronomy:rules_manage"))):
        _validate_rule(body.signal, body.operator)
        await _crop_or_404(body.crop)
        doc = body.model_dump()
        doc.update({"id": str(uuid.uuid4()), "is_active": True,
                    "is_default": False, "created_at": _now()})
        await db.agronomy_rules.insert_one(doc)
        doc.pop("_id", None)
        await log_audit(db, user, action="create", entity="agronomy_rule",
                        entity_id=doc["id"], new_value=doc, request=request)
        return doc

    @api_router.put("/agronomy/rules/{rule_id}")
    async def update_rule(rule_id: str, body: RuleUpdate, request: Request,
                          user=Depends(require_permission("agronomy:rules_manage"))):
        old = await db.agronomy_rules.find_one({"id": rule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kural bulunamadı")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        _validate_rule(updates.get("signal"), updates.get("operator"))
        if "crop" in updates:
            await _crop_or_404(updates["crop"])
        if updates:
            await db.agronomy_rules.update_one({"id": rule_id}, {"$set": updates})
        new = await db.agronomy_rules.find_one({"id": rule_id}, {"_id": 0})
        await log_audit(db, user, action="update", entity="agronomy_rule",
                        entity_id=rule_id, old_value=old, new_value=new, request=request)
        return new

    @api_router.delete("/agronomy/rules/{rule_id}")
    async def delete_rule(rule_id: str, request: Request,
                          user=Depends(require_permission("agronomy:rules_manage"))):
        old = await db.agronomy_rules.find_one({"id": rule_id}, {"_id": 0})
        if not old:
            raise HTTPException(404, "Kural bulunamadı")
        await db.agronomy_rules.update_one({"id": rule_id}, {"$set": {"is_active": False}})
        await log_audit(db, user, action="soft_delete", entity="agronomy_rule",
                        entity_id=rule_id, old_value=old, request=request)
        return {"status": "deactivated"}

    # =================================================================
    # AI prompt kütüphanesi — düzenlenebilir
    # =================================================================
    class PromptUpdate(BaseModel):
        system_prompt: Optional[str] = None
        user_template: Optional[str] = None

    def _prompt_key(crop: str) -> str:
        return f"ekim_planlama_{crop}"

    @api_router.get("/agronomy/prompt")
    async def get_prompt(crop: str = DEFAULT_CROP["key"],
                         user=Depends(require_permission("plantings:view"))):
        doc = await db.agronomy_prompts.find_one({"key": _prompt_key(crop)}, {"_id": 0})
        if doc:
            return doc
        crop_doc = await db.agronomy_crops.find_one({"key": crop}, {"_id": 0})
        return _default_prompt_for(crop_doc["label"] if crop_doc else crop)

    @api_router.put("/agronomy/prompt")
    async def update_prompt(body: PromptUpdate, request: Request, crop: str = DEFAULT_CROP["key"],
                            user=Depends(require_permission("agronomy:rules_manage"))):
        pkey = _prompt_key(crop)
        old = await db.agronomy_prompts.find_one({"key": pkey}, {"_id": 0})
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        updates["updated_at"] = _now()
        await db.agronomy_prompts.update_one(
            {"key": pkey},
            {"$set": updates, "$setOnInsert": {"id": str(uuid.uuid4()), "key": pkey,
                                               "crop": crop, "label": DEFAULT_PROMPT_TEMPLATE["label"]}},
            upsert=True)
        new = await db.agronomy_prompts.find_one({"key": pkey}, {"_id": 0})
        await log_audit(db, user, action="update", entity="agronomy_prompt",
                        entity_id=pkey, old_value=old, new_value=new, request=request)
        return new

    # =================================================================
    # Idempotent seed
    # =================================================================
    @api_router.post("/agronomy/seed-defaults")
    async def seed_defaults(request: Request,
                            user=Depends(require_permission("agronomy:rules_manage"))):
        # Denetim düzeltmesi (2026-07-24) — bitki kataloğuna varsayılan "Şeker
        # Pancarı" kaydı (idempotent) — mevcut DEFAULT_RULES/DEFAULT_PROMPT_
        # TEMPLATE zaten bu ürün için yazılmıştı, davranış AYNEN korunur.
        crop_key = DEFAULT_CROP["key"]
        if not await db.agronomy_crops.find_one({"key": crop_key}, {"_id": 0}):
            await db.agronomy_crops.insert_one({
                "id": str(uuid.uuid4()), **DEFAULT_CROP,
                "is_active": True, "is_default": True, "created_at": _now(),
            })

        added = 0
        for i, r in enumerate(DEFAULT_RULES):
            if await db.agronomy_rules.find_one({"name": r["name"], "crop": crop_key}, {"_id": 0}):
                continue
            doc = dict(r)
            doc.update({"id": str(uuid.uuid4()), "crop": crop_key, "is_active": True, "is_default": True,
                        "order": (i + 1) * 10, "created_at": _now()})
            await db.agronomy_rules.insert_one(doc)
            added += 1

        pkey = _prompt_key(crop_key)
        if not await db.agronomy_prompts.find_one({"key": pkey}, {"_id": 0}):
            p = _default_prompt_for(DEFAULT_CROP["label"])
            p.update({"id": str(uuid.uuid4()), "key": pkey, "crop": crop_key, "created_at": _now()})
            await db.agronomy_prompts.insert_one(p)

        # Çeşit lookup grubu (field_definitions.py'nin _ensure_* kalıbıyla AYNI şekil)
        variety_group_key = f"{crop_key}_cesidi"
        grp = await db.lookup_groups.find_one({"key": variety_group_key}, {"_id": 0})
        if not grp:
            grp = {"id": str(uuid.uuid4()), "key": variety_group_key,
                   "label": f"{DEFAULT_CROP['label']} Çeşidi", "order": 90, "parent_group_id": None,
                   "is_active": True, "created_at": _now()}
            await db.lookup_groups.insert_one(dict(grp))
        varieties_added = 0
        for i, v in enumerate(DEFAULT_VARIETIES):
            slug = v.lower().replace(" ", "_")
            if await db.lookup_values.find_one({"group_id": grp["id"], "value": slug}, {"_id": 0}):
                continue
            await db.lookup_values.insert_one({
                "id": str(uuid.uuid4()), "group_id": grp["id"], "value": slug, "label": v,
                "order": (i + 1) * 10, "parent_id": None, "is_active": True, "created_at": _now()})
            varieties_added += 1

        await log_audit(db, user, action="seed", entity="agronomy",
                        entity_id="defaults", new_value={"rules": added}, request=request)
        return {"rules_added": added, "varieties_added": varieties_added,
                "total_rules": await db.agronomy_rules.count_documents({"is_active": {"$ne": False}})}

    # =================================================================
    # Sinyal toplama — GERÇEK veriden
    # =================================================================
    async def _gather_signals(parcel: Dict[str, Any], season: int, match_terms: List[str]) -> Dict[str, Any]:
        pid = parcel["id"]
        sig: Dict[str, Any] = {}
        detay: Dict[str, Any] = {}

        # --- Toprak: en güncel analiz ---
        soil = await db.soil_samples.find(
            {"parcel_id": pid, "is_active": {"$ne": False}}, {"_id": 0}
        ).sort([("sample_date", -1)]).to_list(20)
        latest = soil[0] if soil else None
        sig["toprak_analiz_var"] = 1 if latest else 0
        if latest:
            sig["toprak_ph"] = latest.get("ph")
            sig["toprak_ec"] = latest.get("ec")
            sig["toprak_om"] = latest.get("organic_matter_pct")
            sig["toprak_n"] = latest.get("n_ppm")
            sig["toprak_p"] = latest.get("p_ppm")
            sig["toprak_k"] = latest.get("k_ppm")
            ds = latest.get("sample_date") or latest.get("created_at")
            yas = None
            if ds:
                try:
                    d = datetime.fromisoformat(str(ds).replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=timezone.utc)
                    yas = (datetime.now(timezone.utc) - d).days
                except (ValueError, TypeError):
                    yas = None
            sig["toprak_analiz_yasi_gun"] = yas
            detay["toprak_analiz_tarihi"] = ds
            detay["toprak_oneri"] = latest.get("recommendation")

        # --- Uydu ---
        sig["ndvi_son"] = parcel.get("son_ndvi")
        stats_n = await db.remote_sensing_statistics.count_documents({"parcel_id": pid})
        sig["uydu_goruntu_sayisi"] = stats_n
        sig["ekim_durumu"] = parcel.get("ekim_durumu")
        detay["crop_status_date"] = parcel.get("crop_status_date")

        # --- Su ---
        sig["sulama_tipi"] = parcel.get("irrigation")
        irr = await db.irrigation_events.find(
            {"parcel_id": pid, "is_active": {"$ne": False}}, {"_id": 0}).to_list(500)
        sig["sulama_olay_sayisi"] = len(irr)
        sig["toplam_su_m3"] = round(sum(e.get("water_m3") or 0 for e in irr), 1) if irr else 0

        # --- Hastalık ---
        sig["hastalik_sayisi"] = await db.disease_detections.count_documents({"parcel_id": pid})

        # --- Geçmiş verim & polar (yields parcel_id taşır) ---
        ylds = await db.yields.find({"parcel_id": pid}, {"_id": 0}).to_list(100)
        polars = [y.get("polar_oran") for y in ylds if y.get("polar_oran")]
        sig["gecmis_yil_sayisi"] = len(ylds)
        if polars:
            sig["ort_polar"] = round(sum(polars) / len(polars), 2)
        son = sorted(ylds, key=lambda y: y.get("season") or 0)
        if son and son[-1].get("polar_oran"):
            sig["son_polar"] = son[-1]["polar_oran"]
        alan = parcel.get("area_dekar") or 0
        tons = [y.get("actual_ton") for y in ylds if y.get("actual_ton")]
        if tons and alan:
            sig["ort_verim_ton_dekar"] = round((sum(tons) / len(tons)) / alan, 2)
        detay["gecmis_sezonlar"] = sorted(
            [{"season": y.get("season"), "ton": y.get("actual_ton"), "polar": y.get("polar_oran")}
             for y in ylds], key=lambda x: x["season"] or 0, reverse=True)[:6]

        # --- Münavebe: ardışık AYNI ÜRÜN yılı (plantings + yields birleşimi) ---
        # Denetim düzeltmesi (2026-07-24) — ÖNCEDEN hardcoded "ancar" (pancar)
        # alt-string eşleşmesiydi; artık seçili ürünün `match_terms` listesine
        # (agronomy_crops, admin düzenler) göre eşleşir — herhangi bir ürün
        # için doğru çalışır.
        plant = await db.plantings.find(
            {"parcel_id": pid, "is_active": {"$ne": False}}, {"_id": 0}).to_list(100)
        terms = [t.strip().lower() for t in (match_terms or []) if t and t.strip()]
        crop_yillari = set()
        for rec in list(plant) + list(ylds):
            crop = str(rec.get("crop") or "").strip().lower()
            if crop and any(term in crop for term in terms) and rec.get("season"):
                crop_yillari.add(int(rec["season"]))
        ardisik = 0
        yil = int(season) - 1
        while yil in crop_yillari:
            ardisik += 1
            yil -= 1
        sig["ardisik_pancar_yili"] = ardisik
        sig["munavebe_ihlali"] = 1 if ardisik >= 1 else 0
        detay["ayni_urun_ekilen_yillar"] = sorted(crop_yillari, reverse=True)[:8]

        return sig, detay

    def _build_narrative(parcel, season, variety, result, sig) -> str:
        """AI yokken kural tabanlı, dürüst bir özet (extras.py fallback deseni)."""
        lines = [f"{parcel.get('name') or 'Parsel'} — {season} sezonu değerlendirmesi: "
                 f"{result['decision_label']} (skor {result['score']}/100)."]
        if not result["matched_rules"]:
            lines.append("Kural kütüphanesinde bu parsel için olumsuz bir bulgu tespit edilmedi.")
        for m in result["matched_rules"][:6]:
            isaret = "ENGEL" if m["is_blocking"] else f"{m['score_delta']:+.0f}"
            lines.append(f"[{isaret}] {m['name']}: {m['advice']}")
        if sig.get("ort_polar"):
            lines.append(f"Parselin geçmiş polar ortalaması %{sig['ort_polar']}.")
        return "\n".join(lines)

    # =================================================================
    # ANALİZ — #10'un ana ucu
    # =================================================================
    class AnalyzeRequest(BaseModel):
        parcel_id: str
        crop: str = DEFAULT_CROP["key"]
        season: Optional[int] = None
        variety: Optional[str] = None
        use_ai: bool = True

    @api_router.post("/ekim-planlama/analyze")
    async def analyze(body: AnalyzeRequest, request: Request,
                      user=Depends(require_permission("agronomy:analyze"))):
        parcel = await db.parcels.find_one(
            {"id": body.parcel_id, "is_active": {"$ne": False}}, {"_id": 0})
        if not parcel:
            raise HTTPException(404, "Parsel bulunamadı")
        crop_doc = await _crop_or_404(body.crop)
        season = body.season or datetime.now(timezone.utc).year

        rules = await db.agronomy_rules.find(
            {"is_active": {"$ne": False}, "crop": body.crop}, {"_id": 0}).sort([("order", 1)]).to_list(500)
        if not rules:
            raise HTTPException(
                400, f"'{crop_doc['label']}' için bilgi kütüphanesi boş. Önce kural ekleyin "
                     "(varsayılan ürün için 'Varsayılanları Yükle' kullanılabilir).")

        sig, detay = await _gather_signals(parcel, season, crop_doc.get("match_terms") or [])
        result = evaluate_rules(rules, sig)

        # Eksik veri şeffaflığı — "veri yok" ile "sorun yok" karıştırılmasın
        gaps = []
        if not sig.get("toprak_analiz_var"):
            gaps.append("Toprak analizi yok")
        if not sig.get("uydu_goruntu_sayisi"):
            gaps.append("Uydu ölçümü yok")
        if not sig.get("gecmis_yil_sayisi"):
            gaps.append("Geçmiş verim kaydı yok")
        if sig.get("ndvi_son") is None:
            gaps.append("Güncel NDVI yok")

        farmer = None
        if parcel.get("farmer_id"):
            farmer = await db.farmers.find_one({"id": parcel["farmer_id"]},
                                               {"_id": 0, "id": 1, "full_name": 1, "member_no": 1})

        # --- AI anlatımı (opsiyonel, kararı DEĞİŞTİRMEZ) ---
        narrative = _build_narrative(parcel, season, body.variety, result, sig)
        ai_powered = False
        ai_error = None
        if body.use_ai:
            try:
                from ai_router import get_ai_router
                router = await get_ai_router(db)
                if router.local or router.external:
                    prompt = await db.agronomy_prompts.find_one({"key": _prompt_key(body.crop)}, {"_id": 0}) \
                             or _default_prompt_for(crop_doc["label"])
                    sinyal_metni = "\n".join(
                        f"- {s['label']}: {sig.get(s['key'])}"
                        for s in SIGNAL_CATALOG if sig.get(s["key"]) is not None)
                    bulgu_metni = "\n".join(
                        f"- {m['name']} ({m['score_delta']:+.0f}): {m['advice']}"
                        for m in result["matched_rules"]) or "- Olumsuz bulgu yok"
                    user_text = (prompt.get("user_template") or DEFAULT_PROMPT_TEMPLATE["user_template"]).format(
                        parsel_adi=parcel.get("name") or "-", il=parcel.get("il") or "-",
                        ilce=parcel.get("ilce") or "-",
                        mahalle=parcel.get("mahalle") or parcel.get("village") or "-",
                        alan=parcel.get("area_dekar") or "-", sezon=season,
                        cesit=body.variety or "-", skor=result["score"],
                        karar=result["decision_label"], sinyaller=sinyal_metni, bulgular=bulgu_metni)
                    text = router.generate_text(
                        prompt.get("system_prompt") or DEFAULT_PROMPT_TEMPLATE["system_prompt"].format(urun=crop_doc["label"]),
                        user_text)
                    if text and text.strip():
                        narrative = text.strip()
                        ai_powered = True
            except Exception as e:                                  # noqa: BLE001
                # AI hatası analizi ÇÖKERTMEZ — kural tabanlı sonuç zaten hazır.
                ai_error = str(e)[:200]

        out = {
            "parcel": {"id": parcel["id"], "name": parcel.get("name"),
                       "il": parcel.get("il"), "ilce": parcel.get("ilce"),
                       "mahalle": parcel.get("mahalle") or parcel.get("village"),
                       "area_dekar": parcel.get("area_dekar"),
                       "ada_no": parcel.get("ada_no"),
                       "parsel_no_tapu": parcel.get("parsel_no_tapu")},
            "farmer": farmer,
            "crop": body.crop,
            "crop_label": crop_doc["label"],
            "season": season,
            "variety": body.variety,
            "score": result["score"],
            "decision": result["decision"],
            "decision_label": result["decision_label"],
            "matched_rules": result["matched_rules"],
            "signals": sig,
            "details": detay,
            "data_gaps": gaps,
            "narrative": narrative,
            "ai_powered": ai_powered,
            "ai_error": ai_error,
            "analyzed_at": _now(),
        }

        # Analiz izlenebilir olsun (otomasyon/rapor için) — kayıt tutulur.
        await db.agronomy_analyses.insert_one({
            "id": str(uuid.uuid4()), "parcel_id": parcel["id"], "crop": body.crop, "season": season,
            "variety": body.variety, "score": result["score"], "decision": result["decision"],
            "matched_rule_ids": [m["id"] for m in result["matched_rules"]],
            "ai_powered": ai_powered, "created_at": _now(),
            "created_by": user.get("id"), "created_by_name": user.get("full_name"),
        })
        return out

    @api_router.get("/ekim-planlama/analyses")
    async def list_analyses(parcel_id: Optional[str] = None, limit: int = 50,
                            user=Depends(require_permission("plantings:view"))):
        filt = {}
        if parcel_id:
            filt["parcel_id"] = parcel_id
        return await db.agronomy_analyses.find(filt, {"_id": 0}).sort(
            [("created_at", -1)]).limit(min(limit, 200)).to_list(200)

    # =================================================================
    # TOPLU SORGU — Denetim düzeltmesi (2026-07-24): "bu sene X ekmeye en
    # uygun alanlar hangileri" — tekil analiz motorunun (evaluate_rules)
    # AYNI kural kütüphanesini bir parsel HAVUZUNA uygular ve skora göre
    # SIRALAR. AI çağrısı YAPILMAZ (yüzlerce parsel için pahalı/yavaş
    # olurdu — bkz. analyze()'in tekil AI anlatımı, o ayrı kalır); bu uç
    # SADECE deterministik kural motorunun (saniyeler içinde biten) skorunu
    # döner. crud_base.py'nin CSV export'undaki "ilk N kayıt + truncated
    # bayrağı" bilinçli sınırlama ailesiyle AYNI — silent cap YOK.
    # =================================================================
    class BulkAnalyzeRequest(BaseModel):
        crop: str = DEFAULT_CROP["key"]
        season: Optional[int] = None
        parcel_ids: Optional[List[str]] = None   # verilirse SADECE bunlar taranır
        il: Optional[str] = None
        ilce: Optional[str] = None
        scan_limit: int = 1000                    # taranacak parsel üst sınırı
        top_n: Optional[int] = None                # sonuç listesini en iyi N ile sınırla

    @api_router.post("/ekim-planlama/bulk-analyze")
    async def bulk_analyze(body: BulkAnalyzeRequest,
                           user=Depends(require_permission("agronomy:analyze"))):
        crop_doc = await _crop_or_404(body.crop)
        season = body.season or datetime.now(timezone.utc).year
        match_terms = crop_doc.get("match_terms") or []

        rules = await db.agronomy_rules.find(
            {"is_active": {"$ne": False}, "crop": body.crop}, {"_id": 0}).sort([("order", 1)]).to_list(500)
        if not rules:
            raise HTTPException(
                400, f"'{crop_doc['label']}' için bilgi kütüphanesi boş. Önce kural ekleyin.")

        filt: Dict[str, Any] = {"is_active": {"$ne": False}}
        if body.parcel_ids:
            filt["id"] = {"$in": body.parcel_ids}
        if body.il:
            filt["il"] = body.il
        if body.ilce:
            filt["ilce"] = body.ilce

        total_candidates = await db.parcels.count_documents(filt)
        scan_limit = max(1, min(body.scan_limit, 2000))
        parcels = await db.parcels.find(filt, {"_id": 0}).limit(scan_limit).to_list(scan_limit)

        results = []
        for parcel in parcels:
            sig, _ = await _gather_signals(parcel, season, match_terms)
            r = evaluate_rules(rules, sig)
            results.append({
                "parcel_id": parcel["id"], "name": parcel.get("name"),
                "il": parcel.get("il"), "ilce": parcel.get("ilce"),
                "mahalle": parcel.get("mahalle") or parcel.get("village"),
                "area_dekar": parcel.get("area_dekar"), "farmer_id": parcel.get("farmer_id"),
                "score": r["score"], "decision": r["decision"], "decision_label": r["decision_label"],
                "blocking": r["blocking"],
                "top_issues": [{"name": m["name"], "score_delta": m["score_delta"]} for m in r["matched_rules"][:3]],
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        truncated = total_candidates > len(parcels)
        if body.top_n:
            results = results[:max(1, body.top_n)]

        return {
            "crop": body.crop, "crop_label": crop_doc["label"], "season": season,
            "total_candidates": total_candidates, "scanned": len(parcels),
            "truncated": truncated, "results": results,
        }
