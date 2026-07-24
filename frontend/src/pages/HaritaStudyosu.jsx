/**
 * HARİTA STÜDYOSU (Denetim raporu #9 / Faz 7 — Harita Stüdyosu)
 *
 * Kullanıcının kendi harita katmanlarını (dosya yükleyerek VEYA elle
 * çizerek) oluşturup stil/popup ayarladığı, bir projede birleştirip
 * yayınladığı (kendisi/organizasyon/belirli kullanıcılar/herkese açık
 * link) bağımsız bir çalışma alanı. `HaritaPaneli.jsx`'e (widget/zaman
 * makinesi merkezi) BİLİNÇLİ OLARAK DOKUNULMADI, ayrı bir sayfa.
 *
 * Çizim aracı `MapDrawTools.jsx`'i (parsel seçim/çizim akışlarına özel,
 * marker/polyline desteklemiyor) YENİDEN KULLANMADI — bu sayfaya özel,
 * kendi kendine yeten küçük bir `L.Control.Draw` sarmalayıcısı
 * (`StudioDrawControl`) yazıldı (aynı kütüphane, aynı vanilla-Leaflet
 * yaklaşımı — MapDrawTools.jsx'in stale-closure dersini ref ile
 * tekrarlıyor, ama paylaşılan bileşene dokunma riski yok).
 */
import { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";
import api from "@/api";
import Drawer from "@/components/Drawer";
import {
  Layers, Plus, Trash2, Upload, Pencil, FolderOpen, Share2, Copy,
  Eye, EyeOff, X, MapPin, Spline, Hexagon, Save, Globe,
} from "lucide-react";

const BASEMAPS = {
  dark: { label: "Koyu", url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", attribution: "&copy; OpenStreetMap &copy; CARTO" },
  light: { label: "Açık", url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", attribution: "&copy; OpenStreetMap &copy; CARTO" },
  streets: { label: "Sokak", url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: "&copy; OpenStreetMap katkıcıları" },
  satellite: { label: "Uydu", url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attribution: "Tiles &copy; Esri" },
};

function renderTemplate(tpl, props) {
  return (tpl || "").replace(/\{(\w+)\}/g, (_, k) => (props?.[k] ?? ""));
}

/** react-leaflet'in <GeoJSON> sarmalayıcısı yerine ham L.geoJSON — birden
 * fazla katmanı bağımsız stille render etmek + değişince temiz sökmek için. */
function GeoJsonLayer({ layer }) {
  const map = useMap();
  useEffect(() => {
    if (!layer?.features?.length) return undefined;
    const style = layer.style || {};
    const fc = { type: "FeatureCollection", features: layer.features.map((f) => ({ type: "Feature", geometry: f.geometry, properties: { ...f.properties, __feature_id: f.id } })) };
    const gj = L.geoJSON(fc, {
      style: () => ({ color: style.color, fillColor: style.fillColor, weight: style.weight, opacity: style.opacity, fillOpacity: style.fillOpacity }),
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
        radius: 7, color: style.color, fillColor: style.fillColor, weight: style.weight, opacity: style.opacity, fillOpacity: style.fillOpacity,
      }),
      onEachFeature: (feature, l) => {
        const cfg = layer.popup_config || {};
        const title = renderTemplate(cfg.title_template, feature.properties);
        const rows = (cfg.fields || []).map((f) => `<div><b>${f}:</b> ${feature.properties?.[f] ?? "—"}</div>`).join("");
        l.bindPopup(`<div style="min-width:150px"><div style="font-weight:600;margin-bottom:4px">${title || layer.name}</div>${rows}</div>`);
      },
    });
    gj.addTo(map);
    return () => map.removeLayer(gj);
  }, [map, layer]);
  return null;
}

/** Bu sayfaya özel çizim kontrolü — marker/polyline/polygon + düzenle/sil.
 * `targetLayerId` null iken kontrol haritada GÖRÜNMEZ (hedef katman
 * seçilmeden çizim anlamsız). */
function StudioDrawControl({ targetLayerId, onCreated }) {
  const map = useMap();
  const drawnRef = useRef(null);
  const controlRef = useRef(null);
  const onCreatedRef = useRef(onCreated);
  onCreatedRef.current = onCreated;

  useEffect(() => {
    const drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);
    drawnRef.current = drawnItems;
    const control = new L.Control.Draw({
      position: "topright",
      draw: {
        marker: true, polyline: { shapeOptions: { color: "#22C55E" } },
        polygon: { allowIntersection: false, shapeOptions: { color: "#22C55E" } },
        rectangle: false, circle: false, circlemarker: false,
      },
      edit: { featureGroup: drawnItems, remove: false },
    });
    controlRef.current = control;
    const handleCreated = (e) => {
      const geojson = e.layer.toGeoJSON();
      onCreatedRef.current && onCreatedRef.current(geojson.geometry);
      // Kalıcı feature backend'e yazıldıktan sonra proje yeniden yüklendiğinde
      // GeoJsonLayer zaten gösterecek — geçici çizimi haritada BİRİKTİRMEMEK
      // için hemen kaldırılıyor.
      drawnItems.removeLayer(e.layer);
    };
    map.on(L.Draw.Event.CREATED, handleCreated);
    return () => {
      map.off(L.Draw.Event.CREATED, handleCreated);
      try { map.removeControl(control); } catch { /* zaten kaldırılmış olabilir */ }
      map.removeLayer(drawnItems);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  useEffect(() => {
    if (!controlRef.current) return;
    if (targetLayerId) map.addControl(controlRef.current);
    else { try { map.removeControl(controlRef.current); } catch { /* zaten kaldırılmış */ } }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetLayerId, map]);

  return null;
}

const emptyLayerForm = {
  name: "", color: "#3B82F6", fillColor: "#3B82F6", weight: 2, opacity: 1, fillOpacity: 0.3,
  title_template: "", fields: "",
};

export default function HaritaStudyosu() {
  const [layers, setLayers] = useState([]);
  const [projects, setProjects] = useState([]);
  const [openProject, setOpenProject] = useState(null); // {project, layers: {id: layer+features}}
  const [basemapKey, setBasemapKey] = useState("dark");

  const [layerFormOpen, setLayerFormOpen] = useState(false);
  const [layerForm, setLayerForm] = useState(emptyLayerForm);
  const [editingLayer, setEditingLayer] = useState(null);

  const [uploadLayerId, setUploadLayerId] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);
  const [epsgCodes, setEpsgCodes] = useState([]);
  const [uploadEpsg, setUploadEpsg] = useState("");
  const [uploading, setUploading] = useState(false);

  const [newProjectName, setNewProjectName] = useState("");
  const [drawTargetLayerId, setDrawTargetLayerId] = useState("");

  const [publishOpen, setPublishOpen] = useState(false);
  const [publishForm, setPublishForm] = useState({ share_scope: "private", shared_unit_id: "", shared_user_ids_text: "", is_public: false });
  const [orgUnits, setOrgUnits] = useState([]);
  const [publishResult, setPublishResult] = useState(null);

  const [error, setError] = useState("");

  const loadLayers = () => api.get("/map-layers").then((r) => setLayers(r.data));
  const loadProjects = () => api.get("/map-projects").then((r) => setProjects(r.data));

  useEffect(() => {
    loadLayers();
    loadProjects();
    api.get("/geo-import/epsg-codes").then((r) => setEpsgCodes(r.data)).catch(() => setEpsgCodes([]));
    api.get("/organization-units").then((r) => setOrgUnits(r.data)).catch(() => setOrgUnits([]));
  }, []);

  async function saveLayer(e) {
    e.preventDefault();
    setError("");
    const body = {
      name: layerForm.name,
      style: {
        color: layerForm.color, fillColor: layerForm.fillColor,
        weight: Number(layerForm.weight), opacity: Number(layerForm.opacity), fillOpacity: Number(layerForm.fillOpacity),
      },
      popup_config: {
        title_template: layerForm.title_template,
        fields: layerForm.fields.split(",").map((f) => f.trim()).filter(Boolean),
      },
    };
    try {
      if (editingLayer) await api.put(`/map-layers/${editingLayer.id}`, body);
      else await api.post("/map-layers", { ...body, source_type: "drawn" });
      setLayerFormOpen(false); setEditingLayer(null); setLayerForm(emptyLayerForm);
      loadLayers();
    } catch (err) {
      setError(err.response?.data?.detail || "Katman kaydedilemedi");
    }
  }

  function openEditLayer(l) {
    setEditingLayer(l);
    setLayerForm({
      name: l.name, color: l.style?.color || "#3B82F6", fillColor: l.style?.fillColor || "#3B82F6",
      weight: l.style?.weight ?? 2, opacity: l.style?.opacity ?? 1, fillOpacity: l.style?.fillOpacity ?? 0.3,
      title_template: l.popup_config?.title_template || "", fields: (l.popup_config?.fields || []).join(", "),
    });
    setLayerFormOpen(true);
  }

  async function deleteLayer(l) {
    if (!window.confirm(`"${l.name}" katmanı (ve tüm kayıtları) silinsin mi?`)) return;
    await api.delete(`/map-layers/${l.id}`);
    loadLayers();
  }

  async function doUpload() {
    if (!uploadFile || !uploadLayerId) return;
    setUploading(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      if (uploadEpsg) fd.append("source_epsg", uploadEpsg);
      const { data } = await api.post(`/map-layers/${uploadLayerId}/import`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setUploadLayerId(null); setUploadFile(null); setUploadEpsg("");
      loadLayers();
      if (openProject) openTheProject(openProject.project.id);
      alert(`${data.imported} kayıt içe aktarıldı.`);
    } catch (err) {
      setError(err.response?.data?.detail || "İçe aktarılamadı");
    } finally {
      setUploading(false);
    }
  }

  async function createProject(e) {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    const { data } = await api.post("/map-projects", { name: newProjectName.trim(), layers: [], center: [39.0, 35.0], zoom: 6 });
    setNewProjectName("");
    loadProjects();
    openTheProject(data.id);
  }

  async function openTheProject(id) {
    const { data } = await api.get(`/map-projects/${id}/full`);
    setOpenProject(data);
    setBasemapKey(data.project.basemap_key || "dark");
  }

  async function deleteProject(p) {
    if (!window.confirm(`"${p.name}" projesi silinsin mi?`)) return;
    await api.delete(`/map-projects/${p.id}`);
    if (openProject?.project.id === p.id) setOpenProject(null);
    loadProjects();
  }

  function addLayerToProject(layerId) {
    if (!openProject || !layerId) return;
    const already = openProject.project.layers.some((l) => l.layer_id === layerId);
    if (already) return;
    setOpenProject((op) => ({
      ...op,
      project: { ...op.project, layers: [...op.project.layers, { layer_id: layerId, visible: true, order: op.project.layers.length, opacity: 1 }] },
    }));
  }

  function updateProjectLayerRef(layerId, patch) {
    setOpenProject((op) => ({
      ...op,
      project: { ...op.project, layers: op.project.layers.map((l) => (l.layer_id === layerId ? { ...l, ...patch } : l)) },
    }));
  }

  function removeLayerFromProject(layerId) {
    setOpenProject((op) => ({ ...op, project: { ...op.project, layers: op.project.layers.filter((l) => l.layer_id !== layerId) } }));
  }

  async function saveProject() {
    if (!openProject) return;
    await api.put(`/map-projects/${openProject.project.id}`, {
      layers: openProject.project.layers, basemap_key: basemapKey,
    });
    loadProjects();
    openTheProject(openProject.project.id);
  }

  async function handleFeatureCreated(geometry) {
    if (!drawTargetLayerId) return;
    await api.post(`/map-layers/${drawTargetLayerId}/features`, { geometry, properties: {} });
    loadLayers();
    if (openProject) openTheProject(openProject.project.id);
  }

  function openPublish() {
    if (!openProject) return;
    const p = openProject.project;
    setPublishForm({
      share_scope: p.share_scope || "private", shared_unit_id: p.shared_unit_id || "",
      shared_user_ids_text: (p.shared_user_ids || []).join(", "), is_public: !!p.is_public,
    });
    setPublishResult(null);
    setPublishOpen(true);
  }

  async function doPublish() {
    const body = {
      share_scope: publishForm.share_scope,
      shared_unit_id: publishForm.share_scope === "org_unit" ? publishForm.shared_unit_id : null,
      shared_user_ids: publishForm.share_scope === "users"
        ? publishForm.shared_user_ids_text.split(",").map((s) => s.trim()).filter(Boolean) : [],
      is_public: publishForm.is_public,
    };
    const { data } = await api.post(`/map-projects/${openProject.project.id}/share`, body);
    setPublishResult(data);
    loadProjects();
  }

  function copyPublicLink() {
    if (!publishResult?.public_token) return;
    navigator.clipboard?.writeText(`${window.location.origin}/harita/${publishResult.public_token}`);
  }

  const layersById = openProject?.layers || {};
  const projectLayerRefs = openProject?.project.layers || [];
  const availableToAdd = layers.filter((l) => !projectLayerRefs.some((r) => r.layer_id === l.id));

  return (
    <div className="p-8 max-w-[1600px]" data-testid="harita-studyosu-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SAHA & LOJİSTİK</div>
        <h1 className="font-display text-4xl">Harita Stüdyosu</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Kendi harita katmanlarınızı oluşturun (dosya yükleyerek veya çizerek), stil ve popup'ları
          özelleştirin, bir projede birleştirip yayınlayın.
        </p>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr_280px] gap-4">
        {/* SOL: Katmanlarım + Projelerim */}
        <div className="space-y-4">
          <div className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display text-base flex items-center gap-1.5"><Layers size={15} className="text-[var(--primary)]"/>Katmanlarım</h3>
              <button onClick={() => { setEditingLayer(null); setLayerForm(emptyLayerForm); setLayerFormOpen(true); }} className="btn btn-ghost text-xs" data-testid="new-layer-btn">
                <Plus size={12}/> Yeni
              </button>
            </div>
            <div className="space-y-1.5">
              {layers.map((l) => (
                <div key={l.id} className="p-2 bg-[var(--surface-2)] rounded-lg text-xs" data-testid={`map-layer-${l.id}`}>
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full shrink-0" style={{ background: l.style?.color }}/>
                    <span className="flex-1 truncate">{l.name}</span>
                    <span className="text-[var(--text-dim)]">{l.feature_count}</span>
                  </div>
                  <div className="flex items-center gap-1 mt-1.5">
                    <button onClick={() => openEditLayer(l)} className="btn btn-ghost !px-1.5 !py-0.5 text-[10px]"><Pencil size={10}/></button>
                    <button onClick={() => setUploadLayerId(l.id)} className="btn btn-ghost !px-1.5 !py-0.5 text-[10px]"><Upload size={10}/></button>
                    {openProject && (
                      <button onClick={() => addLayerToProject(l.id)} className="btn btn-ghost !px-1.5 !py-0.5 text-[10px]">Projeye Ekle</button>
                    )}
                    <button onClick={() => deleteLayer(l)} className="btn btn-ghost !px-1.5 !py-0.5 text-[10px] text-red-400 ml-auto"><Trash2 size={10}/></button>
                  </div>
                </div>
              ))}
              {layers.length === 0 && <div className="text-xs text-[var(--text-dim)] text-center py-3">Henüz katman yok</div>}
            </div>
          </div>

          <div className="card p-4">
            <h3 className="font-display text-base flex items-center gap-1.5 mb-3"><FolderOpen size={15} className="text-[var(--primary)]"/>Projelerim</h3>
            <form onSubmit={createProject} className="flex items-center gap-1.5 mb-3">
              <input className="input flex-1 !py-1.5 !text-xs" placeholder="Yeni proje adı" value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)}/>
              <button type="submit" className="btn btn-primary !px-2 !py-1.5"><Plus size={12}/></button>
            </form>
            <div className="space-y-1.5">
              {projects.map((p) => (
                <div key={p.id} className={`p-2 rounded-lg text-xs ${openProject?.project.id === p.id ? "bg-[var(--primary)]/15 border border-[var(--primary)]/40" : "bg-[var(--surface-2)]"}`}>
                  <div className="flex items-center justify-between">
                    <button onClick={() => openTheProject(p.id)} className="flex-1 text-left truncate hover:underline">{p.name}</button>
                    <button onClick={() => deleteProject(p)} className="text-[var(--text-dim)] hover:text-red-400"><Trash2 size={11}/></button>
                  </div>
                </div>
              ))}
              {projects.length === 0 && <div className="text-xs text-[var(--text-dim)] text-center py-3">Henüz proje yok</div>}
            </div>
          </div>
        </div>

        {/* ORTA: Harita */}
        <div className="card overflow-hidden" style={{ height: "640px" }}>
          <div className="flex items-center gap-2 p-2 border-b border-[var(--border)] flex-wrap">
            <select className="input !py-1 !text-xs w-28" value={basemapKey} onChange={(e) => setBasemapKey(e.target.value)}>
              {Object.entries(BASEMAPS).map(([k, b]) => <option key={k} value={k}>{b.label}</option>)}
            </select>
            <select className="input !py-1 !text-xs flex-1" value={drawTargetLayerId} onChange={(e) => setDrawTargetLayerId(e.target.value)} data-testid="draw-target-select">
              <option value="">Çizim hedef katmanı seç...</option>
              {layers.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
            {drawTargetLayerId && (
              <span className="text-[10px] text-[var(--text-dim)] flex items-center gap-1">
                <MapPin size={10}/><Spline size={10}/><Hexagon size={10}/> sağ üstteki araçlarla çizin
              </span>
            )}
          </div>
          <MapContainer center={[39.0, 35.0]} zoom={6} style={{ height: "calc(100% - 41px)", width: "100%" }}>
            <TileLayer url={BASEMAPS[basemapKey].url} attribution={BASEMAPS[basemapKey].attribution}/>
            {projectLayerRefs.filter((r) => r.visible).map((r) => layersById[r.layer_id] && (
              <GeoJsonLayer key={r.layer_id} layer={layersById[r.layer_id]}/>
            ))}
            <StudioDrawControl targetLayerId={drawTargetLayerId} onCreated={handleFeatureCreated}/>
          </MapContainer>
        </div>

        {/* SAĞ: açık projenin katman listesi */}
        <div className="card p-4">
          {!openProject ? (
            <div className="text-xs text-[var(--text-dim)] text-center py-6">Bir proje açın veya yeni oluşturun</div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-display text-sm truncate">{openProject.project.name}</h3>
                <button onClick={openPublish} className="btn btn-ghost !px-2 !py-1 text-[10px]" data-testid="publish-project-btn"><Share2 size={11}/></button>
              </div>
              <div className="space-y-1.5 mb-3">
                {projectLayerRefs.map((r) => {
                  const layer = layersById[r.layer_id];
                  return (
                    <div key={r.layer_id} className="p-2 bg-[var(--surface-2)] rounded-lg text-xs">
                      <div className="flex items-center gap-1.5">
                        <button onClick={() => updateProjectLayerRef(r.layer_id, { visible: !r.visible })}>
                          {r.visible ? <Eye size={12}/> : <EyeOff size={12} className="text-[var(--text-dim)]"/>}
                        </button>
                        <span className="flex-1 truncate">{layer?.name || r.layer_id.slice(0, 8)}</span>
                        <button onClick={() => removeLayerFromProject(r.layer_id)} className="text-[var(--text-dim)] hover:text-red-400"><X size={11}/></button>
                      </div>
                      <input type="range" min="0" max="1" step="0.1" value={r.opacity} className="w-full mt-1"
                             onChange={(e) => updateProjectLayerRef(r.layer_id, { opacity: Number(e.target.value) })}/>
                    </div>
                  );
                })}
                {projectLayerRefs.length === 0 && <div className="text-[10px] text-[var(--text-dim)]">Sol taraftan "Projeye Ekle" ile katman ekleyin</div>}
              </div>
              {availableToAdd.length > 0 && (
                <select className="input !py-1 !text-xs w-full mb-2" value="" onChange={(e) => addLayerToProject(e.target.value)}>
                  <option value="">+ Katman ekle...</option>
                  {availableToAdd.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              )}
              <button onClick={saveProject} className="btn btn-primary text-xs w-full flex items-center justify-center gap-1.5" data-testid="save-project-btn">
                <Save size={12}/> Projeyi Kaydet
              </button>
            </>
          )}
        </div>
      </div>

      {/* KATMAN OLUŞTUR/DÜZENLE */}
      <Drawer open={layerFormOpen} onClose={() => setLayerFormOpen(false)} title={editingLayer ? "Katmanı Düzenle" : "Yeni Katman"}>
        <form onSubmit={saveLayer} className="p-4 space-y-3">
          <input className="input" placeholder="Katman adı" required value={layerForm.name} onChange={(e) => setLayerForm((f) => ({ ...f, name: e.target.value }))}/>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-[var(--text-dim)]">Çizgi Rengi
              <input type="color" className="input h-9" value={layerForm.color} onChange={(e) => setLayerForm((f) => ({ ...f, color: e.target.value }))}/>
            </label>
            <label className="text-xs text-[var(--text-dim)]">Dolgu Rengi
              <input type="color" className="input h-9" value={layerForm.fillColor} onChange={(e) => setLayerForm((f) => ({ ...f, fillColor: e.target.value }))}/>
            </label>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <label className="text-xs text-[var(--text-dim)]">Kalınlık
              <input type="number" min="1" max="10" className="input" value={layerForm.weight} onChange={(e) => setLayerForm((f) => ({ ...f, weight: e.target.value }))}/>
            </label>
            <label className="text-xs text-[var(--text-dim)]">Opaklık
              <input type="number" min="0" max="1" step="0.1" className="input" value={layerForm.opacity} onChange={(e) => setLayerForm((f) => ({ ...f, opacity: e.target.value }))}/>
            </label>
            <label className="text-xs text-[var(--text-dim)]">Dolgu Opaklığı
              <input type="number" min="0" max="1" step="0.1" className="input" value={layerForm.fillOpacity} onChange={(e) => setLayerForm((f) => ({ ...f, fillOpacity: e.target.value }))}/>
            </label>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Popup Başlık Şablonu (ör. {"{ad}"})</label>
            <input className="input" value={layerForm.title_template} onChange={(e) => setLayerForm((f) => ({ ...f, title_template: e.target.value }))}/>
          </div>
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Popup'ta Gösterilecek Alanlar (virgülle ayır)</label>
            <input className="input" placeholder="ad, aciklama, alan" value={layerForm.fields} onChange={(e) => setLayerForm((f) => ({ ...f, fields: e.target.value }))}/>
          </div>
          <button type="submit" className="btn btn-primary w-full" data-testid="save-layer-btn">Kaydet</button>
        </form>
      </Drawer>

      {/* DOSYA YÜKLE */}
      <Drawer open={!!uploadLayerId} onClose={() => setUploadLayerId(null)} title="Dosyadan İçe Aktar">
        <div className="p-4 space-y-3">
          <div className="text-xs text-[var(--text-dim)]">
            Desteklenen türler: GeoJSON, KML, KMZ, SHP (.zip), DXF, CSV (lat/lon sütunlu).
          </div>
          <input type="file" className="input" onChange={(e) => setUploadFile(e.target.files?.[0] || null)}/>
          {(uploadFile?.name.endsWith(".zip") || uploadFile?.name.endsWith(".dxf")) && (
            <select className="input" value={uploadEpsg} onChange={(e) => setUploadEpsg(e.target.value)}>
              <option value="">Kaynak koordinat sistemi (EPSG) seç...</option>
              {epsgCodes.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
            </select>
          )}
          <button onClick={doUpload} disabled={!uploadFile || uploading} className="btn btn-primary w-full" data-testid="do-upload-btn">
            {uploading ? "İçe aktarılıyor…" : "İçe Aktar"}
          </button>
        </div>
      </Drawer>

      {/* YAYINLA */}
      <Drawer open={publishOpen} onClose={() => setPublishOpen(false)} title={`Yayınla: ${openProject?.project.name || ""}`}>
        <div className="p-4 space-y-3">
          <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Kurum İçi Görünürlük</div>
          <div className="space-y-1.5">
            {[
              { v: "private", l: "Sadece Ben" },
              { v: "org_unit", l: "Organizasyon Birimim" },
              { v: "users", l: "Belirli Kullanıcılar" },
              { v: "tenant", l: "Kurum Geneli" },
            ].map((o) => (
              <label key={o.v} className="flex items-center gap-2 text-sm">
                <input type="radio" name="share_scope" checked={publishForm.share_scope === o.v}
                       onChange={() => setPublishForm((f) => ({ ...f, share_scope: o.v }))}/>
                {o.l}
              </label>
            ))}
          </div>
          {publishForm.share_scope === "org_unit" && (
            <select className="input" value={publishForm.shared_unit_id} onChange={(e) => setPublishForm((f) => ({ ...f, shared_unit_id: e.target.value }))}>
              <option value="">Birim seç...</option>
              {orgUnits.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          )}
          {publishForm.share_scope === "users" && (
            <input className="input" placeholder="Kullanıcı ID'leri (virgülle ayır)"
                   value={publishForm.shared_user_ids_text}
                   onChange={(e) => setPublishForm((f) => ({ ...f, shared_user_ids_text: e.target.value }))}/>
          )}

          <label className="flex items-center gap-2 text-sm pt-2 border-t border-[var(--border)]">
            <input type="checkbox" checked={publishForm.is_public} onChange={(e) => setPublishForm((f) => ({ ...f, is_public: e.target.checked }))}/>
            <Globe size={13}/> Herkese açık link oluştur (login gerekmez)
          </label>

          <button onClick={doPublish} className="btn btn-primary w-full" data-testid="do-publish-btn">Yayınla</button>

          {publishResult && (
            <div className="bg-[var(--surface-2)] rounded-lg p-3 space-y-2">
              {publishResult.is_public ? (
                <>
                  <div className="text-xs text-[var(--text-dim)]">Herkese açık bağlantı:</div>
                  <div className="flex items-center gap-2">
                    <input className="input flex-1 text-xs" readOnly value={`${window.location.origin}/harita/${publishResult.public_token}`}/>
                    <button onClick={copyPublicLink} className="btn btn-ghost text-xs"><Copy size={12}/></button>
                  </div>
                </>
              ) : (
                <div className="text-xs text-[var(--text-dim)]">Güncellendi — herkese açık link kapalı.</div>
              )}
            </div>
          )}
        </div>
      </Drawer>
    </div>
  );
}
