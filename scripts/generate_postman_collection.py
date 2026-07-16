#!/usr/bin/env python3
"""generate_postman_collection.py -- PR-25: OpenAPI'den Otomatik Postman
Collection Uretimi.

Elle yazilmaz -- FastAPI'nin kendi introspection'indan (app.openapi(), HIC
bir DB baglantisi/HTTP sunucusu GEREKTIRMEZ) otomatik uretilir. Her modul
(path'in /api/ sonrasi ilk segmenti) bir Postman "folder"i olur -- Query
Engine modul listesiyle (query_engine.py MODULE_COLLECTIONS) hizalidir.

Kullanim:
    cd backend && python ../scripts/generate_postman_collection.py

Cikti:
    postman/toprax.postman_collection.json
    postman/toprax.postman_environment.json

Insomnia notu: Insomnia, Postman v2.1 collection'larini DOGRUDAN import
edebiliyor (File > Import > "From Postman") -- bu yuzden ayri bir Insomnia
formati elle bakimi gereken kod olarak TUTULMAZ, ayni dosya iki arac
icin de kullanilir (PR-25 "elle guncelleme yuku sifir" prensibiyle tutarli).

CI entegrasyonu: bu script her deploy sonrasi (PR-10 CI/CD pipeline'inin
bir adimi olarak) yeniden calistirilip postman/ altindaki dosyalar
Gelistirici Portali'na (PR-26) yeniden yayinlanir -- elle dokunulmaz.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import os
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "toprax_postman_gen")
os.environ.setdefault("JWT_SECRET", "postman-gen-only-not-a-real-secret")
os.environ.setdefault("PLATFORM_ADMIN_EMAIL", "gen@local")
os.environ.setdefault("PLATFORM_ADMIN_PASSWORD", "gen-placeholder-pass")

import server  # noqa: E402  -- import SADECE introspection icin, DB'ye gercekten baglanmaz

OUT_DIR = Path(__file__).resolve().parent.parent / "postman"


def _example_for_schema(schema: dict, components: dict, depth=0) -> object:
    """Bir OpenAPI sema parcasindan orneklenebilir bir govde uretir --
    'example'/'default' varsa onu kullanir, yoksa tipe gore basit bir
    placeholder uretir (string -> 'string', integer -> 0 vb.)."""
    if depth > 4:
        return None
    if not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        resolved = components.get(ref_name, {})
        return _example_for_schema(resolved, components, depth + 1)
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        result = {}
        for prop_name, prop_schema in (schema.get("properties") or {}).items():
            result[prop_name] = _example_for_schema(prop_schema, components, depth + 1)
        return result
    if schema_type == "array":
        item_example = _example_for_schema(schema.get("items", {}), components, depth + 1)
        return [item_example] if item_example is not None else []
    if schema_type == "string":
        return schema.get("enum", ["string"])[0]
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0.0
    if schema_type == "boolean":
        return True
    return None


def _postman_url(path: str) -> dict:
    # FastAPI: /api/farmers/{farmer_id} -> Postman: {{base_url}}/api/farmers/:farmer_id
    postman_path = re.sub(r"\{(\w+)\}", r":\1", path)
    path_variables = re.findall(r"\{(\w+)\}", path)
    segments = [s for s in postman_path.split("/") if s]
    return {
        "raw": "{{base_url}}" + postman_path,
        "host": ["{{base_url}}"],
        "path": segments,
        "variable": [{"key": v, "value": ""} for v in path_variables],
    }


def build_collection() -> dict:
    schema = server.app.openapi()
    components = (schema.get("components", {}) or {}).get("schemas", {})
    paths = schema.get("paths", {})

    folders = {}  # module_name -> list of Postman item dicts

    for path, methods in paths.items():
        if not path.startswith("/api/"):
            continue
        if path.startswith("/api/v1/"):
            continue  # /api/v1 zaten /api'nin zarflanmis hali, ayrica listelenmez
        rest = path[len("/api/"):]
        module = (rest.split("/")[0] or "genel").replace("-", "_") or "genel"

        for method, operation in methods.items():
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue

            body_example = None
            request_body = operation.get("requestBody", {})
            content = request_body.get("content", {})
            json_content = content.get("application/json", {})
            if json_content.get("schema"):
                body_example = _example_for_schema(json_content["schema"], components)

            item = {
                "name": operation.get("summary") or f"{method.upper()} {path}",
                "request": {
                    "method": method.upper(),
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "url": _postman_url(path),
                    "description": (operation.get("description") or "").strip()[:500],
                },
            }
            if body_example is not None:
                item["request"]["body"] = {
                    "mode": "raw",
                    "raw": json.dumps(body_example, ensure_ascii=False, indent=2),
                    "options": {"raw": {"language": "json"}},
                }
            folders.setdefault(module, []).append(item)

    collection = {
        "info": {
            "name": "Toprax API",
            "description": "OpenAPI semasindan OTOMATIK uretildi -- elle DUZENLEMEYIN, "
                            "scripts/generate_postman_collection.py'yi tekrar calistirin.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{bearer_token}}", "type": "string"}],
        },
        "event": [
            {
                "listen": "prerequest",
                "script": {
                    "type": "text/javascript",
                    "exec": [
                        "// PR-24: eger {{api_key}} ortam degiskeni doluysa, bearer_token yerine",
                        "// API key'i kullan (M2M senaryosu -- kullanici login JWT'sine gerek yok).",
                        "const apiKey = pm.environment.get('api_key');",
                        "if (apiKey) { pm.environment.set('bearer_token', apiKey); }",
                    ],
                },
            }
        ],
        "item": [
            {"name": module, "item": items}
            for module, items in sorted(folders.items())
        ],
    }
    return collection


def build_environment() -> dict:
    return {
        "name": "Toprax - Yerel",
        "values": [
            {"key": "base_url", "value": "http://localhost:8001", "enabled": True},
            {"key": "bearer_token", "value": "", "enabled": True,
             "description": "POST /api/auth/login yanitindaki 'token' alani"},
            {"key": "api_key", "value": "", "enabled": True,
             "description": "Opsiyonel -- PR-24 API key (toprax_key_...). Doluysa bearer_token yerine kullanilir."},
        ],
    }


def main():
    OUT_DIR.mkdir(exist_ok=True)
    collection = build_collection()
    environment = build_environment()

    coll_path = OUT_DIR / "toprax.postman_collection.json"
    env_path = OUT_DIR / "toprax.postman_environment.json"

    coll_path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    env_path.write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")

    total_requests = sum(len(f["item"]) for f in collection["item"])
    print(f"Uretildi: {coll_path} ({len(collection['item'])} klasor, {total_requests} istek)")
    print(f"Uretildi: {env_path}")


if __name__ == "__main__":
    main()
