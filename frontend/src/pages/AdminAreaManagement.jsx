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
import { getBasemapUrl } from "@/lib/theme";

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

// SON HAL #7 — "toplu idari alan yüklerken isimleri verinin içinden ayırıp
// yaz" talebi: kullanıcı artık dosyadaki attribute adını KÖR yazmıyor
// (önceden "ad"/"ILCE_ADI" gibi tahminle elle girilirdi). Akış ikiye
// bölündü: 1) Ayrıştır — dosya PARSE edilir, gerçek property anahtarları
// çıkarılır ve en olası "ad" alanı otomatik tahmin edilip seçili gelir;
// 2) kullanıcı önizlemede ADLARI GÖRÜR, gerekirse dropdown'dan doğru
// alanı seçer, sonra İçe Aktar eder. /geo-import/parse HÂLÂ hiçbir şey
// yazmıyor (mevcut "önizle→onayla" ilkesi korunur).
const NAME_FIELD_GUESSES = [
  "ad", "isim", "name", "ADI", "AD", "NAME", "ILCE_ADI", "IL_ADI", "MAH_ADI",
  "mahalle_adi", "ilce_adi", "il_adi", "NAME_1", "NAME_2", "label",
];

function guessNameField(keys) {
  const lower = keys.map((k) => k.toLowerCase());
  for (const guess of NAME_FIELD_GUESSES) {
    const idx = lower.indexOf(guess.toLowerCase());
    if (idx !== -1) return keys[idx];
  }
  // Tam eşleşme yoksa "ad"/"isim"/"name" geçen ilk anahtar.
  const partial = keys.find((k) => /ad|isim|name/i.test(k));
  return partial || keys[0] || "";
}

function BulkImport({ onDone }) {
  const [file, setFile] = useState(null);
  const [areaType, setAreaType] = useState("mahalle");
  const [nameField, setNameField] = useState("");
  const [sourceEpsg, setSourceEpsg] = useState("");
  const [epsgCodes, setEpsgCodes] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [parsed, setParsed] = useState(null);      // {features} — ayrıştırılmış ama henüz kaydedilmemiş
  const [propKeys, setPropKeys] = useState([]);     // dosyadaki gerçek attribute anahtarları

  useEffect(() => { api.get("/geo-import/epsg-codes").then((r) => setEpsgCodes(r.data)); }, []);

  const ext = file?.name.split(".").pop()?.toLowerCase() || "";
  const needsEpsg = ext === "zip" || ext === "dxf";

  async function parseFile() {
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    setParsed(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (sourceEpsg) form.append("source_epsg", sourceEpsg);
      const { data } = await api.post("/geo-import/parse", form, { headers: { "Content-Type": "multipart/form-data" } });
      setParsed(data);
      const keys = [...new Set((data.features || []).flatMap((f) => Object.keys(f.properties || {})))];
      setPropKeys(keys);
      setNameField(guessNameField(keys));
    } catch (err) {
      setError(err.response?.data?.detail || "Dosya ayrıştırılamadı.");
    } finally {
      setBusy(false);
    }
  }

  async function runImport() {
    if (!parsed || !nameField) return;
    setBusy(true);
    setError("");
    try {
      const { data: imported } = await api.post("/admin-areas/bulk-import", {
        area_type: areaType, name_field: nameField, features: parsed.features,
      });
      setResult(imported);
      setParsed(null);
      setFile(null);
      onDone();
    } catch (err) {
      setError(err.response?.data?.detail || "İçe aktarılamadı.");
    } finally {
      setBusy(false);
    }
  }

  // Önizleme: seçili ad alanına göre ilk 5 kaydın gerçek adları (kullanıcı
  // doğru alanı seçtiğini görsün diye — "verinin içinden ayırıp yaz" tam
  // olarak budur).
  const namePreview = parsed ? (parsed.features || []).slice(0, 5).map((f) => f.properties?.[nameField]) : [];

  return (
    <div className="card p-5 mb-4">
      <div className="flex items-center gap-2 mb-3">
        <Upload size={16} className="text-[var(--primary)]" />
        <h3 className="font-display text-lg">Toplu Sınır Yükleme (tek SHP/GeoJSON/KML/DXF → çok sayıda idari alan)</h3>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="text-xs text-[var(--text-dim)] mb-1 block">Dosya</label>
          <input type="file" accept=".geojson,.json,.kml,.dxf,.zip"
                 onChange={(e) => { setFile(e.target.files[0] || null); setParsed(null); setResult(null); }} className="text-xs" />
        </div>
        <div>
          <label className="text-xs text-[var(--text-dim)] mb-1 block">Alan Tipi</label>
          <select className="input text-xs" value={areaType} onChange={(e) => setAreaType(e.target.value)}>
            <option value="il">İl</option><option value="ilce">İlçe</option><option value="mahalle">Mahalle</option>
          </select>
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
        {!parsed && (
          <button onClick={parseFile} disabled={!file || busy} className="btn btn-primary text-xs" data-testid="admin-area-bulk-parse">
            {busy ? "Ayrıştırılıyor…" : "Dosyayı Ayrıştır"}
          </button>
        )}
      </div>

      {parsed && (
        <div className="mt-4 p-3 bg-[var(--surface-2)] rounded-lg" data-testid="admin-area-bulk-preview">
          <div className="text-xs text-[var(--text-dim)] mb-2">
            {parsed.features?.length || 0} kayıt ayrıştırıldı. Dosyadaki gerçek alanlardan hangisi "ad" ise seçin —
            aşağıda o alana göre ilk kayıtların adları önizlenir.
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="text-xs text-[var(--text-dim)] mb-1 block">Ad Alanı (dosyadan otomatik tespit edildi)</label>
              <select className="input text-xs" value={nameField} onChange={(e) => setNameField(e.target.value)} data-testid="admin-area-bulk-namefield">
                {propKeys.length === 0 && <option value="">— dosyada attribute bulunamadı —</option>}
                {propKeys.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
            <button onClick={runImport} disabled={busy || !nameField} className="btn btn-primary text-xs" data-testid="admin-area-bulk-import">
              {busy ? "İçe aktarılıyor…" : `${parsed.features?.length || 0} Alanı İçe Aktar`}
            </button>
            <button onClick={() => { setParsed(null); setFile(null); }} className="btn text-xs">Vazgeç</button>
          </div>
          {namePreview.length > 0 && (
            <div className="text-[11px] text-[var(--text-dim)] mt-2">
              Önizleme: {namePreview.map((n) => n ?? "—").join(", ")}{parsed.features.length > 5 ? "…" : ""}
            </div>
          )}
        </div>
      )}

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mt-3">{error}</div>}
      {result && <div className="text-xs text-[var(--primary)] mt-3">{result.count} idari alan oluşturuldu.</div>}
      {/* Denetim STAB-B1: geometri tipi uygun olmayan (örn. Point) kayıtlar
          artık backend'den uyarı olarak döner ve burada gösterilir. */}
      {result?.warnings?.length > 0 && (
        <div className="text-xs text-amber-400 p-2 bg-amber-500/10 rounded mt-2 space-y-1" data-testid="admin-area-bulk-warnings">
          {result.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}
    </div>
  );
}

function AreaDrawer({ area, onClose, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [summary, setSummary] = useState(null);
  const [editValues, setEditValues] = useState({});
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState([]);
  const [areas, setAreas] = useState([]);

  useEffect(() => {
    if (!area) return;
    api.get(`/admin-areas/${area.id}`).then((r) => { setDetail(r.data); setEditValues(r.data); });
    api.get(`/admin-areas/${area.id}/summary`).then((r) => setSummary(r.data));
    api.get("/users").then((r) => setUsers(r.data || [])).catch(() => {});
    api.get("/admin-areas").then((r) => setAreas(r.data || [])).catch(() => {});
  }, [area]);

  async function saveBasic() {
    setSaving(true);
    try {
      await api.put(`/admin-areas/${area.id}`, {
        name: editValues.name,
        area_type: editValues.area_type,
        parent_id: editValues.parent_id || null,          // null → değişmez (üst alan temizleme ender)
        responsible_user_id: editValues.responsible_user_id ?? "",   // "" → sorumluyu kaldır
      });
      const r = await api.get(`/admin-areas/${area.id}`);
      setDetail(r.data); setEditValues(r.data);
      onChanged();
    } catch (err) {
      alert(err.response?.data?.detail || "Kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

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
                <TileLayer url={getBasemapUrl()} attribution="&copy; OpenStreetMap" />
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
            <div className="text-xs font-medium text-[var(--primary)] mb-2">Temel Bilgiler</div>
            <div className="space-y-2">
              <div>
                <label className="text-[11px] text-[var(--text-dim)]">Ad</label>
                <input className="input" value={editValues.name || ""}
                       onChange={(e) => setEditValues((f) => ({ ...f, name: e.target.value }))}
                       data-testid="admin-area-edit-name" />
              </div>
              <div>
                <label className="text-[11px] text-[var(--text-dim)]">Tip</label>
                <select className="input" value={editValues.area_type || ""}
                        onChange={(e) => setEditValues((f) => ({ ...f, area_type: e.target.value }))}>
                  <option value="il">İl</option>
                  <option value="ilce">İlçe</option>
                  <option value="mahalle">Mahalle</option>
                </select>
              </div>
              <div>
                <label className="text-[11px] text-[var(--text-dim)]">Üst Alan</label>
                <select className="input" value={editValues.parent_id || ""}
                        onChange={(e) => setEditValues((f) => ({ ...f, parent_id: e.target.value }))}>
                  <option value="">— yok —</option>
                  {areas.filter((a) => a.id !== area?.id).map((a) => (
                    <option key={a.id} value={a.id}>{a.name} ({a.area_type})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[11px] text-[var(--text-dim)]">Sorumlu Personel (köy sorumlusu)</label>
                <select className="input" value={editValues.responsible_user_id || ""}
                        onChange={(e) => setEditValues((f) => ({ ...f, responsible_user_id: e.target.value }))}
                        data-testid="admin-area-responsible">
                  <option value="">— atanmadı —</option>
                  {users.filter((u) => u.role !== "ciftci").map((u) => (
                    <option key={u.id} value={u.id}>{u.full_name || u.email} ({u.role})</option>
                  ))}
                </select>
                <div className="text-[10px] text-[var(--text-dim)] mt-1">Bu köydeki çiftçi ve parseller bu sorumluyu devralır (portföy).</div>
              </div>
              <button onClick={saveBasic} disabled={saving} className="btn btn-primary text-xs" data-testid="admin-area-save-basic">
                {saving ? "Kaydediliyor…" : "Temel Bilgileri Kaydet"}
              </button>
            </div>
          </div>

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

          <div className="pt-3 border-t border-[var(--border)]">
            <button
              onClick={async () => {
                if (!window.confirm("Bu idari alan silinsin mi?\n(Kayıt arşivlenir — geri alınabilir.)")) return;
                try { await api.delete(`/admin-areas/${area.id}`); onChanged(); onClose(); }
                catch (err) { alert(err.response?.data?.detail || "Silinemedi."); }
              }}
              className="btn btn-ghost text-xs text-red-400" data-testid="admin-area-delete">
              Bölgeyi Sil
            </button>
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
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">İDARİ ALANLAR</div>
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

      {/* SON HAL #7 — toplu silme (grid çoklu seçim + POST /admin-areas/bulk-delete) */}
      <SmartDataGrid
        key={gridKey}
        module="admin_areas"
        columns={GRID_COLUMNS}
        onRowClick={setSelectedArea}
        bulkActions={(ids, { clearSelection, reload }) => (
          <button
            className="text-red-400 hover:underline"
            data-testid="admin-area-bulk-delete"
            onClick={async () => {
              if (!window.confirm(`${ids.length} idari alan silinsin mi?\n(Kayıtlar arşivlenir — geri alınabilir.)`)) return;
              await api.post("/admin-areas/bulk-delete", { area_ids: ids });
              clearSelection();
              reload();
            }}
          >
            Seçilenleri Sil ({ids.length})
          </button>
        )}
      />

      <AreaDrawer area={selectedArea} onClose={() => setSelectedArea(null)} onChanged={refresh} />
    </div>
  );
}
