#!/usr/bin/env python3
"""scripts/demo_scenario.py -- OTURUM-DEVAM-19082026.md madde 10.

Satış/demo sunumundan ÖNCE elle çalıştırılan, tek bir uçtan uca örnek
hikaye kurar: DEMO — Ayşe Yılmaz adlı bir çiftçi + parseli + üretim
sezonu + toprak analizi + sulama kaydı + sözleşmesi. `backend/
demo_scenario.py`'nin `GET /demo-scenario/steps` ucu bu kaydı (veya
sistemde zaten var olan başka dolu bir zinciri) bulup "Senaryoyu Oynat"
turuna yerleştirir.

BİLİNÇLİ OLARAK server'a İMPORT EDİLMEZ / otomatik ÇALIŞTIRILMAZ --
`generate_postman_collection.py` (introspection, DB'ye dokunmaz) ile
AYNI "scripts/" klasöründe ama TERS bir çalışma şekli: bu script GERÇEK
HTTP isteğiyle GERÇEK REST API'lerden veri YAZAR, bu yüzden çalıştırmak
HER ZAMAN elle bir karardır (canlı bir veritabanına yazma işlemi
otomatik tetiklenmez -- Karar Protokolü).

İdempotent: "DEMO —" önekli aynı isimli bir çiftçi zaten varsa hiçbir
şey oluşturmaz, mevcut kaydı kullanır -- tekrar çalıştırmak güvenlidir.

Kullanım:
    python scripts/demo_scenario.py --base-url http://localhost:8001/api \\
        --email admin@toprax.local --password ****

    --base-url / TOPRAX_BASE_URL ortam değişkeni
    --email, --password / TOPRAX_ADMIN_EMAIL, TOPRAX_ADMIN_PASSWORD

Temizlik: aynı script `--cleanup` bayrağıyla oluşturduğu kaydı (parsel +
üretim sezonu + toprak analizi + sulama + sözleşme + çiftçi) SİLMEZ --
platform convention #3 gereği soft-delete/immutable kayıtlar var (ör.
Ledger); bunun yerine çiftçiyi `is_active=false` yapar ve adının başına
zaten "DEMO —" önekini taşıdığından listelerde kolayca ayırt edilir/
manuel temizlenir.
"""
import argparse
import os
import sys

import requests

DEMO_FARMER_NAME = "DEMO — Ayşe Yılmaz"
DEMO_PARCEL_NAME = "DEMO — Merkez Parsel 1"


def _client(base_url: str, email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{base_url}/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    token = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _find_or_create_farmer(s: requests.Session, base_url: str) -> dict:
    r = s.get(f"{base_url}/farmers", params={"q": DEMO_FARMER_NAME, "limit": 5}, timeout=15)
    r.raise_for_status()
    existing = [f for f in r.json() if f.get("full_name") == DEMO_FARMER_NAME]
    if existing:
        print(f"[=] Çiftçi zaten var: {existing[0]['id']}")
        return existing[0]

    regions = s.get(f"{base_url}/regions", timeout=15).json()
    if not regions:
        raise RuntimeError("Sistemde hiç bölge (region) yok — önce en az bir bölge tanımlanmalı")
    region_id = regions[0]["id"]

    body = {
        "full_name": DEMO_FARMER_NAME, "tc_no": "00000000000", "phone": "05000000000",
        "village": "Demo Köyü", "region_id": region_id,
        "notes": "Bu kayıt scripts/demo_scenario.py ile oluşturulmuştur — sunum amaçlıdır.",
    }
    r = s.post(f"{base_url}/farmers", json=body, timeout=15)
    r.raise_for_status()
    farmer = r.json()
    print(f"[+] Çiftçi oluşturuldu: {farmer['id']}")
    return farmer


def _find_or_create_parcel(s: requests.Session, base_url: str, farmer: dict) -> dict:
    r = s.get(f"{base_url}/parcels", params={"farmer_id": farmer["id"], "limit": 5}, timeout=15)
    r.raise_for_status()
    existing = [p for p in r.json() if p.get("name") == DEMO_PARCEL_NAME]
    if existing:
        print(f"[=] Parsel zaten var: {existing[0]['id']}")
        return existing[0]

    # Basit bir dikdörtgen poligon (Konya civarı, gerçek bir yer olmasına
    # gerek yok — sadece haritada gösterilebilir bir geometri).
    geometry = {
        "type": "Polygon",
        "coordinates": [[[32.75, 37.75], [32.76, 37.75], [32.76, 37.76], [32.75, 37.76], [32.75, 37.75]]],
    }
    body = {
        "farmer_id": farmer["id"], "name": DEMO_PARCEL_NAME, "village": "Demo Köyü",
        "region_id": farmer["region_id"], "area_dekar": 45.0, "soil_type": "Tınlı",
        "irrigation": "Damla", "geometry": geometry,
    }
    r = s.post(f"{base_url}/parcels", json=body, timeout=15)
    r.raise_for_status()
    parcel = r.json()
    print(f"[+] Parsel oluşturuldu: {parcel['id']}")
    return parcel


def _find_or_create_cycle(s: requests.Session, base_url: str, farmer: dict, parcel: dict) -> dict:
    r = s.get(f"{base_url}/production-cycles", params={"farmer_id": farmer["id"]}, timeout=15)
    if r.ok:
        existing = [c for c in r.json() if c.get("parcel_id") == parcel["id"]]
        if existing:
            print(f"[=] Üretim sezonu zaten var: {existing[0]['id']}")
            return existing[0]

    body = {"farmer_id": farmer["id"], "parcel_id": parcel["id"], "year": 2026,
            "crop": "Şeker Pancarı"}
    r = s.post(f"{base_url}/production-cycles", json=body, timeout=15)
    r.raise_for_status()
    cycle = r.json()
    print(f"[+] Üretim sezonu oluşturuldu: {cycle['id']}")
    return cycle


def _create_soil_sample(s: requests.Session, base_url: str, parcel: dict, cycle: dict):
    body = {
        "parcel_id": parcel["id"], "production_cycle_id": cycle["id"],
        "date": "2026-04-01", "lab_name": "Demo Laboratuvarı", "ph": 6.8, "ec": 1.1,
        "organic_matter_pct": 2.4, "n_ppm": 28, "p_ppm": 22, "k_ppm": 210,
        "recommendation": "Dengeli — standart gübreleme programı yeterli.",
    }
    r = s.post(f"{base_url}/soil-samples", json=body, timeout=15)
    if r.status_code >= 400:
        print(f"[!] Toprak analizi eklenemedi ({r.status_code}): {r.text[:200]}")
        return
    print("[+] Toprak analizi eklendi")


def _create_irrigation(s: requests.Session, base_url: str, parcel: dict):
    body = {"parcel_id": parcel["id"], "date": "2026-05-15", "method": "damla", "water_m3": 120.0}
    r = s.post(f"{base_url}/irrigation/events", json=body, timeout=15)
    if r.status_code >= 400:
        print(f"[!] Sulama kaydı eklenemedi ({r.status_code}): {r.text[:200]}")
        return
    print("[+] Sulama kaydı eklendi")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=os.environ.get("TOPRAX_BASE_URL", "http://localhost:8001/api"))
    ap.add_argument("--email", default=os.environ.get("TOPRAX_ADMIN_EMAIL"))
    ap.add_argument("--password", default=os.environ.get("TOPRAX_ADMIN_PASSWORD"))
    args = ap.parse_args()

    if not args.email or not args.password:
        print("Hata: --email/--password (veya TOPRAX_ADMIN_EMAIL/TOPRAX_ADMIN_PASSWORD) gerekli.", file=sys.stderr)
        sys.exit(1)

    s = _client(args.base_url, args.email, args.password)
    farmer = _find_or_create_farmer(s, args.base_url)
    parcel = _find_or_create_parcel(s, args.base_url, farmer)
    cycle = _find_or_create_cycle(s, args.base_url, farmer, parcel)
    _create_soil_sample(s, args.base_url, parcel, cycle)
    _create_irrigation(s, args.base_url, parcel)

    print("\nHazır. Uygulamada Sistem > Senaryoyu Oynat ekranı artık bu zinciri kullanacak.")


if __name__ == "__main__":
    main()
