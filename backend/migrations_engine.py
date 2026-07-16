"""migrations_engine.py -- PR-04: Migration Runner + Surum Yukseltme/Geri Alma
Mekanizmasi.

MongoDB semasiz oldugu icin "migration" burada index olusturma, veri
donusumu, varsayilan alan ekleme gibi islemler anlamina gelir. Her
migration `backend/migrations/versions/NNNN_aciklama.py` dosyasidir ve
iki async fonksiyon tanimlar:

    async def up(db) -> None      # zorunlu -- migration'i uygular
    async def down(db) -> None    # opsiyonel -- migration'i geri alir

`db` burada HER ZAMAN raw_db'dir (tenant filtresi yok) -- migration'lar
sema/index seviyesinde calisir.

Uygulanan migration'lar db.schema_migrations koleksiyonunda tutulur; surum
numarasi dosya adinin basindaki NNNN'den gelir (0001, 0002, ...).

Kullanim (CLI): `python migration_runner.py status|migrate|rollback <version>`
Kullanim (API): register_migration_routes(...) -- /api/migrations/*
"""
import importlib
import logging
import pkgutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("toprax.migrations")

VERSIONS_PACKAGE = "migrations.versions"
VERSIONS_DIR = Path(__file__).parent / "migrations" / "versions"


def _discover_migrations() -> List[dict]:
    if not VERSIONS_DIR.exists():
        return []
    found = []
    for _, name, _ in pkgutil.iter_modules([str(VERSIONS_DIR)]):
        if "_" not in name:
            continue
        prefix = name.split("_", 1)[0]
        if not prefix.isdigit():
            continue
        module = importlib.import_module(f"{VERSIONS_PACKAGE}.{name}")
        found.append({
            "version": int(prefix),
            "name": name,
            "description": getattr(module, "DESCRIPTION", name),
            "module": module,
        })
    found.sort(key=lambda m: m["version"])
    return found


async def get_applied_versions(db) -> List[int]:
    cursor = db.schema_migrations.find({}, {"_id": 0, "version": 1})
    return sorted([doc["version"] async for doc in cursor])


async def get_current_version(db) -> int:
    applied = await get_applied_versions(db)
    return applied[-1] if applied else 0


async def get_status(db) -> dict:
    all_migrations = _discover_migrations()
    applied = set(await get_applied_versions(db))
    pending = [m for m in all_migrations if m["version"] not in applied]
    return {
        "current_version": max(applied) if applied else 0,
        "latest_available_version": all_migrations[-1]["version"] if all_migrations else 0,
        "applied_count": len(applied),
        "pending_count": len(pending),
        "pending": [{"version": m["version"], "name": m["name"], "description": m["description"]} for m in pending],
    }


async def migrate(db, target_version: Optional[int] = None) -> dict:
    """Bekleyen migration'lari surum sirasina gore uygular.

    Bir migration sirasinda hata olursa: o migration'in (varsa) down()'i
    OTOMATIK cagirilir, calisma durdurulur, bu migration schema_migrations'a
    yazilmaz (yani DB son basarili surumde kalir) -- PR-04 kabul kriteri
    ("kasitli bozulan migration'da sistem otomatik eski surume donuyor").
    """
    all_migrations = _discover_migrations()
    applied = set(await get_applied_versions(db))
    to_run = [m for m in all_migrations
              if m["version"] not in applied and (target_version is None or m["version"] <= target_version)]

    ran = []
    for m in to_run:
        logger.info("Migration uygulaniyor: %s (v%s)", m["name"], m["version"])
        try:
            await m["module"].up(db)
        except Exception as exc:  # noqa: BLE001
            logger.error("Migration basarisiz: %s -- %s", m["name"], exc)
            down_fn = getattr(m["module"], "down", None)
            rolled_back = False
            if down_fn:
                try:
                    await down_fn(db)
                    rolled_back = True
                    logger.warning("Migration %s icin otomatik rollback (down()) calistirildi.", m["name"])
                except Exception as rollback_exc:  # noqa: BLE001
                    logger.critical(
                        "Rollback da basarisiz oldu (%s): %s -- veritabani tutarsiz olabilir, ELLE MUDAHALE GEREKLI.",
                        m["name"], rollback_exc,
                    )
            return {
                "status": "failed",
                "failed_migration": m["name"],
                "error": str(exc),
                "applied_this_run": ran,
                "rolled_back": rolled_back,
                "current_version": await get_current_version(db),
            }
        await db.schema_migrations.insert_one({
            "version": m["version"],
            "name": m["name"],
            "description": m["description"],
            "applied_at": datetime.now(timezone.utc).isoformat(),
        })
        ran.append(m["name"])

    return {"status": "ok", "applied_this_run": ran, "current_version": await get_current_version(db)}


async def rollback_to(db, target_version: int) -> dict:
    """Uygulanmis migration'lari en yeniden en eskiye dogru, target_version'a
    inene kadar down() cagirarak geri alir. down() tanimsizsa durur (elle
    mudahale gerektigini bildirir) -- rastgele veri kaybina yol acmaz."""
    all_migrations = {m["version"]: m for m in _discover_migrations()}
    applied = sorted(await get_applied_versions(db), reverse=True)
    rolled_back = []
    for version in applied:
        if version <= target_version:
            break
        m = all_migrations.get(version)
        if not m:
            return {"status": "failed", "error": f"v{version} icin migration dosyasi bulunamadi, elle mudahale gerekli.",
                     "rolled_back": rolled_back}
        down_fn = getattr(m["module"], "down", None)
        if not down_fn:
            return {"status": "failed",
                     "error": f"v{version} ({m['name']}) icin down() tanimli degil, otomatik rollback yapilamiyor.",
                     "rolled_back": rolled_back}
        await down_fn(db)
        await db.schema_migrations.delete_one({"version": version})
        rolled_back.append(m["name"])
    return {"status": "ok", "rolled_back": rolled_back, "current_version": await get_current_version(db)}


def register_migration_routes(api_router, raw_db, require_permission, log_audit):
    """server.py'den cagrilir. `raw_db` -- tenant filtresiz ham DB handle."""
    from fastapi import Depends, Request

    @api_router.get("/migrations/status")
    async def migrations_status(user=Depends(require_permission("platform_core:view"))):
        return await get_status(raw_db)

    @api_router.post("/migrations/run")
    async def migrations_run(request: Request, user=Depends(require_permission("platform_core:manage"))):
        result = await migrate(raw_db)
        await log_audit(raw_db, user, action="run", entity="schema_migration", entity_id="migrate",
                         new_value=result, request=request)
        return result

    @api_router.post("/migrations/rollback/{target_version}")
    async def migrations_rollback(target_version: int, request: Request,
                                   user=Depends(require_permission("platform_core:manage"))):
        result = await rollback_to(raw_db, target_version)
        await log_audit(raw_db, user, action="rollback", entity="schema_migration", entity_id=str(target_version),
                         new_value=result, request=request)
        return result
