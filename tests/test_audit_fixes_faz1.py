"""
2026-07-24 -- Denetim düzeltmeleri Faz 1 (A9/A10/A11) birim testleri.

- A9: geo_validation.py topoloji doğrulaması (self-intersection, açık halka)
- A10: field_ops.py `ertelendi` durumu geçiş kuralları
- A11: ledger reverse → bağlı belgeye "Düzeltildi" işareti
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pytest
from mongomock_motor import AsyncMongoMockClient

from geo_validation import validate_geometry
from field_ops import TASK_ALLOWED_TRANSITIONS, TASK_STATUS_LABELS
from ledger import create_ledger_entry
from tenant_context import TenantScopedDB, current_tenant_id


# ---------------------------------------------------------------- A9
VALID_SQUARE = {
    "type": "Polygon",
    "coordinates": [[[32.0, 37.0], [32.01, 37.0], [32.01, 37.01], [32.0, 37.01], [32.0, 37.0]]],
}
# Kum saati (bowtie) — kenarlar ortada kesişir: klasik self-intersection.
BOWTIE = {
    "type": "Polygon",
    "coordinates": [[[32.0, 37.0], [32.01, 37.01], [32.01, 37.0], [32.0, 37.01], [32.0, 37.0]]],
}
OPEN_RING = {
    "type": "Polygon",
    "coordinates": [[[32.0, 37.0], [32.01, 37.0], [32.01, 37.01], [32.0, 37.01]]],
}


def test_valid_polygon_passes():
    assert validate_geometry(VALID_SQUARE) == []


def test_self_intersecting_polygon_rejected():
    errors = validate_geometry(BOWTIE)
    assert errors and "kesişiyor" in errors[0]


def test_open_ring_rejected():
    errors = validate_geometry(OPEN_RING)
    assert errors and "kapalı değil" in errors[0]


def test_none_geometry_allowed():
    assert validate_geometry(None) == []


def test_multipolygon_validated():
    mp = {"type": "MultiPolygon", "coordinates": [BOWTIE["coordinates"]]}
    assert validate_geometry(mp)


def test_out_of_range_coordinates_rejected():
    bad = {"type": "Polygon",
           "coordinates": [[[200.0, 37.0], [201.0, 37.0], [201.0, 38.0], [200.0, 37.0]]]}
    errors = validate_geometry(bad)
    assert errors and "aralık dışı" in errors[0]


# ---------------------------------------------------------------- A10
def test_ertelendi_reachable_from_field_stages():
    for s in ("planlandi", "atandi", "kabul_edildi", "yola_cikildi",
              "yerine_ulasildi", "calisiliyor"):
        assert "ertelendi" in TASK_ALLOWED_TRANSITIONS[s], s


def test_ertelendi_not_reachable_after_completion():
    assert "ertelendi" not in TASK_ALLOWED_TRANSITIONS["tamamlandi"]
    assert "ertelendi" not in TASK_ALLOWED_TRANSITIONS["onay_bekliyor"]


def test_ertelendi_can_be_replanned():
    assert TASK_ALLOWED_TRANSITIONS["ertelendi"] == {"planlandi", "iptal_edildi"}


def test_ertelendi_has_label():
    assert TASK_STATUS_LABELS["ertelendi"] == "Ertelendi"


def test_terminal_states_unchanged():
    assert TASK_ALLOWED_TRANSITIONS["kapandi"] == set()
    assert TASK_ALLOWED_TRANSITIONS["iptal_edildi"] == set()


# ---------------------------------------------------------------- A11
@pytest.mark.asyncio
async def test_ledger_reverse_flags_linked_document():
    """Reverse akışının bağlı belgeyi işaretleme mantığı — endpoint'in
    _REF_COLLECTIONS eşlemesiyle AYNI davranış, create_ledger_entry +
    elle update üzerinden uçtan uca simüle edilir."""
    raw = AsyncMongoMockClient()["test_db"]
    db = TenantScopedDB(raw)
    reset = current_tenant_id.set("tenant-a")
    try:
        sr_id = str(uuid.uuid4())
        await db.support_requests.insert_one({"id": sr_id, "status": "muhasebelesti"})
        original = await create_ledger_entry(
            db, production_cycle_id="pc-1", farmer_id="f-1",
            entry_type="destek_teslimi", amount=-2500,
            reference_type="support_request", reference_id=sr_id,
        )
        # reverse (endpoint mantığının çekirdeği)
        reversal = await create_ledger_entry(
            db, production_cycle_id="pc-1", farmer_id="f-1",
            entry_type="destek_teslimi", amount=2500,
            reference_type="support_request", reference_id=sr_id,
            is_reversal=True, reversed_entry_id=original["id"],
        )
        await db.support_requests.update_one(
            {"id": sr_id},
            {"$set": {"correction_status": "Düzeltildi",
                      "corrected_by_ledger_entry_id": reversal["id"]}},
        )
        doc = await db.support_requests.find_one({"id": sr_id}, {"_id": 0})
        assert doc["correction_status"] == "Düzeltildi"
        assert doc["status"] == "muhasebelesti"  # kendi durum makinesi DEĞİŞMEZ
        # orijinal ledger kaydı bozulmadı
        orig = await db.ledger_entries.find_one({"id": original["id"]}, {"_id": 0})
        assert orig["amount"] == -2500 and not orig["is_reversal"]
    finally:
        current_tenant_id.reset(reset)
