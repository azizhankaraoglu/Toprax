#!/usr/bin/env python3
"""migration_runner.py -- PR-04 CLI girisi.

Kullanim:
    python migration_runner.py status
    python migration_runner.py migrate
    python migration_runner.py rollback <hedef_surum>

Docker icinde:
    docker-compose run --rm backend python migration_runner.py migrate

Bu script config_service.py uzerinden MONGO_URL/DB_NAME okur (server.py ile
ayni kaynak), yani .env doldurulmus olmali.
"""
import asyncio
import json
import sys

from motor.motor_asyncio import AsyncIOMotorClient

from config_service import MONGO_URL, DB_NAME
import migrations_engine as engine


async def _main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("status", "migrate", "rollback"):
        print(__doc__)
        return 1

    client = AsyncIOMotorClient(MONGO_URL)
    raw_db = client[DB_NAME]

    cmd = sys.argv[1]
    if cmd == "status":
        result = await engine.get_status(raw_db)
    elif cmd == "migrate":
        result = await engine.migrate(raw_db)
    else:  # rollback
        if len(sys.argv) < 3 or not sys.argv[2].isdigit():
            print("Kullanim: python migration_runner.py rollback <hedef_surum>")
            return 1
        result = await engine.rollback_to(raw_db, int(sys.argv[2]))

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("status", "ok") == "ok" else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
