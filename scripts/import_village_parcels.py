#!/usr/bin/env python3
"""scripts/import_village_parcels.py -- OTURUM-DEVAM köy verisi yükleme
(2026-08-20 kullanıcı isteği).

4 köyün (Gökhüyük, Kuzucu, Üçhüyük, Dinlendik) gerçek parsel sınırı
GeoJSON dosyalarını GERÇEK REST API'ye (`POST /parcels/import-geojson`)
HTTP isteğiyle yükler -- `scripts/demo_scenario.py` ile AYNI çalışma
şekli (server'a import edilmez, canlı veriye yazma HER ZAMAN elle
tetiklenir, Karar Protokolü).

Kaynak dosyalar: FeatureCollection, geometri tipi LineString (Polygon
DEĞİL, backend'in 2026-08-20'de eklenen `_close_linestring_to_polygon`
kapatıcısı bunu otomatik çözer), tek özellik `Name` = "101/10" (ada/
parsel formatı -- backend'in `_extract_tkgm_fields`'i bunu ada_no/
parsel_no_tapu'ya otomatik ayrıştırır, AYNI 2026-08-20 düzeltmesi).

Kullanıcı kararları (bu script bunlara göre yazıldı):
  - Çiftçi ataması: mevcut çiftçilere ROUND-ROBIN dağıtılır (Abditolu
    emsaliyle aynı -- "Abditolu gibi otomatik çiftçi dağıt").
  - "101/10" -> ada_no=101, parsel_no_tapu=10 (backend'de düzeltildi).

Kullanım:
    python scripts/import_village_parcels.py \\
        --base-url http://localhost:8001/api \\
        --email <tenant-admin-email> --password <şifre> \\
        --geojson-dir "C:\\Users\\Azizhan\\Desktop\\koyler\\tamamı"

    --dry-run ile hiçbir şey yazmadan sadece kaç parsel/hangi köy
    bulunduğunu ve round-robin dağılımını gösterir.

Dosya adı -> köy adı eşlemesi VILLAGE_FILES sabitinde. Aynı isimde bir
parsel (village+name eşleşmesi) zaten varsa ATLANIR (idempotent --
script'i tekrar çalıştırmak, kısmi bir önceki denemeyi tamamlar).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

VILLAGE_FILES = {
    "Gökhüyük": "GÖKHÜYÜK_PARSEL_ALN.geojson",
    "Kuzucu": "KUZUCU_PARSEL_ALN.geojson",
    "Üçhüyük": "ÜÇHÜYÜK_PARSEL_ALN.geojson",
    "Dinlendik": "DINLENDIK_PARSEL_ALN.geojson",
}

# Bir seferde göndermek yerine parça parça -- büyük dosyalarda (KUZUCU
# ~1900 feature) tek istekte hem sunucu tarafı hem ağ zaman aşımı riskini
# azaltır, ayrıca kısmi bir hata TÜM köyü değil sadece o parçayı etkiler.
CHUNK_SIZE = 200


def _client(base_url: str, email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{base_url}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s


def _load_geojson(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _existing_parcel_keys(s: requests.Session, base_url: str, village: str) -> set:
    """İdempotentlik için: bu köyde zaten var olan (village, name) çiftlerini
    döner -- script tekrar çalıştırıldığında aynı parseli iki kez oluşturmaz."""
    r = s.get(f"{base_url}/parcels", params={"limit": 5000}, timeout=30)
    r.raise_for_status()
    return {p.get("name") for p in r.json() if p.get("village") == village}


def import_village(s: requests.Session, base_url: str, village: str, path: Path,
                    farmers: list, farmer_cursor: list, dry_run: bool) -> dict:
    gj = _load_geojson(path)
    features = gj.get("features", [])
    existing_names = set() if dry_run else _existing_parcel_keys(s, base_url, village)

    to_send = []
    skipped_existing = 0
    for feat in features:
        props = feat.get("properties") or {}
        raw_name = props.get("Name") or props.get("name") or ""
        display_name = f"{village} {raw_name}".strip() if raw_name else village
        if display_name in existing_names:
            skipped_existing += 1
            continue
        farmer = farmers[farmer_cursor[0] % len(farmers)] if farmers else None
        farmer_cursor[0] += 1
        new_props = {**props, "village": village, "name": display_name}
        if farmer:
            new_props["farmer_id"] = farmer["id"]
        to_send.append({"type": "Feature", "geometry": feat.get("geometry"), "properties": new_props})

    print(f"[{village}] kaynakta {len(features)} feature, {skipped_existing} zaten var, "
          f"{len(to_send)} gönderilecek")

    if dry_run or not to_send:
        return {"village": village, "sent": 0, "created": 0, "errors": 0, "dry_run": dry_run}

    created_total, error_total = 0, 0
    for i in range(0, len(to_send), CHUNK_SIZE):
        chunk = to_send[i:i + CHUNK_SIZE]
        body = {
            "geojson": {"type": "FeatureCollection", "features": chunk},
            "default_soil_type": "Tınlı",
            "default_irrigation": "Damla",
        }
        r = s.post(f"{base_url}/parcels/import-geojson", json=body, timeout=120)
        r.raise_for_status()
        data = r.json()
        created_total += data.get("created_count", 0)
        error_total += data.get("error_count", 0)
        print(f"  parça {i // CHUNK_SIZE + 1}: {data.get('created_count')} oluşturuldu, "
              f"{data.get('error_count')} hata")
        if data.get("errors"):
            for e in data["errors"][:5]:
                print(f"    - {e}")

    return {"village": village, "sent": len(to_send), "created": created_total, "errors": error_total}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=os.environ.get("TOPRAX_BASE_URL", "http://localhost:8001/api"))
    ap.add_argument("--email", default=os.environ.get("TOPRAX_ADMIN_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("TOPRAX_ADMIN_PASSWORD"))
    ap.add_argument("--geojson-dir", required=True, help=r'ör. "C:\Users\Azizhan\Desktop\koyler\tamamı"')
    ap.add_argument("--villages", nargs="*", default=list(VILLAGE_FILES.keys()),
                     help="Sadece belirli köyleri yükle (varsayılan: hepsi)")
    ap.add_argument("--dry-run", action="store_true", help="Hiçbir şey yazma, sadece say")
    args = ap.parse_args()

    if not args.dry_run and (not args.email or not args.password):
        print("Hata: --email/--password (veya TOPRAX_ADMIN_EMAIL/TOPRAX_ADMIN_PASSWORD) gerekli "
              "(--dry-run hariç).", file=sys.stderr)
        sys.exit(1)

    geojson_dir = Path(args.geojson_dir)
    s = None
    farmers = []
    if not args.dry_run:
        s = _client(args.base_url, args.email, args.password)
        r = s.get(f"{args.base_url}/farmers", params={"limit": 2000}, timeout=30)
        r.raise_for_status()
        farmers = r.json()
        print(f"{len(farmers)} çiftçi bulundu -- round-robin dağıtım için kullanılacak")
        if not farmers:
            print("UYARI: hiç çiftçi yok -- parseller 'atanmamış' olarak eklenecek.")

    farmer_cursor = [0]
    results = []
    for village in args.villages:
        filename = VILLAGE_FILES.get(village)
        if not filename:
            print(f"UYARI: bilinmeyen köy '{village}', atlanıyor.", file=sys.stderr)
            continue
        path = geojson_dir / filename
        if not path.exists():
            print(f"UYARI: dosya bulunamadı: {path}", file=sys.stderr)
            continue
        results.append(import_village(s, args.base_url, village, path, farmers, farmer_cursor, args.dry_run))

    print("\n--- ÖZET ---")
    for r in results:
        print(r)


if __name__ == "__main__":
    main()
