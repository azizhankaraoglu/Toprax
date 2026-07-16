import { useEffect, useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "@/api";
import { MapContainer, TileLayer, Polygon, Popup, Marker, useMapEvents } from "react-leaflet";
import * as turf from "@turf/turf";
import { MapDrawTools } from "@/components/MapDrawTools";
import { QuickAddPanel } from "@/components/QuickAdd";
import { mapTkgmProperties } from "@/lib/tkgmMapping";
import {
  PenLine, Scissors, Combine, Crosshair, Upload, X, Check, Layers, Plus
} from "lucide-react";

const RISK_COLORS = { yesil: "#4ade80", sari: "#fbbf24", turuncu: "#fb923c", kirmizi: "#ef4444" };
const RISK_LABELS = { yesil: "Düşük Risk", sari: "İzlemeye Değer", turuncu: "Riskli", kirmizi: "Acil Müdahale" };

function RiskBadge({ level, label }) {
  const color = RISK_COLORS[level] || "#97a8a0";
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded font-medium" style={{ background: `${color}22`, color }}>
      {label || RISK_LABELS[level] || "—"}
    </span>
  );
}

/** Harita üzerinde tıklanan noktanın koordinatını yakalar ("Koordinat Al" aracı) */
function CoordsClickHandler({ active, onPick }) {
  useMapEvents({
    click(e) {
      if (active) onPick(e.latlng);
    },
  });
  return null;
}

const areaFromGeoJSON = (geojson) => Math.round((turf.area(geojson) / 1000) * 10) / 10; // m² → dekar

export default function Parcels() {
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [parcels, setParcels] = useState([]);
  const [farmers, setFarmers] = useState([]);
  const [selected, setSelected] = useState(null);

  // Aktif araç: null | "draw" | "edit" | "split" | "merge" | "coords" | "import"
  const [tool, setTool] = useState(null);
  const [toolMsg, setToolMsg] = useState("");

  // ÇİZ
  const [drawnGeoJSON, setDrawnGeoJSON] = useState(null);

  // DÜZENLE (mevcut parseli yeniden çizerek geometriyi değiştirme)
  const [editTarget, setEditTarget] = useState(null);
  const [editGeoJSON, setEditGeoJSON] = useState(null);

  // BÖL
  const [splitTarget, setSplitTarget] = useState(null);
  const [splitPieces, setSplitPieces] = useState([]); // [{geojson, area}]
  const [splitDrawing, setSplitDrawing] = useState(false);

  // BİRLEŞTİR
  const [mergeIds, setMergeIds] = useState([]);
  const [mergePreview, setMergePreview] = useState(null); // geojson geometry
  const [mergeError, setMergeError] = useState("");

  // KOORDİNAT AL
  const [pickedCoord, setPickedCoord] = useState(null);

  // GEOJSON IMPORT
  const [importFile, setImportFile] = useState(null);
  const [importPreview, setImportPreview] = useState(null);
  const [importFarmerId, setImportFarmerId] = useState("");
  const [importResult, setImportResult] = useState(null);

  // İDARİ SINIR KATMANI — IT-13.6 Layer v1 (aç/kapa, sadeleştirilmiş geometri)
  const [showAdminAreas, setShowAdminAreas] = useState(false);
  const [adminAreas, setAdminAreas] = useState([]);

  const load = useCallback(() => {
    api.get("/parcels", { params: { limit: 1200 } }).then((r) => setParcels(r.data));
  }, []);

  useEffect(() => {
    if (showAdminAreas && adminAreas.length === 0) {
      api.get("/admin-areas").then((r) => setAdminAreas(r.data));
    }
  }, [showAdminAreas, adminAreas.length]);

  useEffect(() => {
    load();
    api.get("/farmers", { params: { limit: 500 } }).then((r) => setFarmers(r.data));
  }, [load]);

  function resetTool() {
    setTool(null);
    setToolMsg("");
    setDrawnGeoJSON(null);
    setEditTarget(null);
    setEditGeoJSON(null);
    setSplitTarget(null);
    setSplitPieces([]);
    setSplitDrawing(false);
    setMergeIds([]);
    setMergePreview(null);
    setMergeError("");
    setPickedCoord(null);
    setImportFile(null);
    setImportPreview(null);
    setImportResult(null);
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
      import: "Bir .geojson dosyası seçin — TKGM Parsel Sorgu'dan (parselsorgu.tkgm.gov.tr) dışa aktardığınız dosyalar da desteklenir, il/ilçe/mahalle/ada/parsel bilgileri otomatik tanınır.",
    };
    setToolMsg(msgs[t] || "");
  }

  // ============ ÇİZ: yeni parsel oluştur ============
  function onDrawCreated(layer, geojson) {
    if (tool === "draw") {
      setDrawnGeoJSON(geojson);
    } else if (tool === "edit" && editTarget) {
      setEditGeoJSON(geojson);
    } else if (tool === "split" && splitTarget) {
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
      ...extra,                                              // IT-02 dinamik alanlar (ada_no, il, ilçe, ...)
      farmer_id,
      name,
      village,
      region_id: farmers.find((f) => f.id === farmer_id)?.region_id,
      area_dekar: area,
      soil_type,
      irrigation,
      geometry: drawnGeoJSON.geometry,
    });
    resetTool();
    load();
  }

  async function submitManualParcel(values) {
    // Harita çizimi olmadan, sadece formla — geometry boş bırakılır,
    // istenirse sonra "Düzenle" aracıyla haritada çizilebilir.
    const { farmer_id, name, village, area_dekar, soil_type, irrigation, ...extra } = values;
    await api.post("/parcels", {
      ...extra,                                              // IT-02 dinamik alanlar (ada_no, il, ilçe, ...)
      farmer_id,
      name,
      village,
      region_id: farmers.find((f) => f.id === farmer_id)?.region_id,
      area_dekar: Number(area_dekar),
      soil_type,
      irrigation,
      geometry: null,
    });
    resetTool();
    load();
  }

  async function submitEdit() {
    if (!editTarget || !editGeoJSON) return;
    const area = areaFromGeoJSON(editGeoJSON);
    await api.put(`/parcels/${editTarget.id}`, { geometry: editGeoJSON.geometry, area_dekar: area });
    resetTool();
    load();
  }

  async function submitSplit() {
    if (!splitTarget || splitPieces.length < 2) return;
    if (splitPieces.some((p) => !p.name?.trim())) {
      setToolMsg("Her parça için bir isim girmelisiniz.");
      return;
    }
    await api.post(`/parcels/${splitTarget.id}/split`, {
      new_geometries: splitPieces.map((p) => p.geojson.geometry),
      new_areas_dekar: splitPieces.map((p) => p.area),
      new_names: splitPieces.map((p) => p.name.trim()),
    });
    resetTool();
    load();
  }

  function toggleMergeSelect(parcelId) {
    setMergeIds((ids) => {
      const next = ids.includes(parcelId) ? ids.filter((x) => x !== parcelId) : [...ids, parcelId];
      computeMergePreview(next);
      return next;
    });
  }

  function computeMergePreview(ids) {
    setMergeError("");
    setMergePreview(null);
    if (ids.length < 2) return;
    const selectedParcels = parcels.filter((p) => ids.includes(p.id));
    const farmerSet = new Set(selectedParcels.map((p) => p.farmer_id));
    if (farmerSet.size > 1) {
      setMergeError("Seçilen parseller farklı çiftçilere ait — birleştirilemez.");
      return;
    }
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
    resetTool();
    load();
  }

  function onImportFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportFile(file);
    setImportResult(null);
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const gj = JSON.parse(ev.target.result);
        const count = (gj.features || []).length;
        setImportPreview({ geojson: gj, count });
      } catch {
        setImportPreview({ error: "Geçersiz GeoJSON dosyası" });
      }
    };
    reader.readAsText(file);
  }

  async function submitImport() {
    if (!importPreview?.geojson) return;
    try {
      const { data } = await api.post("/parcels/import-geojson", {
        geojson: importPreview.geojson,
        farmer_id: importFarmerId || null,
        default_soil_type: "Tınlı",
        default_irrigation: "Damla",
      });
      setImportResult(data);
      load();
    } catch (err) {
      setImportResult({ error: err.response?.data?.detail || "İçe aktarma başarısız" });
    }
  }

  const totalArea = parcels.reduce((s, p) => s + (p.area_dekar || 0), 0);
  const riskyCount = parcels.filter((p) => p.risk_level === "turuncu" || p.risk_level === "kirmizi").length;

  // KONU 3 (drill-down): Dashboard "Riskli Parsel" kartı /parseller?risk=1 ile
  // gelir; harita ve liste yalnızca riskli parselleri gösterir (CLAUDE.md Kural 5).
  const riskOnly = searchParams.get("risk") === "1";
  const visibleParcels = riskOnly
    ? parcels.filter((p) => p.risk_level === "turuncu" || p.risk_level === "kirmizi")
    : parcels;

  const TOOLS = [
    { key: "manual", icon: Plus, label: "Manuel Ekle" },
    { key: "draw", icon: PenLine, label: "Parsel Çiz" },
    { key: "edit", icon: Layers, label: "Düzenle" },
    { key: "split", icon: Scissors, label: "Böl" },
    { key: "merge", icon: Combine, label: "Birleştir" },
    { key: "coords", icon: Crosshair, label: "Koordinat Al" },
    { key: "import", icon: Upload, label: "GeoJSON / TKGM İçe Aktar" },
  ];

  return (
    <div className="p-8 max-w-[1700px]" data-testid="parcels-page">
      <header className="mb-4 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">ARAZİ HARİTASI</div>
          <h1 className="font-display text-4xl">Parseller</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            {parcels.length} parsel · {totalArea.toFixed(0)} dekar toplam
            {riskyCount > 0 && <span className="text-red-400"> · {riskyCount} riskli parsel</span>}
          </p>
          {riskOnly && (
            <div className="mt-2 inline-flex items-center gap-2 text-xs bg-red-500/10 text-red-400 px-2.5 py-1 rounded">
              <span className="w-2 h-2 rounded-full bg-red-400 inline-block" /> Yalnızca riskli parseller ({visibleParcels.length})
              <button className="underline hover:text-red-300" onClick={() => setSearchParams({})}>Tümünü göster</button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs text-[var(--text-dim)]">
          {Object.entries(RISK_COLORS).map(([level, color]) => (
            <span key={level} className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: color }}/>
              {RISK_LABELS[level]}
            </span>
          ))}
        </div>
      </header>

      {/* HARİTA ARAÇLARI TOOLBAR */}
      <div className="flex flex-wrap gap-2 mb-3">
        {TOOLS.map((t) => (
          <button
            key={t.key}
            onClick={() => (tool === t.key ? resetTool() : activateTool(t.key))}
            className={`btn ${tool === t.key ? "btn-primary" : "btn-ghost"} text-xs`}
            data-testid={`tool-${t.key}`}
          >
            <t.icon size={14}/> {t.label}
          </button>
        ))}
        {tool && (
          <button onClick={resetTool} className="btn btn-ghost text-xs text-red-400">
            <X size={14}/> Aracı Kapat
          </button>
        )}
        <button
          onClick={() => setShowAdminAreas((s) => !s)}
          className={`btn ${showAdminAreas ? "btn-primary" : "btn-ghost"} text-xs`}
          data-testid="toggle-admin-areas-layer"
        >
          <Layers size={14}/> İdari Sınırlar
        </button>
      </div>
      {toolMsg && (
        <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mb-3">
          {toolMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3 card overflow-hidden relative" style={{ height: 640 }}>
          <MapContainer center={[39.0, 33.5]} zoom={7} style={{ height: "100%", width: "100%" }}>
            <TileLayer
              attribution='&copy; OpenStreetMap'
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            />

            {/* İdari Sınırlar katmanı — IT-13.6 Layer v1 (aç/kapa) */}
            {showAdminAreas && adminAreas.map((a) => {
              if (!a.geometry) return null;
              const rings = a.geometry.type === "MultiPolygon" ? a.geometry.coordinates.flat() : a.geometry.coordinates;
              return rings.map((ring, i) => (
                <Polygon
                  key={`${a.id}-${i}`}
                  positions={ring.map(([lng, lat]) => [lat, lng])}
                  pathOptions={{ color: "#60a5fa", fillOpacity: 0, weight: 2, dashArray: "6 4" }}
                >
                  <Popup>
                    <div style={{ minWidth: 140 }}>
                      <div style={{ fontWeight: 600 }}>{a.name}</div>
                      <div style={{ fontSize: 12, opacity: 0.8 }}>{a.area_type}</div>
                    </div>
                  </Popup>
                </Polygon>
              ));
            })}

            {/* Mevcut parseller */}
            {visibleParcels.map((p) => {
              if (!p.geometry) return null;
              const isMergeSelected = mergeIds.includes(p.id);
              const isEditOrSplitTarget = editTarget?.id === p.id || splitTarget?.id === p.id;
              const color = isMergeSelected ? "#a78bfa" : (RISK_COLORS[p.risk_level] || "#4ade80");
              return (
                <Polygon
                  key={p.id}
                  positions={p.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])}
                  pathOptions={{
                    color,
                    fillColor: color,
                    fillOpacity: isEditOrSplitTarget ? 0.1 : (isMergeSelected ? 0.5 : 0.4),
                    weight: isMergeSelected || isEditOrSplitTarget ? 3 : 1.5,
                    dashArray: isEditOrSplitTarget ? "6 4" : undefined,
                  }}
                  eventHandlers={{
                    click: () => {
                      if (tool === "merge") toggleMergeSelect(p.id);
                      else if (tool === "edit") { setEditTarget(p); setToolMsg("Şimdi yeni sınırı çizin."); }
                      else if (tool === "split") { setSplitTarget(p); setToolMsg("Şimdi parçaları tek tek çizin (en az 2)."); }
                      else setSelected(p);
                    }
                  }}
                >
                  {!tool && (
                    <Popup>
                      <div style={{ minWidth: 180 }}>
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>{p.parcel_code}</div>
                        <div style={{ fontSize: 12, opacity: 0.8 }}>{p.name}</div>
                        <div style={{ fontSize: 12, marginTop: 6 }}>
                          <strong>{p.area_dekar.toFixed(1)}</strong> dekar · {p.soil_type}
                        </div>
                        <div style={{ fontSize: 12 }}>Sulama: {p.irrigation}</div>
                        {p.ndvi_latest && <div style={{ fontSize: 12 }}>NDVI: {p.ndvi_latest} · {RISK_LABELS[p.risk_level]}</div>}
                      </div>
                    </Popup>
                  )}
                </Polygon>
              );
            })}

            {/* Çizim aracı (yeni parsel / düzenleme / bölme parçası) */}
            <MapDrawTools
              active={tool === "draw" || (tool === "edit" && !!editTarget) || (tool === "split" && !!splitTarget && splitDrawing)}
              mode="polygon"
              onCreated={onDrawCreated}
            />

            {/* Birleştirme önizlemesi */}
            {mergePreview && (
              <Polygon
                positions={mergePreview.coordinates[0].map(([lng, lat]) => [lat, lng])}
                pathOptions={{ color: "#a78bfa", fillColor: "#a78bfa", fillOpacity: 0.25, weight: 3, dashArray: "8 4" }}
              />
            )}

            {/* Bölme parçaları önizlemesi */}
            {splitPieces.map((piece, i) => (
              <Polygon
                key={i}
                positions={piece.geojson.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])}
                pathOptions={{ color: "#60a5fa", fillColor: "#60a5fa", fillOpacity: 0.35, weight: 2 }}
              />
            ))}

            {/* Koordinat al */}
            <CoordsClickHandler active={tool === "coords"} onPick={setPickedCoord} />
            {pickedCoord && <Marker position={[pickedCoord.lat, pickedCoord.lng]} />}
          </MapContainer>
        </div>

        {/* SAĞ PANEL — aktif araca göre değişir */}
        <div className="card p-4 overflow-y-auto scrollbar" style={{ maxHeight: 640 }}>
          {!tool && (
            <>
              <h3 className="font-display text-lg mb-3">Parsel Listesi</h3>
              <div className="space-y-2">
                {visibleParcels.slice(0, 60).map((p) => (
                  <div
                    key={p.id}
                    onClick={() => nav(`/parseller/${p.id}`)}
                    className={`p-3 rounded-lg cursor-pointer border transition-colors ${
                      selected?.id === p.id
                        ? "border-[var(--primary)] bg-[var(--primary)]/5"
                        : "border-[var(--border)] hover:border-[var(--primary)]/40"
                    }`}
                    data-testid={`parcel-${p.parcel_code}`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</div>
                      <div className="text-xs text-[var(--primary)]">{p.area_dekar.toFixed(1)} da</div>
                    </div>
                    <div className="text-sm mt-1">{p.name}</div>
                    <div className="text-xs text-[var(--text-dim)] mt-1">{p.village} · {p.soil_type} · {p.irrigation}</div>
                    {p.risk_level && <div className="mt-1.5"><RiskBadge level={p.risk_level} label={p.risk_label} /></div>}
                  </div>
                ))}
              </div>
            </>
          )}

          {tool === "manual" && (
            <div>
              <h3 className="font-display text-lg mb-3">Yeni Parsel (Manuel)</h3>
              <QuickAddPanel
                title="Parsel Bilgilerini Gir"
                testId="manual-parcel-form"
                extraModule="parcels"
                fields={[
                  { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
                    options: farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
                  { name: "name", label: "Parsel Adı", required: true },
                  { name: "village", label: "Köy", required: true },
                  { name: "area_dekar", label: "Alan (dekar)", type: "number", step: "0.1", required: true },
                  { name: "soil_type", label: "Toprak Tipi", type: "select", required: true,
                    options: ["Killi", "Kumlu", "Tınlı", "Kireçli", "Killi-Tınlı"].map((s) => ({ value: s, label: s })) },
                  { name: "irrigation", label: "Sulama", type: "select", required: true,
                    options: ["Damla", "Yağmurlama", "Karık", "Yok"].map((s) => ({ value: s, label: s })) },
                ]}
                submitLabel="Parseli Kaydet"
                onSubmit={submitManualParcel}
              />
              <p className="text-xs text-[var(--text-dim)] mt-2">
                Sınırlar haritada gösterilmeyecek — istediğinizde "Düzenle" aracıyla sonradan çizebilirsiniz.
              </p>
            </div>
          )}

          {tool === "draw" && (
            <div>
              <h3 className="font-display text-lg mb-3">Yeni Parsel</h3>
              {!drawnGeoJSON ? (
                <p className="text-xs text-[var(--text-dim)]">Haritada çizim bekleniyor…</p>
              ) : (
                <QuickAddPanel
                  title="Parsel Bilgilerini Gir"
                  testId="draw-parcel-form"
                  extraModule="parcels"
                  fields={[
                    { name: "farmer_id", label: "Çiftçi", type: "select", required: true,
                      options: farmers.map((f) => ({ value: f.id, label: `${f.full_name} (${f.member_no})` })) },
                    { name: "name", label: "Parsel Adı", required: true },
                    { name: "village", label: "Köy", required: true },
                    { name: "soil_type", label: "Toprak Tipi", type: "select", required: true,
                      options: ["Killi", "Kumlu", "Tınlı", "Kireçli", "Killi-Tınlı"].map((s) => ({ value: s, label: s })) },
                    { name: "irrigation", label: "Sulama", type: "select", required: true,
                      options: ["Damla", "Yağmurlama", "Karık", "Yok"].map((s) => ({ value: s, label: s })) },
                  ]}
                  submitLabel={`Kaydet (${areaFromGeoJSON(drawnGeoJSON)} dekar)`}
                  onSubmit={submitNewParcel}
                />
              )}
            </div>
          )}

          {tool === "edit" && (
            <div>
              <h3 className="font-display text-lg mb-3">Parsel Düzenle</h3>
              {!editTarget ? (
                <div className="space-y-2">
                  {parcels.slice(0, 40).map((p) => (
                    <div key={p.id} onClick={() => setEditTarget(p)}
                         className="p-2.5 rounded-lg border border-[var(--border)] hover:border-[var(--primary)]/40 cursor-pointer text-sm">
                      <span className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</span> — {p.name}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="text-sm p-2.5 rounded bg-[var(--surface-2)]">
                    Düzenlenen: <strong>{editTarget.parcel_code}</strong> — {editTarget.name}
                  </div>
                  {editGeoJSON ? (
                    <>
                      <div className="text-xs text-[var(--text-dim)]">Yeni alan: {areaFromGeoJSON(editGeoJSON)} dekar</div>
                      <button onClick={submitEdit} className="btn btn-primary w-full justify-center">
                        <Check size={14}/> Yeni Sınırı Kaydet
                      </button>
                    </>
                  ) : (
                    <p className="text-xs text-[var(--text-dim)]">Haritada yeni sınırı çizin…</p>
                  )}
                </div>
              )}
            </div>
          )}

          {tool === "split" && (
            <div>
              <h3 className="font-display text-lg mb-3">Parsel Böl</h3>
              {!splitTarget ? (
                <div className="space-y-2">
                  {parcels.slice(0, 40).map((p) => (
                    <div key={p.id} onClick={() => setSplitTarget(p)}
                         className="p-2.5 rounded-lg border border-[var(--border)] hover:border-[var(--primary)]/40 cursor-pointer text-sm">
                      <span className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</span> — {p.name}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="text-sm p-2.5 rounded bg-[var(--surface-2)]">
                    Bölünen: <strong>{splitTarget.parcel_code}</strong> — {splitTarget.name} ({splitTarget.area_dekar} dekar)
                  </div>
                  <div className="space-y-2">
                    {splitPieces.map((piece, i) => (
                      <div key={i} className="p-2 rounded bg-[var(--surface-2)] space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-[var(--text-dim)]">Yeni Parsel {i + 1} — {piece.area} dekar</span>
                          <button onClick={() => setSplitPieces((ps) => ps.filter((_, idx) => idx !== i))} className="text-red-400">
                            <X size={12}/>
                          </button>
                        </div>
                        <input
                          className="input text-xs"
                          placeholder="Bu parça için parsel adı"
                          value={piece.name}
                          onChange={(e) => setSplitPieceName(i, e.target.value)}
                          data-testid={`split-piece-name-${i}`}
                        />
                      </div>
                    ))}
                  </div>
                  {!splitDrawing ? (
                    <button onClick={() => setSplitDrawing(true)} className="btn btn-ghost w-full justify-center text-xs">
                      <PenLine size={14}/> Yeni Parça Çiz
                    </button>
                  ) : (
                    <p className="text-xs text-[var(--text-dim)]">Haritada çizim bekleniyor…</p>
                  )}
                  {splitPieces.length >= 2 && (
                    <div className="p-3 rounded-lg border border-[var(--primary)]/30 bg-[var(--primary)]/5 space-y-2">
                      <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Özet — Onaylamadan Önce Kontrol Edin</div>
                      <div className="text-xs">
                        <span className="text-red-400">Silinecek:</span> {splitTarget.name} ({splitTarget.area_dekar} dekar)
                      </div>
                      <div className="text-xs space-y-0.5">
                        <span className="text-[var(--primary)]">Oluşturulacak {splitPieces.length} yeni parsel:</span>
                        {splitPieces.map((p, i) => (
                          <div key={i} className="pl-2">• {p.name || `(isimsiz parça ${i + 1})`} — {p.area} dekar</div>
                        ))}
                      </div>
                      <button onClick={submitSplit} className="btn btn-primary w-full justify-center">
                        <Check size={14}/> Onayla ve Böl
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {tool === "merge" && (
            <div>
              <h3 className="font-display text-lg mb-3">Parsel Birleştir</h3>
              <p className="text-xs text-[var(--text-dim)] mb-2">Haritadan {mergeIds.length} parsel seçildi (min. 2)</p>
              {mergeError && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-2">{mergeError}</div>}
              {mergePreview && !mergeError && (
                <div className="text-xs text-[var(--primary)] p-2 bg-[var(--primary)]/10 rounded mb-2">
                  Önizleme hazır — haritada mor renkte gösteriliyor.
                </div>
              )}
              <div className="space-y-2 mb-3 max-h-[300px] overflow-y-auto scrollbar">
                {parcels.filter((p) => mergeIds.includes(p.id)).map((p) => (
                  <div key={p.id} className="flex items-center justify-between text-xs p-2 rounded bg-[var(--surface-2)]">
                    <span>{p.parcel_code} — {p.name}</span>
                    <button onClick={() => toggleMergeSelect(p.id)} className="text-red-400"><X size={12}/></button>
                  </div>
                ))}
              </div>
              {mergeIds.length >= 2 && mergePreview && !mergeError && (
                <button onClick={submitMerge} className="btn btn-primary w-full justify-center">
                  <Check size={14}/> Birleştirmeyi Onayla
                </button>
              )}
            </div>
          )}

          {tool === "coords" && (
            <div>
              <h3 className="font-display text-lg mb-3">Koordinat Al</h3>
              {pickedCoord ? (
                <div className="space-y-2">
                  <div className="text-sm font-mono p-3 rounded bg-[var(--surface-2)]">
                    {pickedCoord.lat.toFixed(6)}, {pickedCoord.lng.toFixed(6)}
                  </div>
                  <button
                    onClick={() => navigator.clipboard?.writeText(`${pickedCoord.lat.toFixed(6)}, ${pickedCoord.lng.toFixed(6)}`)}
                    className="btn btn-ghost w-full justify-center text-xs"
                  >
                    Kopyala
                  </button>
                </div>
              ) : (
                <p className="text-xs text-[var(--text-dim)]">Haritada bir noktaya tıklayın…</p>
              )}
            </div>
          )}

          {tool === "import" && (
            <div>
              <h3 className="font-display text-lg mb-3">GeoJSON / TKGM İçe Aktar</h3>
              <input type="file" accept=".geojson,.json" onChange={onImportFile} className="input mb-3 text-xs" />
              {importPreview?.error && <div className="text-xs text-red-400 mb-2">{importPreview.error}</div>}
              {importPreview?.count != null && (
                <div className="space-y-3">
                  <div className="text-xs text-[var(--text-dim)]">{importPreview.count} parsel bulundu.</div>
                  {(() => {
                    const withTkgm = (importPreview.geojson.features || [])
                      .filter((f) => mapTkgmProperties(f.properties));
                    if (withTkgm.length === 0) return null;
                    return (
                      <div className="text-[10px] text-[var(--primary)] p-2 rounded bg-[var(--primary)]/5">
                        {withTkgm.length} kayıtta TKGM alanları (il/ilçe/mahalle/ada/parsel) algılandı — otomatik doldurulacak.
                      </div>
                    );
                  })()}
                  <div>
                    <label className="text-xs text-[var(--text-dim)] mb-1 block">
                      Varsayılan Çiftçi (feature.properties.farmer_id yoksa kullanılır)
                    </label>
                    <select className="input" value={importFarmerId} onChange={(e) => setImportFarmerId(e.target.value)}>
                      <option value="">Seç...</option>
                      {farmers.map((f) => <option key={f.id} value={f.id}>{f.full_name} ({f.member_no})</option>)}
                    </select>
                  </div>
                  <button onClick={submitImport} className="btn btn-primary w-full justify-center">
                    <Upload size={14}/> İçe Aktar
                  </button>
                </div>
              )}
              {importResult && (
                <div className="mt-3 text-xs p-2 rounded bg-[var(--surface-2)]">
                  {importResult.error ? (
                    <span className="text-red-400">{importResult.error}</span>
                  ) : (
                    <>
                      <div className="text-[var(--primary)]">{importResult.created_count} parsel içe aktarıldı.</div>
                      {importResult.errors?.length > 0 && (
                        <div className="text-amber-400 mt-1">{importResult.errors.length} kayıt atlandı.</div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
