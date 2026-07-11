"""
IT-20 — Hakediş Motoru saf fonksiyon testleri (API/DB'den bağımsız).
Kabul kriteri: "hesaplama formülü unit test edilebilir saf fonksiyon
olarak yazılmalı" — bu dosya o iddiayı doğrular.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from entitlement import (
    calculate_gross_entitlement,
    calculate_entitlement_chain,
    resolve_definition_amount,
)


def test_gross_entitlement_within_quota():
    result = calculate_gross_entitlement({"B": 100.0}, kota_ton=150.0, unit_price=25.0)
    assert result["total_tonnage"] == 100.0
    assert result["tonnage_within_quota"] == 100.0
    assert result["quality_coefficient"] == 1.0
    assert result["gross_entitlement"] == 2500.0


def test_gross_entitlement_caps_at_quota():
    # Kotanın üzerindeki tonaj ödenmez — sadece kota kadarı hesaba katılır.
    result = calculate_gross_entitlement({"B": 200.0}, kota_ton=150.0, unit_price=25.0)
    assert result["tonnage_within_quota"] == 150.0
    assert result["gross_entitlement"] == 150.0 * 25.0


def test_gross_entitlement_no_quota_uses_total_tonnage():
    result = calculate_gross_entitlement({"A": 50.0}, kota_ton=None, unit_price=10.0)
    assert result["tonnage_within_quota"] == 50.0
    assert result["gross_entitlement"] == 50.0 * 10.0 * 1.05  # A kalitesi katsayısı


def test_gross_entitlement_weighted_quality_coefficient():
    # 50 ton A (1.05) + 50 ton C (0.9) -> ağırlıklı ortalama katsayı = 0.975
    result = calculate_gross_entitlement({"A": 50.0, "C": 50.0}, kota_ton=None, unit_price=10.0)
    assert result["quality_coefficient"] == 0.975
    assert result["gross_entitlement"] == round(100.0 * 10.0 * 0.975, 2)


def test_gross_entitlement_empty_tonnage():
    result = calculate_gross_entitlement({}, kota_ton=100.0, unit_price=25.0)
    assert result["total_tonnage"] == 0
    assert result["gross_entitlement"] == 0
    assert result["quality_coefficient"] == 1.0


def test_entitlement_chain_full():
    # Brüt 2500, destek mahsubu 250, bir kesinti 100, bir prim 50
    chain = calculate_entitlement_chain(
        gross_entitlement=2500.0,
        destek_mahsup_total=250.0,
        kesintiler=[{"definition_id": "k1", "name": "Fire", "amount": 100.0}],
        primler=[{"definition_id": "p1", "name": "Kalite Primi", "amount": 50.0}],
    )
    assert chain["total_kesinti"] == 100.0
    assert chain["total_deduction"] == 350.0          # 250 (destek) + 100 (kesinti)
    assert chain["net_entitlement"] == 2150.0         # 2500 - 350
    assert chain["total_prim"] == 50.0
    assert chain["payable_amount"] == 2200.0          # 2150 + 50


def test_entitlement_chain_no_deductions_or_prims():
    chain = calculate_entitlement_chain(1000.0, destek_mahsup_total=0, kesintiler=[], primler=[])
    assert chain["net_entitlement"] == 1000.0
    assert chain["payable_amount"] == 1000.0


def test_resolve_definition_sabit_tutar():
    definition = {"name": "Ceza", "calculation_type": "sabit_tutar", "value": 75.0}
    assert resolve_definition_amount(definition, gross_entitlement=1000.0, override_amount=None) == 75.0


def test_resolve_definition_yuzde():
    definition = {"name": "Kalite Primi", "calculation_type": "yuzde", "value": 5.0}
    assert resolve_definition_amount(definition, gross_entitlement=1000.0, override_amount=None) == 50.0


def test_resolve_definition_override_wins():
    definition = {"name": "Ceza", "calculation_type": "sabit_tutar", "value": 75.0}
    assert resolve_definition_amount(definition, gross_entitlement=1000.0, override_amount=200.0) == 200.0


def test_resolve_definition_formul_requires_override():
    definition = {"name": "Özel Formül", "calculation_type": "formul", "value": 0}
    try:
        resolve_definition_amount(definition, gross_entitlement=1000.0, override_amount=None)
        assert False, "formul tipi override_amount olmadan ValueError vermeli"
    except ValueError:
        pass


def test_resolve_definition_formul_with_override():
    definition = {"name": "Özel Formül", "calculation_type": "formul", "value": 0}
    assert resolve_definition_amount(definition, gross_entitlement=1000.0, override_amount=42.5) == 42.5
