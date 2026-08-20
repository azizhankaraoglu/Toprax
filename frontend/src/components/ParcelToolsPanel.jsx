/**
 * PARSEL ARAÇLARI — Harita Paneli'ne EKLENDİ (2026-08-20, kullanıcı isteği).
 *
 * Kullanıcı önce "Parceller'deki Araçlar kutusunu Harita Paneli'ne taşıyalım"
 * dedi; inceleyince bu kutunun (Manuel Ekle/Çiz/Düzenle/Böl/Birleştir/
 * Koordinat Al/Toplu İçe Aktar) Parcels.jsx'e ÇOK derin bağlı, ~650 satırlık
 * bir sistem olduğu ortaya çıktı (kendi state'i, formu, harita tıklama
 * davranışı her araç için ayrı). Riski sıfırlamak için kullanıcı "Harita
 * Paneli'ne EKLE, Parceller'de de bırak" seçeneğini seçti — yani bu dosya
 * Parcels.jsx'in mantığının ADAPTE EDİLMİŞ bir KOPYASI (Parcels.jsx'e
 * DOKUNULMADI, mevcut çalışan sistem BOZULMADI).
 *
 * TEK bilinçli davranış farkı: Parcels.jsx'te "Birleştir" aracı haritada
 * parsele TIKLAYARAK seçtiriyordu (Polygon onClick). HaritaPaneli.jsx'in
 * kendi parsel popup/görev-atama tıklama zincirine dokunmamak için burada
 * "Düzenle"/"Böl" ile AYNI desende, bir LİSTEDEN seçim yapılır — haritaya
 * hiçbir yeni click-handler eklenmez, bu entegrasyonu gerçekten "ekleme"
 * (mevcut kodu değiştirmeden) yapar.
 *
 * Kullanım (HaritaPaneli.jsx içinde):
 *   const pt = useParcelTools({ parcels, farmers, onChanged: loadParcels });
 *   // toolbar satırında:  <ParcelToolsToggle pt={pt} />
 *   // <MapContainer> içinde: <ParcelToolsMapLayer pt={pt} />
 *   // haritanın altında/yanında: <ParcelToolsSidePanel pt={pt} />
 */
import { useState } from "react";
import { useMapEvents } from "react-leaflet";
import * as turf from "@turf/turf";
import { MapDrawTools } from "@/components/MapDrawTools";
import { QuickAddPanel } from "@/components/QuickAdd";
import { mapTkgmProperties } from "@/lib/tkgmMapping";
import FarmerSelect from "@/components/FarmerSelect";
import api from "@/api";
import {
  Wrench, ChevronDown, X, Check, Plus, PenLine, Layers, Scissors, Combine,
  Crosshair, Upload, Landmark,
} from "lucide-react";

const SOIL_TYPES = ["Killi", "Kumlu", "Tınlı", "Kireçli", "Killi-Tınlı"];
const IRRIGATION_TYPES = ["Damla", "Yağmurlama", "Karık", "Yok"];
const areaFromGeoJSON = (geojson) => Math.round((turf.area(geojson) / 1000) * 10) / 10; // m² → dekar

const TOOLS = [
  { key: "manual", icon: Plus, label: "Manuel Ekle" },
  { key: "draw", icon: PenLine, label: "Parsel Çiz" },
  { key: "edit", icon: Layers, label: "Düzenle" },
  { key: "split", icon: Scissors, label: "Böl" },
  { key: "merge", icon: Combine, label: "Birleştir" },
  { key: "coords", icon: Crosshair, label: "Koordinat Al" },
  { key: "import", icon: Upload, label: "Toplu İçe Aktar (GeoJSON/KML/KMZ)" },
];

/** Haritada tıklanan noktanın koordinatını yakalar ("Koordinat Al" aracı) —
 *  Parcels.jsx'teki `CoordsClickHandler` ile AYNI, sadece bu dosyaya taşındı. */
function CoordsClickHandler({ active, onPick }) {
  useMapEvents({ click(e) { if (active) onPick(e.latlng); } });
  return null;
}

function TakbisQuickBox({ form, setForm, busy, result, msg, onQuery }) {
  return (
    <div className="border border-[var(--border)] rounded-lg p-3 mb-3" data-testid="ht-parcel-add-takbis-box">
      <div className="text-xs font-medium text-[var(--primary)] mb-2 flex items-center gap-1.5">
        <Landmark size={13}/> TAKBİS Tapu Sorgu (opsiyonel — sonucu forma elle taşıyın)
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end">
        <div>
          <label className="text-[10px] text-[var(--text-dim)] mb-1 block">İl</label>
          <input className="input text-xs py-1" value={form.il} onChange={(e) => setForm((f) => ({ ...f, il: e.target.value }))} />
        </div>
        <div>
          <label className="text-[10px] text-[var(--text-dim)] mb-1 block">İlçe</label>
          <input className="input text-xs py-1" value={form.ilce} onChange={(e) => setForm((f) => ({ ...f, ilce: e.target.value }))} />
        </div>
        <div>
          <label className="text-[10px] text-[var(--text-dim)] mb-1 block">Ada No</label>
          <input className="input text-xs py-1" value={form.ada} onChange={(e) => setForm((f) => ({ ...f, ada: e.target.value }))} />
        </div>
        <div>
          <label className="text-[10px] text-[var(--text-dim)] mb-1 block">Parsel No</label>
          <input className="input text-xs py-1" value={form.parsel} onChange={(e) => setForm((f) => ({ ...f, parsel: e.target.value }))} />
        </div>
        <button className="btn btn-ghost text-xs py-1.5" onClick={onQuery} disabled={busy} data-testid="ht-parcel-add-takbis-submit">
          {busy ? "Sorgulanıyor…" : "Sorgula"}
        </button>
      </div>
      {msg && <div className="text-[11px] text-[var(--text-dim)] mt-2">{msg}</div>}
      {result?.found && (
        <div className="text-[11px] mt-2 grid grid-cols-2 md:grid-cols-4 gap-2">
          <div><span className="text-[var(--text-dim)]">Malik:</span> {result.malik}</div>
          <div><span className="text-[var(--text-dim)]">Nitelik:</span> {result.nitelik}</div>
          <div><span className="text-[var(--text-dim)]">Alan:</span> {result.alan_m2} m²</div>
          <div><span className="text-[var(--text-dim)]">Tapu Tarihi:</span> {result.tapu_tarihi}</div>
        </div>
      )}
    </div>
  );
}

export function useParcelTools({ parcels, farmers, onChanged }) {
  const [toolsOpen, setToolsOpen] = useState(false);
  const [tool, setTool] = useState(null);
  const [toolMsg, setToolMsg] = useState("");

  const [takbisQuick, setTakbisQuick] = useState({ il: "", ilce: "", ada: "", parsel: "" });
  const [takbisQuickBusy, setTakbisQuickBusy] = useState(false);
  const [takbisQuickResult, setTakbisQuickResult] = useState(null);
  const [takbisQuickMsg, setTakbisQuickMsg] = useState("");
  async function queryTakbisQuick() {
    setTakbisQuickBusy(true); setTakbisQuickMsg(""); setTakbisQuickResult(null);
    try {
      const { data } = await api.post("/gov/takbis/query", takbisQuick);
      setTakbisQuickResult(data);
      if (!data.found) setTakbisQuickMsg("Kayıt bulunamadı.");
    } catch (err) {
      setTakbisQuickMsg(err.response?.data?.detail || "TAKBİS sorgusu başarısız.");
    } finally { setTakbisQuickBusy(false); }
  }

  const [drawnGeoJSON, setDrawnGeoJSON] = useState(null);
  const [editTarget, setEditTarget] = useState(null);
  const [editGeoJSON, setEditGeoJSON] = useState(null);
  const [splitTarget, setSplitTarget] = useState(null);
  const [splitPieces, setSplitPieces] = useState([]);
  const [splitDrawing, setSplitDrawing] = useState(false);
  const [mergeIds, setMergeIds] = useState([]);
  const [mergePreview, setMergePreview] = useState(null);
  const [mergeError, setMergeError] = useState("");
  const [pickedCoord, setPickedCoord] = useState(null);
  const [importFile, setImportFile] = useState(null);
  const [importPreview, setImportPreview] = useState(null);
  const [importFarmerId, setImportFarmerId] = useState("");
  const [importResult, setImportResult] = useState(null);

  function resetTool() {
    setTool(null); setToolMsg("");
    setDrawnGeoJSON(null);
    setEditTarget(null); setEditGeoJSON(null);
    setSplitTarget(null); setSplitPieces([]); setSplitDrawing(false);
    setMergeIds([]); setMergePreview(null); setMergeError("");
    setPickedCoord(null);
    setImportFile(null); setImportPreview(null); setImportResult(null);
  }

  function activateTool(t) {
    resetTool();
    setTool(t);
    const msgs = {
      manual: "Haritada çizim yapmadan, sadece formla temel bilgileri girerek parsel oluşturun (sınırları daha sonra 'Düzenle' ile çizebilirsiniz).",
      draw: "Haritada yeni parselin sınırlarını çizin (köşe köşe tıklayıp son noktada çift tıklayarak bitirin).",
      edit: "Sınırlarını değiştirmek istediğiniz parseli listeden seçin, ardından yeni sınırı çizin.",
      split: "Bölmek istediğiniz parseli listeden seçin, ardından yeni parçaları tek tek çizin (en az 2).",
      merge: "Birleştirmek istediğiniz parselleri listeden işaretleyin (aynı çiftçiye ait ve bitişik olmalı).",
      coords: "Haritada bir noktaya tıklayın, koordinatı burada göreceksiniz.",
      import: "Bir .geojson, .kml veya .kmz dosyası seçin — birden fazla parseli tek seferde içe aktarır.",
    };
    setToolMsg(msgs[t] || "");
  }

  function onDrawCreated(layer, geojson) {
    try {
      const kinks = turf.kinks(turf.polygon(geojson.geometry.coordinates));
      if (kinks?.features?.length > 0) {
        alert("Çizilen şekil kendisiyle kesişiyor — kenarlar birbirinin üzerinden geçmemeli. Lütfen şekli yeniden çizin.");
        return;
      }
    } catch { /* turf geometriyi okuyamazsa backend doğrulaması yakalar */ }
    if (tool === "draw") setDrawnGeoJSON(geojson);
    else if (tool === "edit" && editTarget) setEditGeoJSON(geojson);
    else if (tool === "split" && splitTarget) {
      const area = areaFromGeoJSON(geojson);
      setSplitPieces((p) => [...p, { geojson, area, name: `${splitTarget.name} (Parça ${p.length + 1})` }]);
      setSplitDrawing(false);
    }
  }

  function setSplitPieceName(index, name) {
    setSplitPieces((pieces) => pieces.map((p, i) => (i === index ? { ...p, name } : p)));
  }

  async function submitNewParcel(values) {
    const { farmer_id, name, village, soil_type, irrigation, ...extra } = values;
    const area = areaFromGeoJSON(drawnGeoJSON);
    await api.post("/parcels", {
      ...extra, farmer_id, name, village,
      region_id: farmers.find((f) => f.id === farmer_id)?.region_id,
      area_dekar: area, soil_type, irrigation, geometry: drawnGeoJSON.geometry,
    });
    resetTool(); onChanged?.();
  }

  async function submitManualParcel(values) {
    const { farmer_id, name, village, area_dekar, soil_type, irrigation, ...extra } = values;
    await api.post("/parcels", {
      ...extra, farmer_id, name, village,
      region_id: farmers.find((f) => f.id === farmer_id)?.region_id,
      area_dekar: Number(area_dekar), soil_type, irrigation, geometry: null,
    });
    resetTool(); onChanged?.();
  }

  async function submitEdit() {
    if (!editTarget || !editGeoJSON) return;
    const area = areaFromGeoJSON(editGeoJSON);
    await api.put(`/parcels/${editTarget.id}`, { geometry: editGeoJSON.geometry, area_dekar: area });
    resetTool(); onChanged?.();
  }

  async function submitSplit() {
    if (!splitTarget || splitPieces.length < 2) return;
    if (splitPieces.some((p) => !p.name?.trim())) { setToolMsg("Her parça için bir isim girmelisiniz."); return; }
    await api.post(`/parcels/${splitTarget.id}/split`, {
      new_geometries: splitPieces.map((p) => p.geojson.geometry),
      new_areas_dekar: splitPieces.map((p) => p.area),
      new_names: splitPieces.map((p) => p.name.trim()),
    });
    resetTool(); onChanged?.();
  }

  function toggleMergeSelect(parcelId) {
    setMergeIds((ids) => {
      const next = ids.includes(parcelId) ? ids.filter((x) => x !== parcelId) : [...ids, parcelId];
      computeMergePreview(next);
      return next;
    });
  }

  function computeMergePreview(ids) {
    setMergeError(""); setMergePreview(null);
    if (ids.length < 2) return;
    const selectedParcels = parcels.filter((p) => ids.includes(p.id));
    const farmerSet = new Set(selectedParcels.map((p) => p.farmer_id));
    if (farmerSet.size > 1) { setMergeError("Seçilen parseller farklı çiftçilere ait — birleştirilemez."); return; }
    try {
      let union = turf.polygon(selectedParcels[0].geometry.coordinates);
      for (let i = 1; i < selectedParcels.length; i++) {
        const next = turf.polygon(selectedParcels[i].geometry.coordinates);
        const result = turf.union(turf.featureCollection([union, next]));
        if (!result) throw new Error("union-failed");
        union = result;
      }
      if (union.geometry.type !== "Polygon") {
        setMergeError("Seçilen parseller bitişik değil (aralarında boşluk var) — birleştirilemez.");
        return;
      }
      setMergePreview(union.geometry);
    } catch {
      setMergeError("Parseller birleştirilemedi — geometriler bitişik/geçerli olmayabilir.");
    }
  }

  async function submitMerge() {
    if (mergeIds.length < 2 || !mergePreview) return;
    await api.post("/parcels/merge", { parcel_ids: mergeIds, merged_geometry: mergePreview });
    resetTool(); onChanged?.();
  }

  async function onImportFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportFile(file); setImportResult(null); setImportPreview(null);
    const name = (file.name || "").toLowerCase();
    if (name.endsWith(".kml") || name.endsWith(".kmz")) {
      try {
        const form = new FormData();
        form.append("file", file);
        const { data } = await api.post("/geo-import/parse", form, { headers: { "Content-Type": "multipart/form-data" } });
        const features = (data.features || []).map((f) => ({ type: "Feature", geometry: f.geometry, properties: f.properties || {} }));
        setImportPreview({ geojson: { type: "FeatureCollection", features }, count: features.length });
      } catch (err) {
        setImportPreview({ error: err.response?.data?.detail || "KML/KMZ dosyası ayrıştırılamadı" });
      }
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const gj = JSON.parse(ev.target.result);
        setImportPreview({ geojson: gj, count: (gj.features || []).length });
      } catch { setImportPreview({ error: "Geçersiz GeoJSON dosyası" }); }
    };
    reader.readAsText(file);
  }

  async function submitImport() {
    if (!importPreview?.geojson) return;
    try {
      const { data } = await api.post("/parcels/import-geojson", {
        geojson: importPreview.geojson, farmer_id: importFarmerId || null,
        default_soil_type: "Tınlı", default_irrigation: "Damla",
      });
      setImportResult(data); onChanged?.();
    } catch (err) {
      setImportResult({ error: err.response?.data?.detail || "İçe aktarma başarısız" });
    }
  }

  return {
    toolsOpen, setToolsOpen, tool, toolMsg, resetTool, activateTool,
    takbisQuick, setTakbisQuick, takbisQuickBusy, takbisQuickResult, takbisQuickMsg, queryTakbisQuick,
    drawnGeoJSON, onDrawCreated,
    editTarget, setEditTarget, editGeoJSON, submitEdit,
    splitTarget, setSplitTarget, splitPieces, setSplitPieceName, splitDrawing, setSplitDrawing, submitSplit,
    mergeIds, toggleMergeSelect, mergePreview, mergeError, submitMerge,
    pickedCoord, setPickedCoord,
    importPreview, importFarmerId, setImportFarmerId, onImportFile, submitImport, importResult,
    submitNewParcel, submitManualParcel,
    parcels, farmers,
  };
}

/** Toolbar tetikleyicisi — HaritaPaneli.jsx'in mevcut toolbar satırına
 *  (Katmanlar/Basemap/Şekille Seç ile YAN YANA) eklenir. */
export function ParcelToolsToggle({ pt }) {
  const activeCount = pt.tool ? 1 : 0;
  return (
    <div className="relative">
      <button onClick={() => pt.setToolsOpen((s) => !s)}
              className={`btn ${pt.toolsOpen || pt.tool ? "btn-primary" : "btn-ghost"} text-xs`}
              data-testid="ht-tools-menu-button">
        <Wrench size={14} /> Parsel Araçları
        {activeCount > 0 && <span className="ml-1 px-1.5 rounded-full bg-black/25 text-[10px]">{activeCount}</span>}
        <ChevronDown size={12} className={pt.toolsOpen ? "rotate-180 transition-transform" : "transition-transform"} />
      </button>
      {pt.toolsOpen && (
        <>
          <div className="fixed inset-0 z-[45]" onClick={() => pt.setToolsOpen(false)} />
          <div className="absolute left-0 mt-1 z-[46] card p-2 shadow-xl" style={{ minWidth: 280 }} data-testid="ht-tools-menu">
            {TOOLS.map((t) => (
              <button key={t.key} type="button" data-testid={`ht-tool-${t.key}`}
                      onClick={() => { pt.tool === t.key ? pt.resetTool() : pt.activateTool(t.key); pt.setToolsOpen(false); }}
                      className={`w-full text-left px-2 py-1.5 rounded text-xs flex items-center gap-2 ${
                        pt.tool === t.key ? "bg-[var(--primary)] text-black font-medium" : "hover:bg-[var(--surface-2)]"}`}>
                <t.icon size={14} /> {t.label}
              </button>
            ))}
            {pt.tool && (
              <button onClick={() => { pt.resetTool(); pt.setToolsOpen(false); }}
                      className="w-full text-left px-2 py-1.5 rounded text-xs text-red-400 hover:bg-[var(--surface-2)] flex items-center gap-2 mt-1">
                <X size={14} /> Aracı Kapat
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/** `<MapContainer>` İÇİNE render edilmesi ZORUNLU parça — çizim aracı +
 *  koordinat tıklama dinleyicisi (react-leaflet context'i gerektirir).
 *
 *  ÖNEMLİ: `MapDrawTools` kendi `L.Draw.Event.CREATED` dinleyicisini
 *  haritaya (paylaşılan Leaflet map nesnesine) `active` durumundan BAĞIMSIZ
 *  olarak, mount olur olmaz kalıcı bağlar (bkz. MapDrawTools.jsx'in "FeatureGroup
 *  + Control kurulumu — bir kere" useEffect'i, `[map]`'e bağımlı). HaritaPaneli.jsx
 *  "Şekille Seç" özelliği için ZATEN kendi `<MapDrawTools>` örneğini SÜREKLİ
 *  mount tutuyor (satır ~1298). Burada da koşulsuz mount edilseydi, HERHANGİ
 *  bir çizim tamamlandığında İKİ dinleyici de tetiklenip iki farklı akışı
 *  (parsel çizimi + Şekille Seç) birbirine karıştırırdı. Bu yüzden
 *  `MapDrawTools` SADECE ilgili parsel aracı (Çiz/Düzenle/Böl) SEÇİLİYKEN
 *  mount edilir — normal kullanımda (parsel aracı kapalı) haritaya HİÇ ek
 *  bir olay dinleyicisi eklenmez, "Şekille Seç" hiç etkilenmez. */
export function ParcelToolsMapLayer({ pt }) {
  const needsDraw = pt.tool === "draw" || pt.tool === "edit" || pt.tool === "split";
  return (
    <>
      {needsDraw && (
        <MapDrawTools
          active={pt.tool === "draw" || (pt.tool === "edit" && !!pt.editTarget) || (pt.tool === "split" && !!pt.splitTarget && pt.splitDrawing)}
          onCreated={pt.onDrawCreated}
        />
      )}
      <CoordsClickHandler active={pt.tool === "coords"} onPick={pt.setPickedCoord} />
    </>
  );
}

/** Aracın form/panel içeriği — haritanın DIŞINDA (altında/yanında) render
 *  edilir. `pt.tool` null ise hiçbir şey döndürmez. */
export function ParcelToolsSidePanel({ pt }) {
  if (!pt.tool) return null;
  return (
    <div className="card p-4 mb-4" data-testid="ht-parcel-tools-panel">
      {pt.toolMsg && <div className="text-xs text-[var(--text-dim)] mb-3 bg-[var(--surface-2)] p-2 rounded">{pt.toolMsg}</div>}

      {pt.tool === "manual" && (
        <div>
          <h3 className="font-display text-lg mb-3">Yeni Parsel (Manuel)</h3>
          <TakbisQuickBox form={pt.takbisQuick} setForm={pt.setTakbisQuick} busy={pt.takbisQuickBusy}
                          result={pt.takbisQuickResult} msg={pt.takbisQuickMsg} onQuery={pt.queryTakbisQuick} />
          <QuickAddPanel
            title="Parsel Bilgilerini Gir" testId="ht-manual-parcel-form" extraModule="parcels"
            fields={[
              { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
                options: pt.farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
              { name: "name", label: "Parsel Adı", required: true },
              { name: "village", label: "Köy", required: true },
              { name: "area_dekar", label: "Alan (dekar)", type: "number", step: "0.1", required: true },
              { name: "soil_type", label: "Toprak Tipi", type: "select", required: true, options: SOIL_TYPES.map((s) => ({ value: s, label: s })) },
              { name: "irrigation", label: "Sulama", type: "select", required: true, options: IRRIGATION_TYPES.map((s) => ({ value: s, label: s })) },
            ]}
            submitLabel="Parseli Kaydet" onSubmit={pt.submitManualParcel}
          />
        </div>
      )}

      {pt.tool === "draw" && (
        <div>
          <h3 className="font-display text-lg mb-3">Yeni Parsel</h3>
          {!pt.drawnGeoJSON ? (
            <p className="text-xs text-[var(--text-dim)]">Haritada çizim bekleniyor…</p>
          ) : (
            <>
              <TakbisQuickBox form={pt.takbisQuick} setForm={pt.setTakbisQuick} busy={pt.takbisQuickBusy}
                              result={pt.takbisQuickResult} msg={pt.takbisQuickMsg} onQuery={pt.queryTakbisQuick} />
              <QuickAddPanel
                title="Parsel Bilgilerini Gir" testId="ht-draw-parcel-form" extraModule="parcels"
                fields={[
                  { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
                    options: pt.farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
                  { name: "name", label: "Parsel Adı", required: true },
                  { name: "village", label: "Köy", required: true },
                  { name: "soil_type", label: "Toprak Tipi", type: "select", required: true, options: SOIL_TYPES.map((s) => ({ value: s, label: s })) },
                  { name: "irrigation", label: "Sulama", type: "select", required: true, options: IRRIGATION_TYPES.map((s) => ({ value: s, label: s })) },
                ]}
                submitLabel={`Kaydet (${areaFromGeoJSON(pt.drawnGeoJSON)} dekar)`} onSubmit={pt.submitNewParcel}
              />
            </>
          )}
        </div>
      )}

      {pt.tool === "edit" && (
        <div>
          <h3 className="font-display text-lg mb-3">Parsel Düzenle</h3>
          {!pt.editTarget ? (
            <div className="space-y-2 max-h-[320px] overflow-y-auto scrollbar">
              {pt.parcels.slice(0, 60).map((p) => (
                <div key={p.id} onClick={() => pt.setEditTarget(p)}
                     className="p-2.5 rounded-lg border border-[var(--border)] hover:border-[var(--primary)]/40 cursor-pointer text-sm">
                  <span className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</span> — {p.name}
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="text-sm p-2.5 rounded bg-[var(--surface-2)]">Düzenlenen: <strong>{pt.editTarget.parcel_code}</strong> — {pt.editTarget.name}</div>
              {pt.editGeoJSON ? (
                <>
                  <div className="text-xs text-[var(--text-dim)]">Yeni alan: {areaFromGeoJSON(pt.editGeoJSON)} dekar</div>
                  <button onClick={pt.submitEdit} className="btn btn-primary w-full justify-center"><Check size={14}/> Yeni Sınırı Kaydet</button>
                </>
              ) : <p className="text-xs text-[var(--text-dim)]">Haritada yeni sınırı çizin…</p>}
            </div>
          )}
        </div>
      )}

      {pt.tool === "split" && (
        <div>
          <h3 className="font-display text-lg mb-3">Parsel Böl</h3>
          {!pt.splitTarget ? (
            <div className="space-y-2 max-h-[320px] overflow-y-auto scrollbar">
              {pt.parcels.slice(0, 60).map((p) => (
                <div key={p.id} onClick={() => pt.setSplitTarget(p)}
                     className="p-2.5 rounded-lg border border-[var(--border)] hover:border-[var(--primary)]/40 cursor-pointer text-sm">
                  <span className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</span> — {p.name}
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="text-sm p-2.5 rounded bg-[var(--surface-2)]">
                Bölünen: <strong>{pt.splitTarget.parcel_code}</strong> — {pt.splitTarget.name} ({pt.splitTarget.area_dekar} dekar)
              </div>
              <div className="space-y-2">
                {pt.splitPieces.map((piece, i) => (
                  <div key={i} className="p-2 rounded bg-[var(--surface-2)] space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-[var(--text-dim)]">Yeni Parsel {i + 1} — {piece.area} dekar</span>
                    </div>
                    <input className="input text-xs" placeholder="Bu parça için parsel adı" value={piece.name}
                           onChange={(e) => pt.setSplitPieceName(i, e.target.value)} />
                  </div>
                ))}
              </div>
              {!pt.splitDrawing ? (
                <button onClick={() => pt.setSplitDrawing(true)} className="btn btn-ghost w-full justify-center text-xs"><PenLine size={14}/> Yeni Parça Çiz</button>
              ) : <p className="text-xs text-[var(--text-dim)]">Haritada çizim bekleniyor…</p>}
              {pt.splitPieces.length >= 2 && (
                <button onClick={pt.submitSplit} className="btn btn-primary w-full justify-center"><Check size={14}/> Onayla ve Böl</button>
              )}
            </div>
          )}
        </div>
      )}

      {pt.tool === "merge" && (
        <div>
          <h3 className="font-display text-lg mb-3">Parsel Birleştir</h3>
          <p className="text-xs text-[var(--text-dim)] mb-2">{pt.mergeIds.length} parsel seçildi (min. 2)</p>
          {pt.mergeError && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-2">{pt.mergeError}</div>}
          {pt.mergePreview && !pt.mergeError && (
            <div className="text-xs text-[var(--primary)] p-2 bg-[var(--primary)]/10 rounded mb-2">Önizleme hazır — geometriler bitişik.</div>
          )}
          <div className="space-y-1 mb-3 max-h-[300px] overflow-y-auto scrollbar">
            {pt.parcels.slice(0, 100).map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-xs p-1.5 rounded hover:bg-[var(--surface-2)] cursor-pointer">
                <input type="checkbox" checked={pt.mergeIds.includes(p.id)} onChange={() => pt.toggleMergeSelect(p.id)} />
                {p.parcel_code} — {p.name}
              </label>
            ))}
          </div>
          {pt.mergeIds.length >= 2 && pt.mergePreview && !pt.mergeError && (
            <button onClick={pt.submitMerge} className="btn btn-primary w-full justify-center"><Check size={14}/> Birleştirmeyi Onayla</button>
          )}
        </div>
      )}

      {pt.tool === "coords" && (
        <div>
          <h3 className="font-display text-lg mb-3">Koordinat Al</h3>
          {pt.pickedCoord ? (
            <div className="space-y-2">
              <div className="text-sm font-mono p-3 rounded bg-[var(--surface-2)]">{pt.pickedCoord.lat.toFixed(6)}, {pt.pickedCoord.lng.toFixed(6)}</div>
              <button onClick={() => navigator.clipboard?.writeText(`${pt.pickedCoord.lat.toFixed(6)}, ${pt.pickedCoord.lng.toFixed(6)}`)}
                      className="btn btn-ghost w-full justify-center text-xs">Kopyala</button>
            </div>
          ) : <p className="text-xs text-[var(--text-dim)]">Haritada bir noktaya tıklayın…</p>}
        </div>
      )}

      {pt.tool === "import" && (
        <div>
          <h3 className="font-display text-lg mb-3">Toplu Parsel İçe Aktar</h3>
          <p className="text-[11px] text-[var(--text-dim)] mb-2">
            GeoJSON (.geojson/.json), KML (.kml) veya KMZ (.kmz) — birden fazla parsel tek seferde eklenir.
          </p>
          <input type="file" accept=".geojson,.json,.kml,.kmz" onChange={pt.onImportFile} className="input mb-3 text-xs" />
          {pt.importPreview?.error && <div className="text-xs text-red-400 mb-2">{pt.importPreview.error}</div>}
          {pt.importPreview?.count != null && (
            <div className="space-y-3">
              <div className="text-xs text-[var(--text-dim)]">{pt.importPreview.count} parsel bulundu.</div>
              {(() => {
                const withTkgm = (pt.importPreview.geojson.features || []).filter((f) => mapTkgmProperties(f.properties));
                if (withTkgm.length === 0) return null;
                return <div className="text-[10px] text-[var(--primary)] p-2 rounded bg-[var(--primary)]/5">{withTkgm.length} kayıtta TKGM alanları algılandı — otomatik doldurulacak.</div>;
              })()}
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Varsayılan Çiftçi (opsiyonel)</label>
                <FarmerSelect farmers={pt.farmers} value={pt.importFarmerId || null}
                              onChange={(fid) => pt.setImportFarmerId(fid || "")} placeholder="Çiftçi ara… (boş bırakabilirsiniz)" />
              </div>
              <button onClick={pt.submitImport} className="btn btn-primary w-full justify-center"><Upload size={14}/> İçe Aktar</button>
            </div>
          )}
          {pt.importResult && (
            <div className="mt-3 text-xs p-2 rounded bg-[var(--surface-2)]">
              {pt.importResult.error ? <span className="text-red-400">{pt.importResult.error}</span> : (
                <div className="text-[var(--primary)]">{pt.importResult.created_count} parsel içe aktarıldı.</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
