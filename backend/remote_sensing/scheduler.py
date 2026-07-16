"""
TOPRAX Remote Sensing — Tarama Politikası motoru (Karar 2, filtre bazlı).

Communication Policy (IT-27) ile AYNI desen: kural = Query Engine filtresi
+ sıklık + indeks listesi + öncelik. Admin KOD YAZMADAN kural tanımlar.
Çakışan politikalarda EN YÜKSEK öncelikli KAZANIR. Her parsel en az bir
politikaya düşmeli; kapsam dışı kalanlar "Politikasız Parseller" uyarısında.

Not: scheduler request context DIŞINDA çalışır (background), bu yüzden
execute_query'nin (query_engine.py) permission gate'ine takılmamak için
parsel filtresi burada hafif bir eşleyiciyle uygulanır — filtre DSL'i
Query Engine ile AYNI şekildedir ({field, operator, value}).
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from .dto import FREQUENCY_DAYS, ScanFrequency
from .tasks import create_task, process_pending_tasks


def _match_condition(parcel: dict, cond: dict) -> bool:
    field, op, val = cond.get("field"), cond.get("operator", "eq"), cond.get("value")
    actual = parcel.get(field)
    try:
        if op in ("eq", "="):
            return actual == val
        if op in ("ne", "!="):
            return actual != val
        if op in ("gt", ">"):
            return actual is not None and actual > val
        if op in ("gte", ">="):
            return actual is not None and actual >= val
        if op in ("lt", "<"):
            return actual is not None and actual < val
        if op in ("lte", "<="):
            return actual is not None and actual <= val
        if op == "contains":
            return actual is not None and str(val).lower() in str(actual).lower()
        if op == "in":
            return actual in (val or [])
    except TypeError:
        return False
    return False


def match_parcel(parcel: dict, filters: List[dict], logic: str = "AND") -> bool:
    if not filters:
        return True   # filtre yok = "hepsi" (varsayılan politika)
    results = [_match_condition(parcel, c) for c in filters]
    return all(results) if logic.upper() == "AND" else any(results)


def _policy_filters(policy: dict) -> List[dict]:
    """Politika filtresi hem {conditions:[...], logic} hem düz liste kabul eder."""
    flt = policy.get("filter") or {}
    if isinstance(flt, list):
        return flt
    return flt.get("conditions", flt.get("filters", []))


async def resolve_covering_policy(db, parcel: dict, policies: List[dict]):
    """Bir parseli kapsayan EN YÜKSEK öncelikli aktif politikayı döner."""
    covering = [p for p in policies
                if p.get("is_active", True)
                and match_parcel(parcel, _policy_filters(p), (p.get("filter") or {}).get("logic", "AND"))]
    if not covering:
        return None
    return sorted(covering, key=lambda p: p.get("priority", 0), reverse=True)[0]


async def find_uncovered_parcels(db) -> List[dict]:
    """"Politikasız Parseller" — hiçbir aktif politikanın kapsamadığı parseller."""
    policies = await db.remote_sensing_policies.find({"is_active": True}, {"_id": 0}).to_list(500)
    uncovered = []
    async for parcel in db.parcels.find({}, {"_id": 0}):
        if not await resolve_covering_policy(db, parcel, policies):
            uncovered.append({"id": parcel.get("id"), "parcel_code": parcel.get("parcel_code"),
                              "name": parcel.get("name")})
    return uncovered


def _is_due(parcel: dict, frequency: str) -> bool:
    days = FREQUENCY_DAYS.get(ScanFrequency(frequency) if frequency in ScanFrequency._value2member_map_ else None)
    if days is None:
        return False   # manuel_only → otomatik taranmaz
    rs = parcel.get("remote_sensing") or {}
    last = rs.get("last_analysis_date")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True
    return datetime.now(timezone.utc) - last_dt >= timedelta(days=days)


async def run_scheduler_tick(db, provider_factory) -> Dict:
    """Bir tarama turu: kapsayan politikaya göre vadesi gelen parseller için
    task kuyruğa yığılır (batch), sonra ardışık işlenir (Performans bölümü:
    "tek scheduler tick'inde kuyruğa yığılır, ardışık işlenir")."""
    policies = await db.remote_sensing_policies.find({"is_active": True}, {"_id": 0}).to_list(500)
    enqueued = 0
    async for parcel in db.parcels.find({}, {"_id": 0}):
        policy = await resolve_covering_policy(db, parcel, policies)
        if not policy:
            continue
        if policy.get("frequency") == ScanFrequency.MANUEL_ONLY.value:
            continue
        if not _is_due(parcel, policy.get("frequency", "haftada_bir")):
            continue
        await create_task(db, parcel_id=parcel["id"], task_type="statistics",
                          indices=policy.get("indices", ["ndvi"]),
                          trigger="scheduled", priority=policy.get("priority", 0))
        enqueued += 1
    result = await process_pending_tasks(db, provider_factory)
    uncovered = await find_uncovered_parcels(db)
    return {"enqueued": enqueued, "processed": result["processed"],
            "uncovered_count": len(uncovered)}
