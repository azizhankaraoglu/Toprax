import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import AdminAreaPopupLinks from "@/components/AdminAreaPopupLinks";
import MapClickAdminPopup from "@/components/MapClickAdminPopup";
import api from "@/api";
import { MapContainer, TileLayer, Polygon, Popup, Marker, useMapEvents, useMap } from "react-leaflet";
import * as turf from "@turf/turf";
import { MapDrawTools } from "@/components/MapDrawTools";
import { QuickAddPanel } from "@/components/QuickAdd";
import { mapTkgmProperties } from "@/lib/tkgmMapping";
import FarmerSelect from "@/components/FarmerSelect";
import BulkRemoteSensing from "@/components/BulkRemoteSensing";
import ParcelsListPanel from "@/components/ParcelsListPanel";
import AiAssistantBox from "@/components/AiAssistantBox";
import { getTheme } from "@/lib/theme";
import { BASEMAPS, getStoredBasemap, storeBasemap } from "@/lib/basemaps";
import {
  PenLine, Scissors, Combine, Crosshair, Upload, X, Check, Layers, Plus, Satellite, List,
  ClipboardPlus, Landmark, Wrench, ChevronDown, Map as MapIcon,
} from "lucide-react";

const RISK_COLORS = { yesil: "#4ade80", sari: "#fbbf24", turuncu: "#fb923c", kirmizi: "#ef4444" };
const RISK_LABELS = { yesil: "Düşük Risk", sari: "İzlemeye Değer", turuncu: "Riskli", kirmizi: "Acil Müdahale" };

/**
 * HARİTA LEJANTI — parsel poligonlarındaki renklerin ne anlama geldiğini
 * haritanın ÜZERİNDE açıklar. Renkler tek kaynaktan (RISK_COLORS) okunur;
 * poligon çizimindeki (aşağıda) sabitlerle elle senkron tutulması gereken
 * tek yerler seçim/birleştirme/idari sınır renkleridir.
 */
function MapLegend({ showAdminAreas, mergeActive }) {
  const [open, setOpen] = useState(true);
  const swatch = (style) => (
    <span className="w-3.5 h-3.5 rounded-sm inline-block shrink-0 border" style={style} />
  );
  const rows = [
    ...Object.entries(RISK_COLORS).map(([level, c]) => ({
      key: level,
      node: swatch({ background: `${c}66`, borderColor: c }),
      label: RISK_LABELS[level],
    })),
    { key: "bilinmiyor", node: swatch({ background: "#4ade8066", borderColor: "#4ade80" }),
      label: "Risk verisi yok (varsayılan)" },
    { key: "secili", node: swatch({ background: "transparent", borderColor: "var(--text)", borderWidth: 3 }),
      label: "Seçili parsel (kalın dış çizgi)" },
    ...(mergeActive
      ? [{ key: "merge", node: swatch({ background: "#a78bfa66", borderColor: "#a78bfa" }),
           label: "Birleştirmek için seçildi" }]
      : []),
    ...(showAdminAreas
      ? [{ key: "idari", node: swatch({ background: "transparent", borderColor: "#60a5fa", borderStyle: "dashed" }),
           label: "İdari sınır (kesikli mavi)" }]
      : []),
  ];
  return (
    <div className="absolute bottom-3 left-3 z-[500] card p-0 overflow-hidden shadow-lg"
         style={{ maxWidth: 240 }} data-testid="harita-lejanti">
      <button type="button" onClick={() => setOpen((o) => !o)}
              className="w-full flex items-center justify-between gap-2 px-3 py-2 text-[11px] uppercase tracking-wider text-[var(--text-dim)] hover:text-[var(--text)]">
        Lejant <span>{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 flex flex-col gap-1.5">
          {rows.map((r) => (
            <span key={r.key} className="flex items-center gap-2 text-[11px] leading-tight">
              {r.node}{r.label}
            </span>
          ))}
          <span className="text-[10px] text-[var(--text-dim)] pt-1 border-t border-[var(--border)]">
            Renk, parselin uydu/NDVI tabanlı risk seviyesini gösterir.
          </span>
        </div>
      )}
    </div>
  );
}

/** Araçlar menüsündeki tek satır. */
function MenuItem({ icon: Icon, label, active, onClick, testId }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId}
            className={`w-full text-left px-2 py-1.5 rounded text-xs flex items-center gap-2 ${
              active ? "bg-[var(--primary)] text-black font-medium" : "hover:bg-[var(--surface-2)]"}`}>
      <Icon size={14} /> {label}
    </button>
  );
}

/**
 * HARİTA ÜZERİ KONTROL PANELİ — Katmanlar + Altlık.
 *
 * Kullanıcı isteği (2026-08-19): idari sınır kutucukları sayfanın üstündeki
 * toolbar'dan haritanın ÜZERİNE, KALICI bir katman kontrolüne taşınsın; ayrıca
 * Parseller haritasında da (Harita Paneli'nde olduğu gibi) altlık seçimi olsun.
 */
function MapControls({
  basemapKey, setBasemapKey,
  showParcels, setShowParcels,
  showAdminAreas, setShowAdminAreas,
  adminLevels, setAdminLevels,
  adminCounts, adminLoading, adminCount,
}) {
  const [panel, setPanel] = useState(null); // "layers" | "basemap" | null
  const Btn = ({ id, icon: Icon, label }) => (
    <button type="button" onClick={() => setPanel(panel === id ? null : id)}
            data-testid={`map-ctrl-${id}`}
            className={`btn text-xs ${panel === id ? "btn-primary" : "btn-ghost"}`}>
      <Icon size={13} /> {label}
    </button>
  );

  return (
    <div className="absolute top-3 right-3 z-[500] flex flex-col items-end gap-2" data-testid="map-controls">
      <div className="flex gap-1.5">
        <Btn id="layers" icon={Layers} label="Katmanlar" />
        <Btn id="basemap" icon={MapIcon} label="Altlık" />
      </div>

      {panel === "layers" && (
        <div className="card p-3 shadow-xl" style={{ minWidth: 230 }} data-testid="layers-panel">
          <label className="flex items-center gap-2 text-xs cursor-pointer py-1">
            <input type="checkbox" checked={showParcels}
                   onChange={(e) => setShowParcels(e.target.checked)} data-testid="layer-parcels" />
            Parseller
          </label>
          <label className="flex items-center gap-2 text-xs cursor-pointer py-1">
            <input type="checkbox" checked={showAdminAreas}
                   onChange={(e) => setShowAdminAreas(e.target.checked)}
                   data-testid="toggle-admin-areas-layer" />
            İdari Sınırlar
          </label>
          {showAdminAreas && (
            <div className="pl-5 mt-1 flex flex-col gap-1 border-l border-[var(--border)]"
                 data-testid="admin-level-picker">
              {[["il", "İl"], ["ilce", "İlçe"], ["mahalle", "Mahalle"]].map(([key, label]) => (
                <label key={key} className="flex items-center gap-1.5 text-[11px] cursor-pointer">
                  <input type="checkbox" checked={!!adminLevels[key]}
                         onChange={(e) => setAdminLevels((s) => ({ ...s, [key]: e.target.checked }))}
                         data-testid={`admin-level-${key}`} />
                  {label}
                  {adminCounts?.[key] != null && (
                    <span className="text-[var(--text-dim)]">({adminCounts[key].toLocaleString("tr-TR")})</span>
                  )}
                </label>
              ))}
              <span className="text-[10px] text-[var(--text-dim)] mt-1">
                {adminLoading ? "yükleniyor…" : `${adminCount} sınır çizili`}
              </span>
              <span className="text-[10px] text-[var(--text-dim)]">
                İlçe/mahalle yalnızca parsellerin bulunduğu bölgede yüklenir.
              </span>
            </div>
          )}
        </div>
      )}

      {panel === "basemap" && (
        <div className="card p-2 shadow-xl" style={{ minWidth: 150 }} data-testid="basemap-panel">
          {Object.entries(BASEMAPS).map(([key, b]) => (
            <button key={key} type="button"
                    onClick={() => { setBasemapKey(key); storeBasemap("parcels", key); }}
                    data-testid={`basemap-${key}`}
                    className={`w-full text-left px-2 py-1.5 rounded text-xs ${
                      basemapKey === key ? "bg-[var(--primary)] text-black font-medium" : "hover:bg-[var(--surface-2)]"}`}>
              {b.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

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

/** SON HAL — listeden seçilen parsele haritayı uçurur (liste↔harita senkronu).
 *  Sadece useEffect kullanır — CLAUDE.md'deki useMapEvents stale-closure
 *  tuzağı burada geçerli değil (event handler bağlanmıyor). */
function MapFlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (!target?.geometry?.coordinates?.[0]?.[0]) return;
    try {
      const c = turf.centroid(target.geometry).geometry.coordinates;
      map.flyTo([c[1], c[0]], Math.max(map.getZoom(), 13), { duration: 0.6 });
    } catch { /* geometri bozuksa sessizce geç */ }
  }, [target, map]);
  return null;
}

export default function Parcels() {
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [parcels, setParcels] = useState([]);
  const [farmers, setFarmers] = useState([]);
  const [selected, setSelected] = useState(null);

  // Aktif araç: null | "draw" | "edit" | "split" | "merge" | "coords" | "import"
  const [tool, setTool] = useState(null);
  const [toolMsg, setToolMsg] = useState("");
  const [showBulkRS, setShowBulkRS] = useState(false);   // Toplu Uzaktan Algılama paneli
  const [showList, setShowList] = useState(false);       // Liste & Filtre & Toplu Silme paneli (#3)

  // Denetim eklentisi (2026-07-25) — kullanıcı isteği: TAKBİS parsel EKLEME
  // formuna da eklensin (öncesinde sadece ParcelDetail.jsx düzenleme modunda
  // vardı). Sorgu-öncesi referans amaçlı — sonucu görüp form alanlarına
  // (Köy/Alan) elle taşıyabilir, backend /gov/takbis/query hiçbir şey YAZMAZ.
  const [takbisQuick, setTakbisQuick] = useState({ il: "", ilce: "", ada: "", parsel: "" });
  const [takbisQuickBusy, setTakbisQuickBusy] = useState(false);
  const [takbisQuickResult, setTakbisQuickResult] = useState(null);
  const [takbisQuickMsg, setTakbisQuickMsg] = useState("");
  async function queryTakbisQuick() {
    setTakbisQuickBusy(true);
    setTakbisQuickMsg("");
    setTakbisQuickResult(null);
    try {
      const { data } = await api.post("/gov/takbis/query", takbisQuick);
      setTakbisQuickResult(data);
      if (!data.found) setTakbisQuickMsg("Kayıt bulunamadı.");
    } catch (err) {
      setTakbisQuickMsg(err.response?.data?.detail || "TAKBİS sorgusu başarısız.");
    } finally {
      setTakbisQuickBusy(false);
    }
  }

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
  //
  // 2026-08-19 — SEVİYE SEÇİCİ GERİ GELDİ. Gerçek Türkiye verisi yüklendikten
  // sonra koleksiyonda 81 il + 971 ilçe + 50.130 mahalle var; hepsini birden
  // çizmek hem okunmaz bir harita hem ağır bir istek demek. Kullanıcı hangi
  // seviyeyi istediğini seçer (varsayılan: il + ilçe), veriler harita görünür
  // alanına göre (`bbox`) çekilir.
  const [showAdminAreas, setShowAdminAreas] = useState(false);
  const [adminLevels, setAdminLevels] = useState({ il: true, ilce: true, mahalle: false });
  // 2026-08-19 — harita üzeri kontroller: altlık seçimi (kalıcı) + parsel
  // katmanı aç/kapa + "Araçlar" menüsünün açık/kapalı durumu.
  const [basemapKey, setBasemapKey] = useState(() => getStoredBasemap("parcels"));
  const [showParcels, setShowParcels] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [adminAreas, setAdminAreas] = useState([]);
  const [adminCounts, setAdminCounts] = useState(null);
  const [adminLoading, setAdminLoading] = useState(false);

  // SON HAL — sabit lookup filtre çubuğu (DB'deki gerçek distinct değerler).
  // Dashboard drill-down'ları URL parametresiyle gelir (?ekili=evet|hayir,
  // ?il=, ?ilce= — CLAUDE.md Kural 11 drill-down konvansiyonu).
  const [filterOpts, setFilterOpts] = useState(null);
  const [lf, setLf] = useState(() => ({
    il: searchParams.get("il") || "",
    ilce: searchParams.get("ilce") || "",
    mahalle: "", ada: "", parsel: "", areaMin: "", areaMax: "",
    ekili: ["evet", "hayir"].includes(searchParams.get("ekili")) ? searchParams.get("ekili") : "",
  }));
  // SON HAL — AI asistanı sonucu (id kümesi; null = filtre yok)
  const [aiIds, setAiIds] = useState(null);
  // SON HAL — parselin en güncel sözleşmesi (popup "Sözleşme detayına git")
  const [contractByParcel, setContractByParcel] = useState(new Map());
  // SON HAL — popup içi "Görev ata" mini formu
  const [taskForm, setTaskForm] = useState(null); // {parcelId, task_type, date, msg}
  // 2026-08-19 — popup'ta "Parsel" seçilince açılan işlem menüsü (parcel id)
  const [popupParcelOpen, setPopupParcelOpen] = useState(null);

  const load = useCallback(() => {
    api.get("/parcels", { params: { limit: 1200 } }).then((r) => setParcels(r.data));
  }, []);

  // Seçili seviyeleri, parsellerin kapladığı alana göre yükler. Parseller
  // zaten yüklendiği için sınırı onlardan hesaplıyoruz — haritanın anlık
  // görünümüne bağlamak her kaydırmada yeni istek demek olurdu.
  const parcelBBox = useMemo(() => {
    const pts = [];
    parcels.forEach((p) => {
      const g = p.geometry;
      if (!g) return;
      (function walk(c) {
        if (typeof c[0] === "number") pts.push(c);
        else c.forEach(walk);
      })(g.coordinates || []);
    });
    if (pts.length === 0) return null;
    const lons = pts.map((p) => p[0]);
    const lats = pts.map((p) => p[1]);
    const pad = 0.05;
    return [Math.min(...lons) - pad, Math.min(...lats) - pad,
            Math.max(...lons) + pad, Math.max(...lats) + pad].join(",");
  }, [parcels]);

  // 2026-08-19 — "İdari sınırlarda sadece Konya geliyor" şikâyetinin sebebi:
  // bbox PARSELLERİN kapladığı alandan türetiliyordu ve tüm parseller Konya'da,
  // dolayısıyla başka hiçbir ilin sınırı hiç istenmiyordu. Artık İL seviyesi
  // bbox'SIZ çekilir (81 kayıt — tamamı gelir, kullanıcı ülke genelinde
  // gezinebilir); ilçe/mahalle ise (971 / 50.130 kayıt) performans için
  // bbox ile sınırlı kalır.
  useEffect(() => {
    if (!showAdminAreas) return;
    const levels = Object.entries(adminLevels).filter(([, on]) => on).map(([k]) => k);
    if (levels.length === 0) { setAdminAreas([]); return; }
    setAdminLoading(true);
    Promise.all(levels.map((lvl) =>
      api.get("/admin-areas", {
        params: {
          area_type: lvl,
          bbox: lvl === "il" ? undefined : (parcelBBox || undefined),
          limit: lvl === "il" ? 100 : 1200,
        },
      }).then((r) => r.data).catch(() => [])
    )).then((lists) => setAdminAreas(lists.flat())).finally(() => setAdminLoading(false));
  }, [showAdminAreas, adminLevels, parcelBBox]);

  useEffect(() => {
    if (showAdminAreas && !adminCounts) {
      api.get("/admin-areas/counts").then((r) => setAdminCounts(r.data)).catch(() => {});
    }
  }, [showAdminAreas, adminCounts]);

  useEffect(() => {
    load();
    api.get("/farmers", { params: { limit: 500 } }).then((r) => setFarmers(r.data));
    api.get("/parcels/filter-options").then((r) => setFilterOpts(r.data)).catch(() => {});
    api.get("/contracts").then((r) => {
      const m = new Map();
      (Array.isArray(r.data) ? r.data : []).forEach((c) => {
        const cur = m.get(c.parcel_id);
        if (!cur || (c.season || 0) > (cur.season || 0)) m.set(c.parcel_id, c);
      });
      setContractByParcel(m);
    }).catch(() => {});
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
      import: "Bir .geojson, .kml veya .kmz dosyası seçin — birden fazla parseli tek seferde içe aktarır. TKGM Parsel Sorgu'dan (parselsorgu.tkgm.gov.tr) dışa aktardığınız dosyalar ve KML/KMZ içindeki öznitelikler (il/ilçe/mahalle/ada/parsel) otomatik tanınıp parsel bilgilerine yazılır.",
    };
    setToolMsg(msgs[t] || "");
  }

  // ============ ÇİZ: yeni parsel oluştur ============
  function onDrawCreated(layer, geojson) {
    // Denetim (2026-07-24): topoloji ön-kontrolü — kendi kendini kesen çizim
    // backend'de zaten 400 ile reddedilir (geo_validation.py), burada erken
    // ve anlaşılır bir uyarı verilir (turf.kinks self-intersection noktalarını bulur).
    try {
      const kinks = turf.kinks(turf.polygon(geojson.geometry.coordinates));
      if (kinks?.features?.length > 0) {
        alert("Çizilen şekil kendisiyle kesişiyor — kenarlar birbirinin üzerinden geçmemeli. Lütfen şekli yeniden çizin.");
        return;
      }
    } catch { /* turf geometriyi okuyamazsa backend doğrulaması yakalar */ }
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

  async function onImportFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportFile(file);
    setImportResult(null);
    setImportPreview(null);
    const name = (file.name || "").toLowerCase();

    // KML/KMZ: tarayıcıda ayrıştıramayız (KMZ bir zip, KML XML) — backend'in
    // /geo-import/parse ucuna yükleyip dönen feature'ları bir GeoJSON
    // FeatureCollection'a çevirir, mevcut toplu import akışına besleriz.
    if (name.endsWith(".kml") || name.endsWith(".kmz")) {
      try {
        const form = new FormData();
        form.append("file", file);
        const { data } = await api.post("/geo-import/parse", form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        const features = (data.features || []).map((f) => ({
          type: "Feature",
          geometry: f.geometry,
          properties: f.properties || {},
        }));
        setImportPreview({ geojson: { type: "FeatureCollection", features }, count: features.length });
      } catch (err) {
        setImportPreview({ error: err.response?.data?.detail || "KML/KMZ dosyası ayrıştırılamadı" });
      }
      return;
    }

    // GeoJSON/JSON: tarayıcıda doğrudan okunur.
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

  // SON HAL — görünür küme: risk drill-down ∩ sabit lookup filtreleri ∩ AI sonucu.
  // Sayfa zaten tüm parselleri çekiyor (mevcut kalıp) — filtreleme client-side.
  const visibleParcels = useMemo(() => {
    let list = riskOnly
      ? parcels.filter((p) => p.risk_level === "turuncu" || p.risk_level === "kirmizi")
      : parcels;
    if (lf.il) list = list.filter((p) => p.il === lf.il);
    if (lf.ilce) list = list.filter((p) => p.ilce === lf.ilce);
    if (lf.mahalle) list = list.filter((p) => (p.mahalle || p.village) === lf.mahalle);
    if (lf.ada) list = list.filter((p) => String(p.ada_no || "") === lf.ada);
    if (lf.parsel) list = list.filter((p) => String(p.parsel_no_tapu || "").includes(lf.parsel));
    if (lf.areaMin !== "") list = list.filter((p) => (p.area_dekar || 0) >= Number(lf.areaMin));
    if (lf.areaMax !== "") list = list.filter((p) => (p.area_dekar || 0) <= Number(lf.areaMax));
    if (lf.ekili === "evet") list = list.filter((p) => p.ekim_durumu === "ekili");
    if (lf.ekili === "hayir") list = list.filter((p) => p.ekim_durumu !== "ekili");
    if (aiIds) list = list.filter((p) => aiIds.has(p.id));
    return list;
  }, [parcels, riskOnly, lf, aiIds]);

  const lookupActive = Object.values(lf).some((v) => v !== "") || aiIds;

  const TOOLS = [
    { key: "manual", icon: Plus, label: "Manuel Ekle" },
    { key: "draw", icon: PenLine, label: "Parsel Çiz" },
    { key: "edit", icon: Layers, label: "Düzenle" },
    { key: "split", icon: Scissors, label: "Böl" },
    { key: "merge", icon: Combine, label: "Birleştir" },
    { key: "coords", icon: Crosshair, label: "Koordinat Al" },
    { key: "import", icon: Upload, label: "Toplu İçe Aktar (GeoJSON/KML/KMZ)" },
  ];

  // Menü kapalıyken kaç şeyin açık olduğunu düğmenin üzerinde göstermek için.
  const activeToolCount = (tool ? 1 : 0) + (showList ? 1 : 0) + (showBulkRS ? 1 : 0);

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

      {/* SON HAL — SABİT LOOKUP FİLTRE ÇUBUĞU (DB'deki gerçek değerlerden) */}
      <div className="card p-4 mb-3" data-testid="parcel-lookup-bar">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
          <select className="input" value={lf.il} data-testid="lf-il"
                  onChange={(e) => setLf({ ...lf, il: e.target.value, ilce: "", mahalle: "" })}>
            <option value="">İl (tümü)</option>
            {(filterOpts?.il || []).map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select className="input" value={lf.ilce} data-testid="lf-ilce"
                  onChange={(e) => setLf({ ...lf, ilce: e.target.value, mahalle: "" })}>
            <option value="">İlçe (tümü)</option>
            {(lf.il ? (filterOpts?.ilce_by_il?.[lf.il] || []) : (filterOpts?.ilce || []))
              .map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select className="input" value={lf.mahalle} data-testid="lf-mahalle"
                  onChange={(e) => setLf({ ...lf, mahalle: e.target.value })}>
            <option value="">Mahalle/Köy (tümü)</option>
            {(lf.ilce ? (filterOpts?.mahalle_by_ilce?.[lf.ilce] || []) : (filterOpts?.mahalle || []))
              .map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select className="input" value={lf.ada} data-testid="lf-ada"
                  onChange={(e) => setLf({ ...lf, ada: e.target.value })}>
            <option value="">Ada (tümü)</option>
            {(filterOpts?.ada || []).map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <input className="input" placeholder="Parsel no" value={lf.parsel} data-testid="lf-parsel"
                 onChange={(e) => setLf({ ...lf, parsel: e.target.value })} />
          <input className="input" type="number" placeholder={`Yüzölçümü min${filterOpts ? ` (${filterOpts.area_min})` : ""}`}
                 value={lf.areaMin} data-testid="lf-area-min"
                 onChange={(e) => setLf({ ...lf, areaMin: e.target.value })} />
          <input className="input" type="number" placeholder={`Yüzölçümü max${filterOpts ? ` (${filterOpts.area_max})` : ""}`}
                 value={lf.areaMax} data-testid="lf-area-max"
                 onChange={(e) => setLf({ ...lf, areaMax: e.target.value })} />
          <select className="input" value={lf.ekili} data-testid="lf-ekili"
                  onChange={(e) => setLf({ ...lf, ekili: e.target.value })}>
            <option value="">Ekili mi? (tümü)</option>
            <option value="evet">Evet</option>
            <option value="hayir">Hayır</option>
          </select>
        </div>
        {lookupActive && (
          <div className="mt-2 flex items-center gap-2 text-xs text-[var(--text-dim)]">
            <span><b className="text-white">{visibleParcels.length}</b> parsel eşleşti</span>
            <button className="underline hover:text-white" data-testid="lf-clear"
                    onClick={() => { setLf({ il: "", ilce: "", mahalle: "", ada: "", parsel: "", areaMin: "", areaMax: "", ekili: "" }); setAiIds(null); }}>
              Filtreleri temizle
            </button>
          </div>
        )}
      </div>

      {/* Denetim UI düzeltmesi (2026-07-24) — AI Asistanı artık kendi ayrı
          satırında DEĞİL, Liste & Filtre / Uzaktan Algılama ile AYNI
          satırda (AiAssistantBox kapalıyken kompakt bir "btn btn-ghost"
          pill'i döndürdüğü için doğal olarak sığar, bkz. o bileşen). */}
      {/* 2026-08-19 — TEK "Araçlar" menüsü. Önceden bu alanda İKİ ayrı satır
          ve 12'ye yakın eşit ağırlıkta buton yan yana duruyordu; hangisinin
          panel açtığı, hangisinin harita aracı olduğu ayırt edilemiyordu ve
          ekranın üst yarısını yiyordu. Artık: panel/araç ayrımı menü içinde
          başlıklandırılmış, harita altlık + katman seçimi ise haritanın
          ÜZERİNE (kalıcı MapControls) taşındı. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <button onClick={() => setToolsOpen((s) => !s)}
                  className={`btn ${toolsOpen || tool || showList || showBulkRS ? "btn-primary" : "btn-ghost"} text-xs`}
                  data-testid="tools-menu-button">
            <Wrench size={14} /> Araçlar
            {activeToolCount > 0 && (
              <span className="ml-1 px-1.5 rounded-full bg-black/25 text-[10px]">{activeToolCount}</span>
            )}
            <ChevronDown size={12} className={toolsOpen ? "rotate-180 transition-transform" : "transition-transform"} />
          </button>
          {toolsOpen && (
            <>
              <div className="fixed inset-0 z-[45]" onClick={() => setToolsOpen(false)} />
              <div className="absolute left-0 mt-1 z-[46] card p-2 shadow-xl"
                   style={{ minWidth: 280 }} data-testid="tools-menu">
                <div className="text-[10px] uppercase tracking-wider text-[var(--text-dim)] px-2 py-1">
                  Paneller
                </div>
                <MenuItem icon={List} label="Liste & Filtre (Toplu Seç/Sil)" active={showList}
                          testId="toggle-list-panel"
                          onClick={() => { setShowList((s) => !s); setToolsOpen(false); }} />
                <MenuItem icon={Satellite} label="Uzaktan Algılama (Toplu Sorgu)" active={showBulkRS}
                          testId="toggle-bulk-rs"
                          onClick={() => { setShowBulkRS((s) => !s); setToolsOpen(false); }} />

                <div className="text-[10px] uppercase tracking-wider text-[var(--text-dim)] px-2 py-1 mt-2 border-t border-[var(--border)] pt-2">
                  Harita Araçları
                </div>
                {TOOLS.map((t) => (
                  <MenuItem key={t.key} icon={t.icon} label={t.label} active={tool === t.key}
                            testId={`tool-${t.key}`}
                            onClick={() => { tool === t.key ? resetTool() : activateTool(t.key); setToolsOpen(false); }} />
                ))}
                {tool && (
                  <button onClick={() => { resetTool(); setToolsOpen(false); }}
                          className="w-full text-left px-2 py-1.5 rounded text-xs text-red-400 hover:bg-[var(--surface-2)] flex items-center gap-2 mt-1">
                    <X size={14} /> Aracı Kapat
                  </button>
                )}
              </div>
            </>
          )}
        </div>

        <AiAssistantBox module="parcels"
                        onResults={(items) => setAiIds(new Set(items.map((p) => p.id)))}
                        placeholder='Örn: "Çumra&apos;daki en riskli 20 parseli göster"'
                        testId="parcels-ai" />

        {/* Aktif araç, menü kapalıyken de görünür kalmalı — kullanıcı hangi
            modda olduğunu menüyü açmadan bilmeli. */}
        {tool && (
          <span className="badge badge-b flex items-center gap-1" data-testid="active-tool-badge">
            {TOOLS.find((t) => t.key === tool)?.label}
            <button onClick={resetTool} className="hover:text-red-400"><X size={11} /></button>
          </span>
        )}
      </div>
      {showList && (
        <div className="card p-5 mb-3">
          <ParcelsListPanel />
        </div>
      )}
      {showBulkRS && (
        <div className="card p-5 mb-3">
          <BulkRemoteSensing />
        </div>
      )}
      {toolMsg && (
        <div className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mb-3">
          {toolMsg}
        </div>
      )}

      {/* SON HAL — PARSEL SATIRLARI ÜSTTE (liste↔harita çift yönlü seçim):
          satıra tıkla → haritada vurgula + uç; haritada tıkla → satır işaretlenir. */}
      <div className="card overflow-hidden mb-4" data-testid="parcel-rows">
        <div className="max-h-[300px] overflow-y-auto scrollbar">
          <table className="w-full text-sm">
            <thead className="bg-[var(--surface-2)] sticky top-0 z-10">
              <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider">
                <th className="p-3">Kod</th><th className="p-3">Ad</th><th className="p-3">İl/İlçe</th>
                <th className="p-3">Mahalle/Köy</th><th className="p-3">Ada/Parsel</th>
                <th className="p-3">Yüzölçümü</th><th className="p-3">Ekili</th><th className="p-3">Risk</th>
              </tr>
            </thead>
            <tbody>
              {visibleParcels.slice(0, 300).map((p) => (
                <tr key={p.id}
                    onClick={() => setSelected(selected?.id === p.id ? null : p)}
                    className={`border-b border-[var(--border)] cursor-pointer transition-colors ${
                      selected?.id === p.id ? "bg-[var(--primary)]/10" : "hover:bg-[var(--surface-2)]"
                    }`}
                    data-testid={`parcel-row-${p.parcel_code}`}>
                  <td className="p-3 font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</td>
                  <td className="p-3">{p.name}</td>
                  <td className="p-3 text-[var(--text-dim)]">{[p.il, p.ilce].filter(Boolean).join("/") || "—"}</td>
                  <td className="p-3 text-[var(--text-dim)]">{p.mahalle || p.village || "—"}</td>
                  <td className="p-3 text-[var(--text-dim)]">
                    {p.ada_no || p.parsel_no_tapu ? `${p.ada_no || "?"}/${p.parsel_no_tapu || "?"}` : "—"}
                  </td>
                  <td className="p-3">{p.area_dekar?.toFixed(1)} da</td>
                  <td className="p-3">{p.ekim_durumu === "ekili"
                    ? <span className="badge badge-a">Evet</span>
                    : <span className="badge badge-neutral">Hayır</span>}</td>
                  <td className="p-3">{p.risk_level && <RiskBadge level={p.risk_level} label={p.risk_label} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {visibleParcels.length === 0 && (
            <p className="p-5 text-sm text-[var(--text-dim)]">Filtreye uyan parsel yok.</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="lg:col-span-3 card overflow-hidden relative" style={{ height: 640 }}>
          <MapContainer center={[39.0, 33.5]} zoom={7} style={{ height: "100%", width: "100%" }}>
            <TileLayer
              key={basemapKey}
              attribution={(BASEMAPS[basemapKey] || BASEMAPS.hibrit).attribution}
              url={(BASEMAPS[basemapKey] || BASEMAPS.hibrit).url}
            />
            {/* Hibrit altlıkta yer adı/sınır etiketleri ikinci bir katman. */}
            {(BASEMAPS[basemapKey] || {}).overlay && (
              <TileLayer key={`${basemapKey}-ov`} url={BASEMAPS[basemapKey].overlay} />
            )}

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
                    <div style={{ minWidth: 200 }}>
                      <div style={{ fontWeight: 600 }}>{a.display_name || a.name}</div>
                      <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 4 }}>
                        {{ il: "İl", ilce: "İlçe", mahalle: "Mahalle/Köy" }[a.area_type] || a.area_type}
                      </div>
                      {[["nufus_toplam", "Nüfus"], ["kayitli_cks_ciftci_sayisi", "ÇKS Çiftçi"],
                        ["islenen_tarim_arazisi_dekar", "İşlenen Arazi"], ["baskin_urun_grubu", "Baskın Ürün"]]
                        .filter(([k]) => a[k] != null && a[k] !== "")
                        .map(([k, label]) => (
                          <div key={k} style={{ fontSize: 12, display: "flex", justifyContent: "space-between", gap: 8 }}>
                            <span style={{ opacity: 0.7 }}>{label}</span>
                            <b>{typeof a[k] === "number" ? a[k].toLocaleString("tr-TR") : a[k]}</b>
                          </div>
                        ))}
                      <button type="button" className="btn btn-ghost" style={{ fontSize: 11, marginTop: 6 }}
                              onClick={() => nav(`/idari-alanlar/${a.id}`)}>
                        Demografik detay →
                      </button>
                    </div>
                  </Popup>
                </Polygon>
              ));
            })}

            {/* Boş alana tıklama → il/ilçe/mahalle popup'ı (2026-08-19) */}
            <MapClickAdminPopup />

            {/* Listeden seçilince haritayı seçili parsele uçur (SON HAL senkron) */}
            <MapFlyTo target={selected} />

            {/* Mevcut parseller — Katmanlar panelinden kapatılabilir
                (idari sınırları tek başına incelemek için). */}
            {showParcels && visibleParcels.map((p) => {
              if (!p.geometry) return null;
              const isMergeSelected = mergeIds.includes(p.id);
              const isEditOrSplitTarget = editTarget?.id === p.id || splitTarget?.id === p.id;
              const isSelected = selected?.id === p.id;
              const color = isMergeSelected ? "#a78bfa" : (RISK_COLORS[p.risk_level] || "#4ade80");
              const latestContract = contractByParcel.get(p.id);
              return (
                <Polygon
                  key={p.id}
                  positions={p.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])}
                  pathOptions={{
                    // Seçim vurgusu: koyu haritada beyaz, açık haritada koyu çizgi
                    color: isSelected ? (getTheme() === "dark" ? "#ffffff" : "#1e1d1a") : color,
                    fillColor: color,
                    fillOpacity: isEditOrSplitTarget ? 0.1 : (isMergeSelected || isSelected ? 0.55 : 0.4),
                    weight: isSelected ? 4 : (isMergeSelected || isEditOrSplitTarget ? 3 : 1.5),
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
                    /* SON HAL — zengin popup: kimlik bilgileri + 4 hızlı işlem */
                    <Popup maxWidth={300}>
                      <div style={{ minWidth: 220 }}>
                        <div style={{ fontWeight: 600, marginBottom: 2 }}>{p.name}</div>
                        <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 6 }}>{p.parcel_code}</div>
                        <table style={{ fontSize: 12, width: "100%", lineHeight: 1.7 }}>
                          <tbody>
                            <tr><td style={{ opacity: 0.7 }}>İl / İlçe</td>
                                <td>{[p.il, p.ilce].filter(Boolean).join(" / ") || "—"}</td></tr>
                            <tr><td style={{ opacity: 0.7 }}>Mahalle</td>
                                <td>{p.mahalle || p.village || "—"}</td></tr>
                            <tr><td style={{ opacity: 0.7 }}>Ada / Parsel</td>
                                <td>{p.ada_no || "—"} / {p.parsel_no_tapu || "—"}</td></tr>
                            <tr><td style={{ opacity: 0.7 }}>Yüzölçümü</td>
                                <td><strong>{p.area_dekar?.toFixed(1)}</strong> dekar</td></tr>
                            <tr><td style={{ opacity: 0.7 }}>Ekili mi</td>
                                <td>{p.ekim_durumu === "ekili" ? "Evet" : "Hayır"}</td></tr>
                            {p.ndvi_latest && (
                              <tr><td style={{ opacity: 0.7 }}>NDVI</td>
                                  <td>{p.ndvi_latest} · {RISK_LABELS[p.risk_level] || ""}</td></tr>
                            )}
                          </tbody>
                        </table>
                        {/* 2026-08-19 — İl / İlçe / Mahalle / Parsel bağlantıları.
                            Konum bazlı sorgulanır ($geoIntersects), parseldeki
                            metin alanlarına güvenilmez.
                            "Parsel" seçilene kadar aşağıdaki işlem menüsü
                            KAPALI durur (kullanıcı isteği): önce hangi seviyeyle
                            ilgilendiğini seçer, sonra o seviyenin işlemleri açılır. */}
                        <div style={{ marginTop: 8, paddingTop: 6, borderTop: "1px solid rgba(125,125,125,.25)" }}>
                          <AdminAreaPopupLinks
                            lon={p.geometry.coordinates[0][0][0]}
                            lat={p.geometry.coordinates[0][0][1]}
                            parcel={p}
                            compact
                            onParcelClick={() => setPopupParcelOpen(
                              popupParcelOpen === p.id ? null : p.id)}
                          />
                        </div>
                        <div style={{ gap: 4, marginTop: 8,
                                      display: popupParcelOpen === p.id ? "grid" : "none" }}>
                          <button className="btn btn-primary text-xs" style={{ width: "100%" }}
                                  onClick={() => nav(`/parseller/${p.id}`)} data-testid="popup-parcel-detail">
                            Parsel detayına git
                          </button>
                          <button className="btn btn-ghost text-xs" style={{ width: "100%" }}
                                  disabled={!latestContract}
                                  title={latestContract ? `${latestContract.contract_no}` : "Bu parselin sözleşmesi yok"}
                                  onClick={() => latestContract && nav(`/sozlesmeler/${latestContract.id}`)}
                                  data-testid="popup-contract-detail">
                            Sözleşme detayına git{latestContract ? "" : " (yok)"}
                          </button>
                          <button className="btn btn-ghost text-xs" style={{ width: "100%" }}
                                  onClick={() => nav(`/ekim?parcel=${p.id}`)} data-testid="popup-planting-detail">
                            Ekim detayına git
                          </button>
                          {taskForm?.parcelId !== p.id ? (
                            <button className="btn btn-ghost text-xs" style={{ width: "100%" }}
                                    onClick={() => setTaskForm({ parcelId: p.id, task_type: "toprak işleme", date: "", msg: "" })}
                                    data-testid="popup-assign-task">
                              <ClipboardPlus size={12} /> Görev ata
                            </button>
                          ) : (
                            <div style={{ display: "grid", gap: 4, padding: 6, borderRadius: 6,
                                          background: "rgba(125,125,125,.08)" }}>
                              <select className="input text-xs" value={taskForm.task_type}
                                      onChange={(e) => setTaskForm({ ...taskForm, task_type: e.target.value })}>
                                {["toprak işleme", "ekim", "gübreleme", "ilaçlama", "sulama", "hasat", "nakliye"]
                                  .map((t) => <option key={t} value={t}>{t}</option>)}
                              </select>
                              <input className="input text-xs" type="date" value={taskForm.date}
                                     onChange={(e) => setTaskForm({ ...taskForm, date: e.target.value })} />
                              <button className="btn btn-primary text-xs" data-testid="popup-task-submit"
                                      onClick={async () => {
                                        if (!taskForm.date) { setTaskForm({ ...taskForm, msg: "Tarih seçin." }); return; }
                                        try {
                                          await api.post("/operations/tasks", {
                                            task_type: taskForm.task_type, parcel_id: p.id,
                                            scheduled_date: new Date(taskForm.date).toISOString(),
                                            machine_id: null, worker_id: null, notes: null,
                                          });
                                          setTaskForm({ ...taskForm, msg: "Görev oluşturuldu ✓" });
                                        } catch (err) {
                                          setTaskForm({ ...taskForm, msg: err.response?.data?.detail || "Görev oluşturulamadı" });
                                        }
                                      }}>
                                Görevi Oluştur
                              </button>
                              {taskForm.msg && <div style={{ fontSize: 11 }}>{taskForm.msg}</div>}
                            </div>
                          )}
                        </div>
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
          <MapControls
            basemapKey={basemapKey} setBasemapKey={setBasemapKey}
            showParcels={showParcels} setShowParcels={setShowParcels}
            showAdminAreas={showAdminAreas} setShowAdminAreas={setShowAdminAreas}
            adminLevels={adminLevels} setAdminLevels={setAdminLevels}
            adminCounts={adminCounts} adminLoading={adminLoading}
            adminCount={adminAreas.length}
          />
          <MapLegend showAdminAreas={showAdminAreas} mergeActive={tool === "merge"} />
        </div>

        {/* SAĞ PANEL — aktif araca göre değişir */}
        <div className="card p-4 overflow-y-auto scrollbar" style={{ maxHeight: 640 }}>
          {/* SON HAL — parsel satırları artık ÜSTTE; bu panel araç yokken
              seçili parselin özetini gösterir (liste↔harita senkron göstergesi) */}
          {!tool && (
            <div data-testid="selected-parcel-panel">
              <h3 className="font-display text-lg mb-3">Seçili Parsel</h3>
              {!selected ? (
                <p className="text-xs text-[var(--text-dim)]">
                  Üstteki listeden bir satıra veya haritada bir parsele tıklayın —
                  seçim iki tarafta da vurgulanır.
                </p>
              ) : (
                <div className="space-y-3">
                  <div className="p-3 rounded-lg border border-[var(--primary)] bg-[var(--primary)]/5">
                    <div className="font-mono text-xs text-[var(--text-dim)]">{selected.parcel_code}</div>
                    <div className="text-sm mt-1 font-medium">{selected.name}</div>
                    <div className="text-xs text-[var(--text-dim)] mt-1">
                      {[selected.il, selected.ilce, selected.mahalle || selected.village].filter(Boolean).join(" / ") || "—"}
                    </div>
                    <div className="text-xs text-[var(--text-dim)] mt-1">
                      Ada {selected.ada_no || "—"} / Parsel {selected.parsel_no_tapu || "—"} ·{" "}
                      {selected.area_dekar?.toFixed(1)} dekar
                    </div>
                    <div className="text-xs text-[var(--text-dim)] mt-1">
                      {selected.soil_type} · {selected.irrigation} · Ekili: {selected.ekim_durumu === "ekili" ? "Evet" : "Hayır"}
                    </div>
                    {selected.risk_level && <div className="mt-1.5"><RiskBadge level={selected.risk_level} label={selected.risk_label} /></div>}
                  </div>
                  <button className="btn btn-primary w-full justify-center text-xs"
                          onClick={() => nav(`/parseller/${selected.id}`)} data-testid="selected-goto-detail">
                    Parsel detayına git
                  </button>
                  <button className="btn btn-ghost w-full justify-center text-xs"
                          onClick={() => setSelected(null)}>
                    Seçimi temizle
                  </button>
                </div>
              )}
            </div>
          )}

          {tool === "manual" && (
            <div>
              <h3 className="font-display text-lg mb-3">Yeni Parsel (Manuel)</h3>
              <TakbisQuickBox form={takbisQuick} setForm={setTakbisQuick} busy={takbisQuickBusy}
                              result={takbisQuickResult} msg={takbisQuickMsg} onQuery={queryTakbisQuick} />
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
                <>
                <TakbisQuickBox form={takbisQuick} setForm={setTakbisQuick} busy={takbisQuickBusy}
                                result={takbisQuickResult} msg={takbisQuickMsg} onQuery={queryTakbisQuick} />
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
                </>
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
              <h3 className="font-display text-lg mb-3">Toplu Parsel İçe Aktar</h3>
              <p className="text-[11px] text-[var(--text-dim)] mb-2">
                GeoJSON (.geojson/.json), KML (.kml) veya KMZ (.kmz) — birden fazla parsel tek seferde eklenir.
                Dosya içindeki il/ilçe/mahalle/ada/parsel bilgileri otomatik olarak parsel alanlarına yazılır.
              </p>
              <input type="file" accept=".geojson,.json,.kml,.kmz" onChange={onImportFile} className="input mb-3 text-xs" />
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
                      Varsayılan Çiftçi <span className="text-[var(--text-dim)]">(opsiyonel)</span>
                    </label>
                    <FarmerSelect
                      farmers={farmers}
                      value={importFarmerId || null}
                      onChange={(fid) => setImportFarmerId(fid || "")}
                      placeholder="Çiftçi ara… (boş bırakabilirsiniz)"
                    />
                    <p className="text-[10px] text-[var(--text-dim)] mt-1">
                      Boş bırakırsanız parseller "atanmamış" olarak eklenir — sonra parsele tıklayıp çiftçi atayabilirsiniz.
                    </p>
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
                      {importResult.errors?.length > 0 && (() => {
                        // Atlama nedenlerini grupla (ör. "1275 × Parsel değil (Point)…")
                        const groups = {};
                        importResult.errors.forEach((e) => {
                          const key = (e.error || "Bilinmeyen").replace(/:.*$/, "").trim();
                          groups[key] = (groups[key] || 0) + 1;
                        });
                        return (
                          <div className="text-amber-400 mt-1">
                            <div>{importResult.errors.length} kayıt atlandı:</div>
                            <ul className="list-disc list-inside mt-0.5">
                              {Object.entries(groups).map(([msg, n]) => (
                                <li key={msg}>{n} × {msg}</li>
                              ))}
                            </ul>
                            <div className="text-[10px] text-[var(--text-dim)] mt-1">
                              Not: Nokta/çizgi geometrileri parsel olamaz (alanı yok); yalnızca Polygon'lar parsele dönüşür.
                            </div>
                          </div>
                        );
                      })()}
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

// Denetim eklentisi (2026-07-25) — TAKBİS ön-sorgu kutusu (parsel EKLEME
// akışında, "manuel" ve "çiz" formlarının üstünde). Backend /gov/takbis/
// query hiçbir şey YAZMAZ (bkz. gov_integration_routes.py) — sadece
// referans bilgi döner, kullanıcı sonucu görüp form alanlarına elle taşır.
function TakbisQuickBox({ form, setForm, busy, result, msg, onQuery }) {
  return (
    <div className="border border-[var(--border)] rounded-lg p-3 mb-3" data-testid="parcel-add-takbis-box">
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
        <button className="btn btn-ghost text-xs py-1.5" onClick={onQuery} disabled={busy} data-testid="parcel-add-takbis-submit">
          {busy ? "Sorgulanıyor…" : "Sorgula"}
        </button>
      </div>
      {msg && <div className="text-[11px] text-[var(--text-dim)] mt-2">{msg}</div>}
      {result?.found && (
        <div className="text-[11px] mt-2 grid grid-cols-2 md:grid-cols-4 gap-2" data-testid="parcel-add-takbis-result">
          <div><span className="text-[var(--text-dim)]">Malik:</span> {result.malik}</div>
          <div><span className="text-[var(--text-dim)]">Nitelik:</span> {result.nitelik}</div>
          <div><span className="text-[var(--text-dim)]">Alan:</span> {result.alan_m2} m²</div>
          <div><span className="text-[var(--text-dim)]">Tapu Tarihi:</span> {result.tapu_tarihi}</div>
        </div>
      )}
    </div>
  );
}
