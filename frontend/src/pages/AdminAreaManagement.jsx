/**
 * İDARİ ALAN YÖNETİMİ (IT-13.6) — il/ilçe/mahalle sınır+demografi yönetimi.
 * Liste: SmartDataGrid (IT-11) — Query Engine'e bağlı, module="admin_areas".
 * Detay: Drawer (IT-12) — sınır önizleme + demografi (DynamicFieldsSection,
 * Sprint A1) + o alandaki çiftçi/parsel özeti ($geoIntersects, backend).
 * Sınır yükleme: GeoFileImport (IT-13.5, tekli) + kendi toplu yükleme formu.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { MapContainer, TileLayer, Polygon } from "react-leaflet";
import { Plus, Upload, Users, Map as MapIcon } from "lucide-react";
import SmartDataGrid from "@/components/SmartDataGrid";
import Drawer from "@/components/Drawer";
import DynamicFieldsSection from "@/components/DynamicFieldsSection";
import GeoFileImport from "@/components/GeoFileImport";
import { QuickAddPanel } from "@/components/QuickAdd";

const GRID_COLUMNS = [
  { key: "name", label: "Ad", type: "text" },
  { key: "area_type", label: "Tip", type: "text" },
  { key: "population", label: "Nüfus", type: "number" },
  { key: "agricultural_area_dekar", label: "Tarım Alanı (dekar)", type: "number" },
  { key: "farmer_count_est", label: "Tahmini Çiftçi Sayısı", type: "number" },
];

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

function BulkImport({ onDone }) {
  const [file, setFile] = useState(null);
  const [areaType, setAreaType] = useState("mahalle");
  const [nameField, setNameField] = useState("ad");
  const [sourceEpsg, setSourceEpsg] = useState("");
  const [epsgCodes, setEpsgCodes] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => { api.get("/geo-import/epsg-codes").then((r) => setEpsgCodes(r.data)); }, []);

  const ext = file?.name.split(".").pop()?.toLowerCase() || "";
  const needsEpsg = ext === "zip" || ext === "dxf";

  async function run() {
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (sourceEpsg) form.append("source_epsg", sourceEpsg);
      const { data: parsed } = await api.post("/geo-import/parse", form, { headers: { "Content-Type": "multipart/form-data" } });
      const { data: imported } = await api.post("/admin-areas/bulk-import", {
        area_type: areaType, name_field: nameField, features: parsed.features,
      });
      setResult(imported);
      onDone();
    } catch (err) {
      setError(err.response?.data?.detail || "İçe aktarılamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card p-5 mb-4">
      <div className="flex items-center gap-2 mb-3">
        <Upload size={16} className="text-[var(--primary)]" />
        <h3 className="font-display text-lg">Toplu Sınır Yükleme (tek SHP/GeoJSON/KML/DXF → çok sayıda idari alan)</h3>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="text-xs text-[var(--text-dim)] mb-1 block">Dosya</label>
          <input type="file" accept=".geojson,.json,.kml,.dxf,.zip" onChange={(e) => setFile(e.target.files[0] || null)} className="text-xs" />
        </div>
        <div>
          <label className="text-xs text-[var(--text-dim)] mb-1 block">Alan Tipi</label>
          <select className="input text-xs" value={areaType} onChange={(e) => setAreaType(e.target.value)}>
            <option value="il">İl</option><option value="ilce">İlçe</option><option value="mahalle">Mahalle</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-[var(--text-dim)] mb-1 block">Ad Alanı (dosyadaki attribute adı)</label>
          <input className="input text-xs" value={nameField} onChange={(e) => setNameField(e.target.value)} placeholder="örn. ad, ILCE_ADI" />
        </div>
        {needsEpsg && (
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Kaynak EPSG</label>
            <select className="input text-xs" value={sourceEpsg} onChange={(e) => setSourceEpsg(e.target.value)}>
              <option value="">.prj varsa otomatik — yoksa seçin</option>
              {epsgCodes.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
            </select>
          </div>
        )}
        <button onClick={run} disabled={!file || busy} className="btn btn-primary text-xs">
          {busy ? "İçe aktarılıyor…" : "Ayrıştır ve İçe Aktar"}
        </button>
      </div>
      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mt-3">{error}</div>}
      {result && <div className="text-xs text-[var(--primary)] mt-3">{result.count} idari alan oluşturuldu.</div>}
    </div>
  );
}

function AreaDrawer({ area, onClose, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [summary, setSummary] = useState(null);
  const [editValues, setEditValues] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!area) return;
    api.get(`/admin-areas/${area.id}`).then((r) => { setDetail(r.data); setEditValues(r.data); });
    api.get(`/admin-areas/${area.id}/summary`).then((r) => setSummary(r.data));
  }, [area]);

  async function saveDemografi() {
    setSaving(true);
    try {
      await api.put(`/admin-areas/${area.id}`, {
        population: editValues.population ? Number(editValues.population) : null,
        agricultural_area_dekar: editValues.agricultural_area_dekar ? Number(editValues.agricultural_area_dekar) : null,
        farmer_count_est: editValues.farmer_count_est ? Number(editValues.farmer_count_est) : null,
      });
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer open={!!area} onClose={onClose} title={area?.name || ""} width="520px">
      {detail && (
        <div className="p-4 space-y-4">
          {detail.geometry && (
            <div className="card overflow-hidden" style={{ height: 220 }}>
              <MapContainer center={centerOf(detail.geometry)} zoom={11} style={{ height: "100%", width: "100%" }}>
                <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap" />
                {(detail.geometry.type === "MultiPolygon" ? detail.geometry.coordinates.flat() : detail.geometry.coordinates).map((ring, i) => (
                  <Polygon key={i} positions={ring.map(([lng, lat]) => [lat, lng])} pathOptions={{ color: "#60a5fa" }} />
                ))}
              </MapContainer>
            </div>
          )}

          {summary && (
            <div className="grid grid-cols-2 gap-3">
              <div className="card p-3 text-center">
                <MapIcon size={16} className="mx-auto mb-1 text-[var(--primary)]" />
                <div className="font-display text-xl">{summary.parcel_count}</div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase">Kesişen Parsel</div>
              </div>
              <div className="card p-3 text-center">
                <Users size={16} className="mx-auto mb-1 text-[var(--primary)]" />
                <div className="font-display text-xl">{summary.farmer_count}</div>
                <div className="text-[10px] text-[var(--text-dim)] uppercase">Çiftçi</div>
              </div>
            </div>
          )}

          <div>
            <div className="text-xs font-medium text-[var(--primary)] mb-2">Demografi</div>
            <DynamicFieldsSection module="admin_areas" values={editValues} onChange={(k, v) => setEditValues((f) => ({ ...f, [k]: v }))} title="" />
            <button onClick={saveDemografi} disabled={saving} className="btn btn-primary text-xs mt-2">
              {saving ? "Kaydediliyor…" : "Demografiyi Kaydet"}
            </button>
          </div>

          <div>
            <div className="text-xs font-medium text-[var(--primary)] mb-2">Sınırı Değiştir</div>
            <GeoFileImport onConfirm={async (geometry) => {
              await api.put(`/admin-areas/${area.id}`, { geometry });
              const r = await api.get(`/admin-areas/${area.id}`);
              setDetail(r.data);
              onChanged();
            }} />
          </div>
        </div>
      )}
    </Drawer>
  );
}

export default function AdminAreaManagement() {
  const [gridKey, setGridKey] = useState(0);
  const [selectedArea, setSelectedArea] = useState(null);
  const [creating, setCreating] = useState(false);
  const [parents, setParents] = useState([]);

  useEffect(() => { api.get("/admin-areas").then((r) => setParents(r.data)); }, [gridKey]);

  function refresh() { setGridKey((k) => k + 1); }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="admin-area-management-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">IT-13.6</div>
          <h1 className="font-display text-4xl">İdari Alan Yönetimi</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">İl / İlçe / Mahalle sınırları ve demografi — sınır verisi sisteme gömülü değildir, dosyadan içe aktarılır.</p>
        </div>
      </header>

      <QuickAddPanel
        title="Yeni İdari Alan"
        testId="admin-area-add"
        fields={[
          { name: "name", label: "Ad", required: true },
          { name: "area_type", label: "Tip", type: "select", required: true,
            options: [{ value: "il", label: "İl" }, { value: "ilce", label: "İlçe" }, { value: "mahalle", label: "Mahalle" }] },
          { name: "parent_id", label: "Üst Alan (opsiyonel)", type: "select",
            options: parents.map((p) => ({ value: p.id, label: `${p.name} (${p.area_type})` })) },
        ]}
        onSubmit={async (v) => {
          await api.post("/admin-areas", { ...v, parent_id: v.parent_id || null });
          refresh();
        }}
      />

      <BulkImport onDone={refresh} />

      <SmartDataGrid key={gridKey} module="admin_areas" columns={GRID_COLUMNS} onRowClick={setSelectedArea} />

      <AreaDrawer area={selectedArea} onClose={() => setSelectedArea(null)} onChanged={refresh} />
    </div>
  );
}
