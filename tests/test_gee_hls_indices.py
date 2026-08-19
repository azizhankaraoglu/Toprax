"""
=====================================================================
GEE/HLS çok-indeksli analiz — birim testleri (2026-08-18)
=====================================================================
Çiftçi AI'nın uydu servisinden TOPRAX'a taşınan davranışın sözleşmesini
kilitler. Gerçek Earth Engine çağrısı YAPILMAZ (ağ/kota gerektirir) —
test edilen şey: indeks doğrulama, mock serinin şekli, sensör ayrımı,
Landsat'ta kırmızı kenar indekslerinin None kalması ve provider
sarmalayıcısının seriyi boru hattının beklediği biçimde vermesi.

`_real_analyze`'ın GEE'ye özgü kısmı (bant harmonizasyonu, JODA tarih
kalıbı, projeksiyon tuzağı) canlı kimlik bilgisiyle ayrıca elle
doğrulanır — bkz. CHANGELOG'daki doğrulama notu.
"""
from datetime import date

import pytest

from remote_sensing.indices import ALL_INDEX_CODES
from remote_sensing.providers.gee_hls import service as gee

RING = [[32.850, 39.900], [32.860, 39.900], [32.860, 39.910], [32.850, 39.910], [32.850, 39.900]]
START = date(2026, 6, 1)
END = date(2026, 6, 30)


# --- İndeks doğrulama --------------------------------------------------------

def test_indices_verilmezse_tum_katalog_hesaplanir():
    assert gee.normalize_indices(None) == list(ALL_INDEX_CODES)


def test_ndvi_her_zaman_eklenir():
    # tasks.py'nin last_ndvi mirror'ı NDVI'siz seriyle çalışamaz.
    assert gee.normalize_indices(["msi"])[0] == "ndvi"
    assert "msi" in gee.normalize_indices(["msi"])


def test_bilinmeyen_indeks_kodu_reddedilir():
    with pytest.raises(gee.InvalidFieldRequest):
        gee.normalize_indices(["ndvi", "bilinmeyen_indeks"])


def test_katalog_sirasi_korunur():
    codes = gee.normalize_indices(["lai", "ndwi", "ndvi"])
    assert codes == [c for c in ALL_INDEX_CODES if c in ("ndvi", "ndwi", "lai")]


# --- Mock analiz şekli -------------------------------------------------------

def test_mock_analiz_tum_indeksleri_ve_sensoru_dondurur():
    result = gee._mock_analyze(RING, START, END, area_ha=4.2)
    assert result["status"] == "success"
    assert result["meta"]["buffer_applied"] == "30 meters"
    assert result["meta"]["mock"] is True
    assert result["ndvi_history"], "mock seri boş olmamalı"
    # Literal Faz 9C sözleşmesi + yeni okunabilir ad AYNI listeyi gösterir.
    assert result["indices_history"] == result["ndvi_history"]
    point = result["ndvi_history"][0]
    for code in ALL_INDEX_CODES:
        assert code in point, f"{code} mock noktada yok"
    assert point["sensor"] in ("S30", "L30")


def test_landsat_sahnelerinde_kirmizi_kenar_indeksleri_none():
    # Sıfır YAZILMAZ — "ölçülemedi" ile "ölçüldü, sıfır çıktı" farklıdır.
    result = gee._mock_analyze(RING, START, END, area_ha=4.2)
    l30 = [p for p in result["ndvi_history"] if p["sensor"] == "L30"]
    assert l30, "mock seride en az bir Landsat sahnesi olmalı"
    for p in l30:
        for code in gee.RED_EDGE_DEPENDENT:
            assert p[code] is None
        assert p["ndvi"] is not None      # NIR/Red Landsat'ta VAR


def test_mock_deterministik():
    a = gee._mock_analyze(RING, START, END, area_ha=4.2)
    b = gee._mock_analyze(RING, START, END, area_ha=4.2)
    assert a["ndvi_history"] == b["ndvi_history"]


def test_secili_indeksler_disindakiler_seriye_girmez():
    result = gee._mock_analyze(RING, START, END, area_ha=4.2, indices=["ndwi"])
    point = result["ndvi_history"][0]
    assert "ndwi" in point and "ndvi" in point
    assert "evi" not in point
    assert result["meta"]["indices"] == ["ndvi", "ndwi"]


def test_sensor_etiketleri_olculen_uydulari_yazar():
    result = gee._mock_analyze(RING, START, END, area_ha=4.2)
    sensors = result["meta"]["sensors"]
    assert sensors, "kaynak sensör listesi boş olmamalı"
    for label in sensors:
        assert label in gee.SENSOR_LABELS.values()


# --- Provider sarmalayıcısı (boru hattı sözleşmesi) --------------------------

def test_provider_serisi_cok_indeksli_doner():
    provider = gee.GEEHLSProvider(mock_mode=True)
    geometry = {"type": "Polygon", "coordinates": [RING]}
    task_id = provider.request_statistics("parsel-1", ["ndvi", "ndwi", "msi"],
                                          (START, END), geometry=geometry)
    status = provider.get_task_status(task_id)
    assert status.state.value == "completed"
    series = status.result["series"]
    assert series
    point = series[0]
    # base.parse_statistics'in beklediği ortak şekil: date + cloud_pct + indeksler
    assert set(["date", "cloud_pct", "ndvi", "ndwi", "msi"]).issubset(point.keys())


def test_provider_geometrisiz_istek_hata_dondurur():
    provider = gee.GEEHLSProvider(mock_mode=True)
    task_id = provider.request_statistics("parsel-1", ["ndvi"], (START, END), geometry=None)
    status = provider.get_task_status(task_id)
    assert status.state.value == "failed"


def test_su_stresi_sezgisi_gee_serisini_okuyabiliyor():
    # base.py'nin detect_water_stress'i MSI/NDWI bekliyor — GEE serisi
    # artık bu alanları taşıdığı için bildirim zinciri GEE ile de çalışır.
    provider = gee.GEEHLSProvider(mock_mode=True)
    series = [{"date": "2026-06-01", "msi": 0.9}, {"date": "2026-06-06", "msi": 1.7}]
    anomaly = provider.detect_water_stress(series)
    assert anomaly.detected is True
    assert anomaly.severity == "yuksek"
