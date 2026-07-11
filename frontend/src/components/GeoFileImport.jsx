import { useEffect, useState } from "react";
import api from "@/api";
import { MapContainer, TileLayer, Polygon, Polyline, CircleMarker } from "react-leaflet";
import { Upload, Check, X, Layers } from "lucide-react";
import { mapTkgmProperties, TKGM_FIELD_LABELS } from "@/lib/tkgmMapping";

/**
 * IT-13.5 — Geo Dosya İçe Aktarma. GeoJSON/KML/DXF/SHP(.zip) dosyası
 * yükler, backend'de (geo_import.py) ayrıştırıp WGS84'e çevirir,
 * SONUCU HARİTADA GÖSTERİR — kullanıcı onaylamadan hiçbir kayıt
 * yazılmaz. Onaylanınca `onConfirm(geometry, tkgmFields)` çağrılır;
 * asıl kaydetme işini (ör. parsel için `PUT /parcels/{id}`) ÇAĞIRAN
 * taraf yapar — bu bileşen sadece dosya→onaylı geometri akışından
 * sorumludur.
 *
 * `tkgmFields` (IT-16) — seçili feature'ın properties'inde TKGM Parsel
 * Sorgu tarzı il/ilçe/mahalle/ada/parsel anahtarları TANINIRSA (bkz.
 * lib/tkgmMapping.js) bunlar burada tespit edilip önizlemede gösterilir;
 * kullanıcı "Bu bilgileri de uygula" kutusunu işaretli bırakırsa
 * `onConfirm`'e ikinci argüman olarak geçirilir, aksi halde `null`
 * (mevcut ÇAĞIRANLAR ikinci argümanı YOK SAYARSA davranış eskisiyle
 * birebir aynı kalır — geriye dönük kırılma yok).
 *
 * Kullanım: <GeoFileImport onConfirm={(geom, tkgmFields) => api.put(`/parcels/${id}`, { geometry: geom, ...(tkgmFields || {}) })} />
 */
const NEEDS_EPSG_EXTENSIONS = new Set(["zip", "dxf"]);

function centerOf(geometry) {
  const flat = [];
  (function walk(c) {
    if (typeof c[0] === "number") flat.push(c);
    else c.forEach(walk);
  })(geometry.coordinates);
  if (flat.length === 0) return [39.5, 33.5];
  const lat = flat.reduce((s, p) => s + p[1], 0) / flat.length;
  const lng = flat.reduce((s, p) => s + p[0], 0) / flat.length;
  return [lat, lng];
}

export default function GeoFileImport({ onConfirm }) {
  const [epsgCodes, setEpsgCodes] = useState([]);
  const [file, setFile] = useState(null);
  const [sourceEpsg, setSourceEpsg] = useState("");
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null); // { format, feature_count, features }
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [saving, setSaving] = useState(false);
  const [applyTkgmFields, setApplyTkgmFields] = useState(true);

  useEffect(() => { api.get("/geo-import/epsg-codes").then((r) => setEpsgCodes(r.data)); }, []);

  const ext = file?.name.split(".").pop()?.toLowerCase() || "";
  const needsEpsg = NEEDS_EPSG_EXTENSIONS.has(ext);

  async function parse() {
    if (!file) return;
    setParsing(true);
    setError("");
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (sourceEpsg) form.append("source_epsg", sourceEpsg);
      const { data } = await api.post("/geo-import/parse", form, { headers: { "Content-Type": "multipart/form-data" } });
      setResult(data);
      setSelectedIdx(0);
    } catch (err) {
      setError(err.response?.data?.detail || "Dosya ayrıştırılamadı.");
    } finally {
      setParsing(false);
    }
  }

  async function confirm() {
    if (!result) return;
    const geometry = result.features[selectedIdx].geometry;
    const tkgmFields = applyTkgmFields ? mapTkgmProperties(result.features[selectedIdx].properties) : null;
    setSaving(true);
    setError("");
    try {
      await onConfirm(geometry, tkgmFields);
      setResult(null);
      setFile(null);
    } catch (err) {
      setError(err.response?.data?.detail || "Kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  const selectedFeature = result?.features[selectedIdx];
  const detectedTkgmFields = selectedFeature ? mapTkgmProperties(selectedFeature.properties) : null;

  return (
    <div className="card p-5" data-testid="geo-file-import">
      <div className="flex items-center gap-2 mb-3">
        <Layers size={16} className="text-[var(--primary)]" />
        <h3 className="font-display text-lg">Sınır İçe Aktar (SHP / GeoJSON / KML / DXF)</h3>
      </div>

      <div className="flex flex-wrap items-end gap-3 mb-3">
        <div>
          <label className="text-xs text-[var(--text-dim)] mb-1 block">Dosya</label>
          <input
            type="file"
            accept=".geojson,.json,.kml,.dxf,.zip"
            data-testid="geo-import-file-input"
            onChange={(e) => { setFile(e.target.files[0] || null); setResult(null); setError(""); }}
            className="text-xs"
          />
        </div>
        {needsEpsg && (
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Kaynak Koordinat Sistemi (EPSG)</label>
            <select className="input text-xs" value={sourceEpsg} onChange={(e) => setSourceEpsg(e.target.value)}>
              <option value="">SHP ise .prj varsa otomatik algılanır — yoksa seçin</option>
              {epsgCodes.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
            </select>
          </div>
        )}
        <button onClick={parse} disabled={!file || parsing} className="btn btn-primary text-xs" data-testid="geo-import-parse-btn">
          <Upload size={13} /> {parsing ? "Ayrıştırılıyor…" : "Ayrıştır"}
        </button>
      </div>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-3">{error}</div>}

      {result && (
        <div className="space-y-3">
          <div className="text-xs text-[var(--text-dim)]">
            {result.feature_count} geometri bulundu ({result.format.toUpperCase()}) — onaylamadan önce haritada kontrol edin.
          </div>

          {result.feature_count > 1 && (
            <select className="input text-xs" value={selectedIdx} onChange={(e) => setSelectedIdx(Number(e.target.value))}>
              {result.features.map((f, i) => (
                <option key={i} value={i}>
                  {i + 1}. {f.properties?.name || f.properties?.ad || f.geometry.type}
                </option>
              ))}
            </select>
          )}

          {selectedFeature && (
            <div className="card overflow-hidden" style={{ height: 300 }}>
              <MapContainer center={centerOf(selectedFeature.geometry)} zoom={15} style={{ height: "100%", width: "100%" }}>
                <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap" />
                {selectedFeature.geometry.type === "Polygon" && (
                  <Polygon positions={selectedFeature.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])} pathOptions={{ color: "#4ade80" }} />
                )}
                {selectedFeature.geometry.type === "LineString" && (
                  <Polyline positions={selectedFeature.geometry.coordinates.map(([lng, lat]) => [lat, lng])} pathOptions={{ color: "#4ade80" }} />
                )}
                {selectedFeature.geometry.type === "Point" && (
                  <CircleMarker center={[selectedFeature.geometry.coordinates[1], selectedFeature.geometry.coordinates[0]]} radius={8} pathOptions={{ color: "#4ade80" }} />
                )}
              </MapContainer>
            </div>
          )}

          {detectedTkgmFields && (
            <div className="text-xs p-3 rounded-lg border border-[var(--primary)]/30 bg-[var(--primary)]/5 space-y-2" data-testid="tkgm-fields-preview">
              <div className="text-[var(--primary)]">TKGM alanları algılandı:</div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[var(--text-dim)]">
                {Object.entries(detectedTkgmFields).map(([k, v]) => (
                  <span key={k}><strong className="text-white">{TKGM_FIELD_LABELS[k] || k}:</strong> {v}</span>
                ))}
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={applyTkgmFields} onChange={(e) => setApplyTkgmFields(e.target.checked)} />
                Bu bilgileri de parsele uygula
              </label>
            </div>
          )}

          <div className="flex items-center gap-2">
            <button onClick={() => { setResult(null); setFile(null); }} className="btn text-xs text-red-400"><X size={13} /> İptal</button>
            <button onClick={confirm} disabled={saving || selectedFeature?.geometry.type !== "Polygon"} className="btn btn-primary text-xs" data-testid="geo-import-confirm-btn">
              <Check size={13} /> {saving ? "Kaydediliyor…" : "Onayla ve Kaydet"}
            </button>
            {selectedFeature && selectedFeature.geometry.type !== "Polygon" && (
              <span className="text-[10px] text-[var(--text-dim)]">Parsel sınırı için Polygon geometrisi gerekir.</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
