import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { MapContainer, TileLayer, Polygon, Popup, CircleMarker, useMapEvents } from "react-leaflet";
import * as turf from "@turf/turf";
import FilterPanel from "@/components/FilterPanel";
import WidgetCard from "@/components/WidgetCard";
import { MapDrawTools } from "@/components/MapDrawTools";
import { MAP_WIDGET_REGISTRY, DEFAULT_WIDGET_KEYS } from "@/lib/mapWidgets";
import { moduleDetailPath } from "@/lib/moduleRoutes";
import { directionsUrl } from "@/lib/directions";
import {
  SlidersHorizontal, Save, RotateCcw, X, Check, Layers, Globe, PenTool, Wrench, ListChecks,
  Camera, Link2, Navigation, Trash2, Plus, History, Play, Pause, Sparkles,
} from "lucide-react";

const RISK_COLORS = { yesil: "#4ade80", sari: "#fbbf24", turuncu: "#fb923c", kirmizi: "#ef4444" };
const RISK_LABELS = { yesil: "Düşük Risk", sari: "İzlemeye Değer", turuncu: "Riskli", kirmizi: "Acil Müdahale" };
const SELECT_COLOR = "#a78bfa";
const DEFAULT_CENTER = [39.0, 33.5];
const DEFAULT_ZOOM = 7;

// IT-15 — Basemap değiştirici: hepsi anahtarsız/ücretsiz genel XYZ servisleri
// (uydu görüntüsü burada gerçek NDVI/Sentinel değil, sadece Esri'nin genel
// ortofoto basemap'i — extras.py'deki simüle NDVI ile KARIŞTIRILMAMALI).
const BASEMAPS = {
  dark: { label: "Koyu", url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", attribution: "&copy; OpenStreetMap &copy; CARTO" },
  light: { label: "Açık", url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", attribution: "&copy; OpenStreetMap &copy; CARTO" },
  streets: { label: "Sokak", url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", attribution: "&copy; OpenStreetMap katkıcıları" },
  satellite: { label: "Uydu", url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attribution: "Tiles &copy; Esri" },
};
const DEFAULT_BASEMAP = "dark";

// IT-15 — Katman kataloğu: sadece 2 katman olduğu için widget'lardaki gibi
// ayrı bir dosya-başına-katman registry'si KURULMADI (bilinçli, o kalıp
// 8 widget'ı gerekçelendirmişti — burada aşırı mühendislik olurdu).
const LAYER_CATALOG = [
  { key: "parcels", label: "Parseller" },
  { key: "admin_areas", label: "İdari Sınırlar" },
  { key: "field_tasks", label: "Saha Görevleri" },
];
const DEFAULT_LAYERS = ["parcels"];

// IT-23 — field_tasks katmanı: 11 backend durumu basit bir renk gruplamasına indirger
// (Kanban'ın 8+1 sütununa AYNI kabaca eşleşir, harita için sadeleştirilmiş).
const FIELD_TASK_STATUS_COLOR = {
  planlandi: "#94a3b8", atandi: "#60a5fa", kabul_edildi: "#60a5fa",
  yola_cikildi: "#fbbf24", yerine_ulasildi: "#fbbf24", calisiliyor: "#fbbf24",
  tamamlandi: "#4ade80", onay_bekliyor: "#4ade80",
  kapandi: "#22c55e", reddedildi: "#ef4444", iptal_edildi: "#ef4444",
};
const TASK_STATUS_LABEL_MAP = {
  planlandi: "Planlandı", atandi: "Atandı", kabul_edildi: "Kabul Edildi",
  reddedildi: "Reddedildi", yola_cikildi: "Yola Çıkıldı", yerine_ulasildi: "Görev Yerine Ulaşıldı",
  calisiliyor: "Çalışılıyor", tamamlandi: "Tamamlandı", onay_bekliyor: "Yönetici Onayı Bekliyor",
  kapandi: "Kapandı", iptal_edildi: "İptal Edildi",
};

// IT-16 — zenginleştirilmiş popup'ta üretim sezonu durumu (ParcelDetail.jsx'teki AYNI etiketler)
const CYCLE_STATUS_LABELS = { planning: "Planlama", active: "Aktif", harvesting: "Hasat", completed: "Tamamlandı", cancelled: "İptal" };

// IT-17 — Mekânsal Zaman Makinesi: backend'in (satellite_provider.py)
// ürettiği 10 SABİT örnek tarih (Mayıs-Eylül 2025, ayda 1 ve 15'i) —
// demo/simüle veri bu tarihlerin DIŞINDA hiçbir gün için üretilmez, bu
// yüzden slider sürekli değil bu 10 noktayı gezen bir index kullanır.
const TIME_MACHINE_DATES = [];
for (let m = 5; m <= 9; m++) {
  for (const d of [1, 15]) {
    TIME_MACHINE_DATES.push(`2025-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`);
  }
}
const TR_MONTHS = { "05": "Mayıs", "06": "Haziran", "07": "Temmuz", "08": "Ağustos", "09": "Eylül" };
function formatTimeMachineDate(dateStr) {
  const [, mm, dd] = dateStr.split("-");
  return `${Number(dd)} ${TR_MONTHS[mm]} 2025`;
}
// Demo satellite verisi hep 2025'e ait — Zaman Makinesi açıkken üretim
// sezonları da bu yıla süzülür (IT-17'nin "sezon senkron" maddesi).
const TIME_MACHINE_SEASON_YEAR = 2025;

function parcelCentroidLatLng(p) {
  if (!p.geometry) return null;
  try {
    const [lng, lat] = turf.centroid(turf.polygon(p.geometry.coordinates)).geometry.coordinates;
    return [lat, lng];
  } catch {
    return null;
  }
}

/**
 * Harita hareket ettikçe (pan/zoom) görünen sınırları + merkez/zoom'u yukarı bildirir.
 *
 * `onChange` her `HaritaPaneli` render'ında YENİ bir fonksiyon referansıdır
 * (bileşen gövdesinde tanımlı). Bunu doğrudan useMapEvents'e verirsek
 * (react-leaflet'in kendi useEffect'i `[map, handlers]`'a bağımlı olduğu
 * için, bkz. node_modules/react-leaflet/lib/hooks.js) her render'da
 * dinleyiciler off/on ile yeniden bağlanır — bu da bir "Maximum update
 * depth exceeded" sonsuz döngüsüne yol açtı (canlı tarayıcı testinde
 * yakalandı). Çözüm: `onChangeRef` ile SADECE en güncel callback'i takip
 * et, `useMapEvents`'e verilen handler nesnesini `useRef` ile TEK SEFER
 * (bileşenin ömrü boyunca sabit referans) oluştur.
 */
function MapSync({ onChange }) {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const handlersRef = useRef();
  if (!handlersRef.current) {
    handlersRef.current = {
      moveend() { onChangeRef.current(map); },
      zoomend() { onChangeRef.current(map); },
    };
  }
  const map = useMapEvents(handlersRef.current);

  useEffect(() => { onChangeRef.current(map); }, [map]);
  return null;
}

export default function HaritaPaneli() {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [parcels, setParcels] = useState([]);
  const [productionCycles, setProductionCycles] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [farmers, setFarmers] = useState([]);

  const [initialView, setInitialView] = useState({ center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM });
  const [enabledKeys, setEnabledKeys] = useState(DEFAULT_WIDGET_KEYS);
  const [hasSavedWorkspace, setHasSavedWorkspace] = useState(false);

  const [mapBounds, setMapBounds] = useState(null);
  const currentViewRef = useRef({ center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM });

  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [filterIds, setFilterIds] = useState(null); // null = Gelişmiş Filtre uygulanmamış

  const [pickerOpen, setPickerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  // IT-15 — basemap değiştirici + katman yönetimi
  const [basemapKey, setBasemapKey] = useState(DEFAULT_BASEMAP);
  const [basemapOpen, setBasemapOpen] = useState(false);
  const [visibleLayers, setVisibleLayers] = useState(DEFAULT_LAYERS);
  const [layersOpen, setLayersOpen] = useState(false);
  const [adminAreas, setAdminAreas] = useState([]);

  // IT-15 — çizim aracıyla seçim (polygon/rectangle/circle → içindeki parseller)
  const [drawSelectActive, setDrawSelectActive] = useState(false);

  // IT-15 — çoklu parsel toplu işlemleri
  const [bulkPanel, setBulkPanel] = useState(null); // null | "update" | "task"
  const [bulkForm, setBulkForm] = useState({});
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMsg, setBulkMsg] = useState("");

  // IT-16 — parsel popup'ında tekli hızlı görev oluşturma (hangi parselin
  // mini-formu açık, bkz. "hızlı işlem merkezi")
  const [quickTaskParcelId, setQuickTaskParcelId] = useState(null);
  const [quickTaskForm, setQuickTaskForm] = useState({});
  const [quickTaskBusy, setQuickTaskBusy] = useState(false);
  const [quickTaskMsg, setQuickTaskMsg] = useState("");

  // IT-16 — Harita Snapshot (kaydet/paylaş): map_workspace'ten AYRI,
  // adlandırılmış/çoklu/paylaşılabilir görünüm kayıtları
  const [snapshots, setSnapshots] = useState([]);
  const [snapshotsLoaded, setSnapshotsLoaded] = useState(false);
  const [snapshotPanelOpen, setSnapshotPanelOpen] = useState(false);
  const [snapshotName, setSnapshotName] = useState("");
  const [snapshotShared, setSnapshotShared] = useState(false);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [snapshotMsg, setSnapshotMsg] = useState("");

  // IT-17 — Mekânsal Zaman Makinesi
  const [timeMachineActive, setTimeMachineActive] = useState(false);
  const [timeMachineIdx, setTimeMachineIdx] = useState(TIME_MACHINE_DATES.length - 1);
  const [timeMachinePlaying, setTimeMachinePlaying] = useState(false);
  const [ndviSnapshot, setNdviSnapshot] = useState(() => new Map());
  const [ndviLoading, setNdviLoading] = useState(false);

  // IT-17 — AI Harita Asistanı (NL → Query Engine → harita filtre/seçim)
  const [aiPanelOpen, setAiPanelOpen] = useState(false);
  const [aiQuery, setAiQuery] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiResult, setAiResult] = useState(null); // { summary, result_count, ai_powered }

  // IT-23 — Saha Görevleri katmanı (IT-22'nin field_tasks'ı — data_entry.py'nin
  // ESKİ "tasks" state'inden BİLİNÇLİ AYRI, karıştırılmamalı).
  const [fieldTasks, setFieldTasks] = useState([]);
  const [taskTypes, setTaskTypes] = useState([]);
  const [assignableStaff, setAssignableStaff] = useState([]);
  const [quickFieldTaskParcelId, setQuickFieldTaskParcelId] = useState(null);
  const [quickFieldTaskForm, setQuickFieldTaskForm] = useState({});
  const [quickFieldTaskBusy, setQuickFieldTaskBusy] = useState(false);
  const [quickFieldTaskMsg, setQuickFieldTaskMsg] = useState("");

  useEffect(() => {
    (async () => {
      const [p, pc, t, f, ws, ft, tt, su] = await Promise.all([
        api.get("/parcels", { params: { limit: 1200 } }),
        api.get("/production-cycles"),
        api.get("/operations/tasks"),
        api.get("/farmers", { params: { limit: 500 } }),
        api.get("/map-workspaces/me"),
        api.get("/tasks").catch(() => ({ data: [] })),
        api.get("/task-types").catch(() => ({ data: [] })),
        api.get("/field-ops/assignable-users").catch(() => ({ data: [] })),
      ]);
      setParcels(p.data);
      setProductionCycles(pc.data);
      setTasks(t.data);
      setFarmers(f.data);
      setFieldTasks(ft.data);
      setTaskTypes(tt.data);
      setAssignableStaff(su.data);
      if (ws.data) {
        setHasSavedWorkspace(true);
        if (ws.data.widget_keys?.length) setEnabledKeys(ws.data.widget_keys);
        if (ws.data.map_center && ws.data.map_zoom) {
          setInitialView({ center: ws.data.map_center, zoom: ws.data.map_zoom });
          currentViewRef.current = { center: ws.data.map_center, zoom: ws.data.map_zoom };
        }
        if (ws.data.basemap_key) setBasemapKey(ws.data.basemap_key);
        if (ws.data.visible_layers?.length) setVisibleLayers(ws.data.visible_layers);
      }

      // IT-16 — ?snapshot=<id> ile açılan paylaşım linki: kişisel çalışma
      // alanının ÜZERİNE yazar (MapContainer henüz mount OLMADAN, initialView
      // burada güncellenmeli — bu yüzden setLoading(false)'DAN ÖNCE await edilir).
      const snapshotId = new URLSearchParams(window.location.search).get("snapshot");
      if (snapshotId) {
        try {
          const { data: snap } = await api.get(`/map-snapshots/${snapshotId}`);
          if (snap.widget_keys?.length) setEnabledKeys(snap.widget_keys);
          if (snap.map_center && snap.map_zoom) {
            setInitialView({ center: snap.map_center, zoom: snap.map_zoom });
            currentViewRef.current = { center: snap.map_center, zoom: snap.map_zoom };
          }
          if (snap.basemap_key) setBasemapKey(snap.basemap_key);
          if (snap.visible_layers?.length) setVisibleLayers(snap.visible_layers);
          if (snap.selected_parcel_ids?.length) setSelectedIds(new Set(snap.selected_parcel_ids));
          setSnapshotMsg(`"${snap.name}" görünümü yüklendi.`);
        } catch {
          setSnapshotMsg("Snapshot bulunamadı veya erişim izniniz yok.");
        }
        setTimeout(() => setSnapshotMsg(""), 5000);
      }

      setLoading(false);
    })();
  }, []);

  // İdari Sınırlar katmanı ilk açıldığında (Parcels.jsx'teki aynı tembel-yükleme kalıbı)
  useEffect(() => {
    if (visibleLayers.includes("admin_areas") && adminAreas.length === 0) {
      api.get("/admin-areas").then((r) => setAdminAreas(r.data));
    }
  }, [visibleLayers, adminAreas.length]);

  // IT-17 — Zaman Makinesi açıkken slider her değiştiğinde (veya ilk
  // açıldığında) o tarihteki NDVI/risk anlık görüntüsünü çeker.
  useEffect(() => {
    if (!timeMachineActive || parcels.length === 0) return;
    const date = TIME_MACHINE_DATES[timeMachineIdx];
    setNdviLoading(true);
    api.post("/satellite/ndvi-snapshot", { parcel_ids: parcels.map((p) => p.id), date })
      .then((r) => setNdviSnapshot(new Map(r.data.items.map((i) => [i.parcel_id, i]))))
      .finally(() => setNdviLoading(false));
  }, [timeMachineActive, timeMachineIdx, parcels]);

  // IT-17 — "Oynat" düğmesi: 1.5s'de bir bir sonraki örnek tarihe ilerler,
  // sona gelince başa döner (basit bir loop — durdurma/duraklatma yeterli,
  // hız kontrolü v1 kapsamı dışı).
  useEffect(() => {
    if (!timeMachinePlaying) return;
    const id = setInterval(() => {
      setTimeMachineIdx((i) => (i + 1) % TIME_MACHINE_DATES.length);
    }, 1500);
    return () => clearInterval(id);
  }, [timeMachinePlaying]);

  const parcelsWithCentroid = useMemo(
    () => parcels.map((p) => ({ ...p, __centroid: parcelCentroidLatLng(p) })),
    [parcels]
  );

  // IT-23 — Saha Görevleri katmanı: her field_task'ın parselinin centroid'inde
  // küçük bir daire marker'ı (durum rengiyle, bkz. FIELD_TASK_STATUS_COLOR).
  const parcelCentroidById = useMemo(
    () => new Map(parcelsWithCentroid.map((p) => [p.id, p.__centroid])),
    [parcelsWithCentroid]
  );
  const fieldTasksWithCentroid = useMemo(
    () => fieldTasks
      .map((t) => ({ ...t, __centroid: t.parcel_id ? parcelCentroidById.get(t.parcel_id) : null }))
      .filter((t) => t.__centroid),
    [fieldTasks, parcelCentroidById]
  );
  const taskTypesById = useMemo(() => new Map(taskTypes.map((t) => [t.id, t])), [taskTypes]);

  // IT-17 — Zaman Makinesi AÇIKKEN parsellerin ndvi_latest/risk_level/
  // risk_label'ı o tarihteki anlık görüntüyle GEÇİCİ OLARAK geçersiz kılınır
  // (DB'deki gerçek değer ETKİLENMEZ — sadece bu sayfanın render/widget
  // hesaplamalarında kullanılan türetilmiş kopya). Snapshot henüz gelmediyse
  // (veya o parsel için veri yoksa) orijinal değer korunur.
  const timeAdjustedParcels = useMemo(() => {
    if (!timeMachineActive || ndviSnapshot.size === 0) return parcelsWithCentroid;
    return parcelsWithCentroid.map((p) => {
      const snap = ndviSnapshot.get(p.id);
      if (!snap) return p;
      return { ...p, ndvi_latest: snap.ndvi, risk_level: snap.risk_level, risk_label: snap.risk_label };
    });
  }, [parcelsWithCentroid, timeMachineActive, ndviSnapshot]);

  // IT-16 — zenginleştirilmiş popup için: parsel→çiftçi adı ve parsel→en
  // güncel üretim sezonu eşlemeleri (mevcut farmers/productionCycles
  // state'lerinden — yeni bir API çağrısı gerekmiyor).
  const farmersById = useMemo(() => new Map(farmers.map((f) => [f.id, f])), [farmers]);
  const latestCycleByParcel = useMemo(() => {
    const map = new Map();
    for (const c of productionCycles) {
      const prev = map.get(c.parcel_id);
      if (!prev || (c.year || 0) > (prev.year || 0)) map.set(c.parcel_id, c);
    }
    return map;
  }, [productionCycles]);

  // Görünen harita sınırları ∩ (varsa) Gelişmiş Filtre sonucu — SEÇİMDEN BAĞIMSIZ.
  // "Şekille Seç" (IT-15) bu havuzdan seçer: önceki tıklama-seçimini değil,
  // o an haritada GERÇEKTEN görünen/filtrelenmiş kümeyi baz alır (aksi halde
  // filtrelenmiş/görünmeyen bir parsel şekil içinde kalınca sessizce seçilirdi).
  const filteredParcels = useMemo(() => {
    let list = timeAdjustedParcels;
    if (mapBounds) {
      list = list.filter((p) => p.__centroid && mapBounds.contains(p.__centroid));
    }
    if (filterIds) {
      list = list.filter((p) => filterIds.has(p.id));
    }
    return list;
  }, [timeAdjustedParcels, mapBounds, filterIds]);

  // IT-14 — harita↔dashboard senkron: seçim varsa SADECE seçim geçerlidir;
  // yoksa filteredParcels (harita sınırları ∩ Gelişmiş Filtre).
  const scopedParcels = useMemo(() => {
    if (selectedIds.size > 0) {
      return timeAdjustedParcels.filter((p) => selectedIds.has(p.id));
    }
    return filteredParcels;
  }, [timeAdjustedParcels, filteredParcels, selectedIds]);

  // IT-17 — "sezon senkron": Zaman Makinesi açıkken üretim sezonları demo
  // uydu verisinin ait olduğu yıla (2025) süzülür — widget'lar (Aktif
  // Üretim Sezonları, Hasat Bekleyen Alanlar vb.) o an "o yılda" görürmüş
  // gibi hesaplanır.
  const ctxProductionCycles = useMemo(() => {
    if (!timeMachineActive) return productionCycles;
    return productionCycles.filter((c) => c.year === TIME_MACHINE_SEASON_YEAR);
  }, [productionCycles, timeMachineActive]);

  const ctx = useMemo(
    () => ({
      parcels: scopedParcels,
      parcelIds: new Set(scopedParcels.map((p) => p.id)),
      productionCycles: ctxProductionCycles,
      tasks,
      farmers,
    }),
    [scopedParcels, ctxProductionCycles, tasks, farmers]
  );

  function onMapChange(map) {
    setMapBounds(map.getBounds());
    const c = map.getCenter();
    currentViewRef.current = { center: [c.lat, c.lng], zoom: map.getZoom() };
  }

  function toggleSelect(id) {
    setSelectedIds((ids) => {
      const next = new Set(ids);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleWidget(key) {
    setEnabledKeys((keys) => (keys.includes(key) ? keys.filter((k) => k !== key) : [...keys, key]));
  }

  function toggleLayer(key) {
    setVisibleLayers((keys) => (keys.includes(key) ? keys.filter((k) => k !== key) : [...keys, key]));
  }

  // IT-15 — poligon/dikdörtgen/daire çizilince: merkezinin/köşelerinin içindeki
  // parselleri (centroid bazlı, harita↔dashboard senkronun geri kalanıyla TUTARLI
  // — bkz. IT-14 mapBounds.contains) otomatik seçer. Daire için leaflet'in
  // toGeoJSON()'ı bir Point döner (properties.radius'la), turf ile kesişim
  // kurabilmek için gerçek çemberi layer.getLatLng()/getRadius()'tan inşa ederiz.
  function onDrawSelection(layer, geojson, shapeType) {
    try {
      const poly = shapeType === "circle"
        ? turf.circle(
            [layer.getLatLng().lng, layer.getLatLng().lat],
            layer.getRadius() / 1000,
            { steps: 64, units: "kilometers" }
          )
        : turf.polygon(geojson.geometry.coordinates);
      const insideIds = filteredParcels
        .filter((p) => p.__centroid && turf.booleanPointInPolygon(turf.point([p.__centroid[1], p.__centroid[0]]), poly))
        .map((p) => p.id);
      setSelectedIds(new Set(insideIds));
    } finally {
      setDrawSelectActive(false);
    }
  }

  async function saveWorkspace() {
    setSaving(true);
    setSaveMsg("");
    try {
      await api.put("/map-workspaces/me", {
        widget_keys: enabledKeys,
        map_center: currentViewRef.current.center,
        map_zoom: currentViewRef.current.zoom,
        basemap_key: basemapKey,
        visible_layers: visibleLayers,
      });
      setHasSavedWorkspace(true);
      setSaveMsg("Çalışma alanı kaydedildi.");
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(""), 3000);
    }
  }

  async function resetWorkspace() {
    await api.delete("/map-workspaces/me");
    setHasSavedWorkspace(false);
    setEnabledKeys(DEFAULT_WIDGET_KEYS);
    setBasemapKey(DEFAULT_BASEMAP);
    setVisibleLayers(DEFAULT_LAYERS);
    setSaveMsg("Varsayılanlara sıfırlandı.");
    setTimeout(() => setSaveMsg(""), 3000);
  }

  // IT-15 — çoklu parsel toplu alan güncelleme (soil_type/irrigation/risk_level)
  async function submitBulkUpdate() {
    const updates = {};
    if (bulkForm.irrigation) updates.irrigation = bulkForm.irrigation;
    if (bulkForm.soil_type) updates.soil_type = bulkForm.soil_type;
    if (bulkForm.risk_level) updates.risk_level = bulkForm.risk_level;
    if (Object.keys(updates).length === 0) {
      setBulkMsg("En az bir alan seçin.");
      return;
    }
    setBulkBusy(true);
    try {
      const { data } = await api.put("/parcels/bulk-update", { parcel_ids: [...selectedIds], updates });
      setBulkMsg(`${data.updated_count} parsel güncellendi.`);
      setBulkForm({});
      setBulkPanel(null);
      const fresh = await api.get("/parcels", { params: { limit: 1200 } });
      setParcels(fresh.data);
    } catch (err) {
      setBulkMsg(err.response?.data?.detail || "Güncelleme başarısız.");
    } finally {
      setBulkBusy(false);
      setTimeout(() => setBulkMsg(""), 4000);
    }
  }

  // IT-15 — çoklu parsel toplu görev oluşturma (mevcut tekli POST /operations/tasks'ı
  // seçili her parsel için tekrarlar — yeni bir bulk endpoint YOK, bilinçli: görevin
  // farmer_id/region_id'si zaten backend'de parselden türetiliyor, N ayrı istek burada
  // beklenen seçim boyutları için (haritadan çizilen bir alan) makul bir maliyet).
  async function submitBulkTask() {
    if (!bulkForm.task_type || !bulkForm.scheduled_date) return;
    setBulkBusy(true);
    try {
      const ids = [...selectedIds];
      await Promise.all(ids.map((id) => api.post("/operations/tasks", {
        task_type: bulkForm.task_type,
        parcel_id: id,
        scheduled_date: new Date(bulkForm.scheduled_date).toISOString(),
        notes: bulkForm.notes || "",
      })));
      setBulkMsg(`${ids.length} parsele görev oluşturuldu.`);
      setBulkForm({});
      setBulkPanel(null);
    } catch (err) {
      setBulkMsg(err.response?.data?.detail || "Görev oluşturma başarısız.");
    } finally {
      setBulkBusy(false);
      setTimeout(() => setBulkMsg(""), 4000);
    }
  }

  // IT-16 — popup'taki "+ Görev" mini formu: TEK parsele hızlı görev (bulk
  // panelin tekli karşılığı, aynı POST /operations/tasks'ı kullanır).
  async function submitQuickTask(parcelId) {
    if (!quickTaskForm.task_type || !quickTaskForm.scheduled_date) return;
    setQuickTaskBusy(true);
    setQuickTaskMsg("");
    try {
      await api.post("/operations/tasks", {
        task_type: quickTaskForm.task_type,
        parcel_id: parcelId,
        scheduled_date: new Date(quickTaskForm.scheduled_date).toISOString(),
        notes: "",
      });
      setQuickTaskParcelId(null);
      setQuickTaskForm({});
    } catch (err) {
      setQuickTaskMsg(err.response?.data?.detail || "Görev oluşturulamadı.");
    } finally {
      setQuickTaskBusy(false);
    }
  }

  // IT-23 — popup'taki "+ Saha Görevi": IT-22'nin field_tasks modeline (POST
  // /tasks) yeni bir görev açar — yukarıdaki "+ Görev" (ESKİ operations/tasks)
  // ile KARIŞTIRILMAMALI, bilinçli olarak ayrı bir buton/form.
  async function submitQuickFieldTask(parcelId) {
    if (!quickFieldTaskForm.task_type_id || !quickFieldTaskForm.assigned_to || !quickFieldTaskForm.planned_date) return;
    setQuickFieldTaskBusy(true);
    setQuickFieldTaskMsg("");
    try {
      const parcel = parcels.find((p) => p.id === parcelId);
      await api.post("/tasks", {
        task_type_id: quickFieldTaskForm.task_type_id,
        assigned_to: quickFieldTaskForm.assigned_to,
        parcel_id: parcelId,
        farmer_id: parcel?.farmer_id || null,
        planned_date: quickFieldTaskForm.planned_date,
      });
      const { data } = await api.get("/tasks");
      setFieldTasks(data);
      setQuickFieldTaskParcelId(null);
      setQuickFieldTaskForm({});
    } catch (err) {
      setQuickFieldTaskMsg(err.response?.data?.detail || "Görev oluşturulamadı.");
    } finally {
      setQuickFieldTaskBusy(false);
    }
  }

  // IT-16 — Harita Snapshot: mevcut görünümü adlandırılmış/paylaşılabilir kayıt olarak saklar.
  async function loadSnapshots() {
    const { data } = await api.get("/map-snapshots");
    setSnapshots(data);
    setSnapshotsLoaded(true);
  }

  async function saveSnapshot() {
    if (!snapshotName.trim()) {
      setSnapshotMsg("Bir isim girin.");
      return;
    }
    setSavingSnapshot(true);
    setSnapshotMsg("");
    try {
      await api.post("/map-snapshots", {
        name: snapshotName.trim(),
        map_center: currentViewRef.current.center,
        map_zoom: currentViewRef.current.zoom,
        widget_keys: enabledKeys,
        basemap_key: basemapKey,
        visible_layers: visibleLayers,
        selected_parcel_ids: [...selectedIds],
        is_shared: snapshotShared,
      });
      setSnapshotName("");
      setSnapshotShared(false);
      setSnapshotMsg("Snapshot kaydedildi.");
      await loadSnapshots();
    } catch (err) {
      setSnapshotMsg(err.response?.data?.detail || "Kaydedilemedi.");
    } finally {
      setSavingSnapshot(false);
      setTimeout(() => setSnapshotMsg(""), 4000);
    }
  }

  // NOT: initialView SADECE ilk mount'ta okunur (react-leaflet gotcha, bkz.
  // MapSync yorumu) — mevcut React state'ini değiştirmek MEVCUT haritayı
  // otomatik kaydırmaz. "Aç" bu yüzden sayfayı ?snapshot=<id> ile YENİDEN
  // yükler; yukarıdaki ilk yükleme effect'i bu parametreyi görüp initialView'i
  // mount ÖNCESİ doğru kurar — tek tutarlı yol (aynı URL "Kopyala"da da paylaşılır).
  function openSnapshot(snap) {
    const url = new URL(window.location.href);
    url.searchParams.set("snapshot", snap.id);
    window.location.href = url.toString();
  }

  function copySnapshotLink(id) {
    const url = new URL(window.location.href);
    url.searchParams.set("snapshot", id);
    navigator.clipboard?.writeText(url.toString());
    setSnapshotMsg("Bağlantı kopyalandı.");
    setTimeout(() => setSnapshotMsg(""), 3000);
  }

  async function deleteSnapshot(id) {
    try {
      await api.delete(`/map-snapshots/${id}`);
      await loadSnapshots();
    } catch (err) {
      setSnapshotMsg(err.response?.data?.detail || "Silinemedi.");
      setTimeout(() => setSnapshotMsg(""), 4000);
    }
  }

  // IT-17 — AI Harita Asistanı: mevcut /ai/copilot'u (IT-10, NL → Query
  // Engine köprüsü) ÇAĞIRIR — yeni bir AI entegrasyonu YOK, sadece
  // sonucu (dönen parcels listesi) haritanın SEÇİM mekanizmasına bağlar
  // ("Şekille Seç"in geometrik değil doğal-dil sürümü gibi).
  async function submitAiQuery() {
    if (!aiQuery.trim()) return;
    setAiBusy(true);
    setAiResult(null);
    try {
      const { data } = await api.post("/ai/copilot", { query: aiQuery.trim() });
      setSelectedIds(new Set(data.parcels.map((p) => p.id)));
      setAiResult({ summary: data.summary, result_count: data.result_count, ai_powered: data.ai_powered });
    } catch (err) {
      setAiResult({ summary: err.response?.data?.detail || "Sorgu işlenemedi.", result_count: 0 });
    } finally {
      setAiBusy(false);
    }
  }

  if (loading) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const activeWidgets = MAP_WIDGET_REGISTRY.filter((w) => enabledKeys.includes(w.key));

  return (
    <div className="p-8 max-w-[1700px]" data-testid="harita-paneli-page">
      <header className="mb-4 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SPATIAL OPERATIONS CENTER</div>
          <h1 className="font-display text-4xl">Harita Paneli</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Widget'lar haritadaki görünüme, aktif filtreye ve seçime göre canlı güncellenir.
            {selectedIds.size > 0 && <span className="text-[var(--primary)]"> · {selectedIds.size} parsel seçili</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {saveMsg && <span className="text-xs text-[var(--primary)]">{saveMsg}</span>}
          {/* IT-16 — snapshotMsg burada gösterilir (panel KAPALIYKEN de görünsün diye,
              ör. ?snapshot=<id> linkiyle gelindiğinde panel varsayılan kapalı olur) */}
          {snapshotMsg && <span className="text-xs text-[var(--primary)]">{snapshotMsg}</span>}
          {selectedIds.size > 0 && (
            <button onClick={() => setSelectedIds(new Set())} className="btn btn-ghost text-xs">
              <X size={14} /> Seçimi Temizle
            </button>
          )}
          <div className="relative">
            <button onClick={() => setPickerOpen((o) => !o)} className="btn btn-ghost text-xs" data-testid="widget-picker-toggle">
              <SlidersHorizontal size={14} /> Widget'lar
            </button>
            {pickerOpen && (
              <div className="absolute right-0 mt-2 w-64 card p-3 z-30 shadow-xl" data-testid="widget-picker-panel">
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Görünür Widget'lar</div>
                <div className="space-y-1.5 max-h-72 overflow-y-auto scrollbar">
                  {MAP_WIDGET_REGISTRY.map((w) => (
                    <label key={w.key} className="flex items-center gap-2 text-xs cursor-pointer">
                      <input type="checkbox" checked={enabledKeys.includes(w.key)} onChange={() => toggleWidget(w.key)} />
                      {w.title}
                    </label>
                  ))}
                </div>
                <button onClick={() => setPickerOpen(false)} className="btn text-xs w-full justify-center mt-3">
                  <Check size={13} /> Kapat
                </button>
              </div>
            )}
          </div>
          <button onClick={saveWorkspace} disabled={saving} className="btn btn-primary text-xs" data-testid="save-workspace-btn">
            <Save size={14} /> {saving ? "Kaydediliyor…" : "Görünümü Kaydet"}
          </button>
          {hasSavedWorkspace && (
            <button onClick={resetWorkspace} className="btn btn-ghost text-xs" data-testid="reset-workspace-btn">
              <RotateCcw size={14} /> Sıfırla
            </button>
          )}
        </div>
      </header>

      {/* IT-15 — Katmanlar / Basemap / Şekille Seç araç çubuğu */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative">
          <button onClick={() => setLayersOpen((o) => !o)} className="btn btn-ghost text-xs" data-testid="layers-toggle">
            <Layers size={14} /> Katmanlar
          </button>
          {layersOpen && (
            <div className="absolute left-0 mt-2 w-56 card p-3 z-30 shadow-xl" data-testid="layers-panel">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Görünür Katmanlar</div>
              <div className="space-y-1.5">
                {LAYER_CATALOG.map((l) => (
                  <label key={l.key} className="flex items-center gap-2 text-xs cursor-pointer">
                    <input type="checkbox" checked={visibleLayers.includes(l.key)} onChange={() => toggleLayer(l.key)} />
                    {l.label}
                  </label>
                ))}
              </div>
              <button onClick={() => setLayersOpen(false)} className="btn text-xs w-full justify-center mt-3">
                <Check size={13} /> Kapat
              </button>
            </div>
          )}
        </div>

        <div className="relative">
          <button onClick={() => setBasemapOpen((o) => !o)} className="btn btn-ghost text-xs" data-testid="basemap-toggle">
            <Globe size={14} /> {BASEMAPS[basemapKey].label}
          </button>
          {basemapOpen && (
            <div className="absolute left-0 mt-2 w-40 card p-2 z-30 shadow-xl" data-testid="basemap-panel">
              {Object.entries(BASEMAPS).map(([key, b]) => (
                <button
                  key={key}
                  onClick={() => { setBasemapKey(key); setBasemapOpen(false); }}
                  className={`w-full text-left text-xs px-2 py-1.5 rounded ${
                    basemapKey === key ? "bg-[var(--primary)]/15 text-[var(--primary)]" : "hover:bg-[var(--surface-2)]"
                  }`}
                  data-testid={`basemap-option-${key}`}
                >
                  {b.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={() => setDrawSelectActive((a) => !a)}
          className={`btn ${drawSelectActive ? "btn-primary" : "btn-ghost"} text-xs`}
          data-testid="draw-select-toggle"
        >
          <PenTool size={14} /> {drawSelectActive ? "Çiziliyor… (poligon/dikdörtgen/daire)" : "Şekille Seç"}
        </button>

        {/* IT-16 — Harita Snapshot (kaydet/paylaş) */}
        <div className="relative">
          <button
            onClick={() => { setSnapshotPanelOpen((o) => !o); if (!snapshotsLoaded) loadSnapshots(); }}
            className="btn btn-ghost text-xs"
            data-testid="snapshot-toggle"
          >
            <Camera size={14} /> Anlık Görüntü
          </button>
          {snapshotPanelOpen && (
            <div className="absolute left-0 mt-2 w-80 card p-3 z-30 shadow-xl space-y-3" data-testid="snapshot-panel">
              <div>
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Bu Görünümü Kaydet</div>
                <div className="flex items-center gap-2">
                  <input
                    className="input text-xs flex-1"
                    placeholder="Görünüm adı"
                    value={snapshotName}
                    onChange={(e) => setSnapshotName(e.target.value)}
                    data-testid="snapshot-name-input"
                  />
                  <button onClick={saveSnapshot} disabled={savingSnapshot} className="btn btn-primary text-xs" data-testid="snapshot-save-btn">
                    <Save size={13} /> {savingSnapshot ? "…" : "Kaydet"}
                  </button>
                </div>
                <label className="flex items-center gap-2 text-xs mt-2 cursor-pointer">
                  <input type="checkbox" checked={snapshotShared} onChange={(e) => setSnapshotShared(e.target.checked)} />
                  Tenant içinde paylaş
                </label>
              </div>

              <div className="border-t border-[var(--border)] pt-2">
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Kayıtlı Görünümler</div>
                <div className="space-y-1.5 max-h-56 overflow-y-auto scrollbar">
                  {snapshots.length === 0 && <div className="text-xs text-[var(--text-dim)]">Henüz kayıtlı görünüm yok.</div>}
                  {snapshots.map((s) => (
                    <div key={s.id} className="flex items-center justify-between gap-2 text-xs p-1.5 rounded hover:bg-[var(--surface-2)]">
                      <div className="min-w-0">
                        <div className="truncate">{s.name}{s.is_shared && <span className="text-[var(--primary)]"> · paylaşılan</span>}</div>
                        <div className="text-[10px] text-[var(--text-dim)] truncate">{s.created_by}</div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <button onClick={() => openSnapshot(s)} className="btn btn-ghost text-[10px] px-2 py-1" data-testid={`snapshot-open-${s.id}`}>Aç</button>
                        <button onClick={() => copySnapshotLink(s.id)} className="btn btn-ghost text-[10px] px-2 py-1" title="Bağlantıyı kopyala"><Link2 size={11} /></button>
                        {s.is_owner && (
                          <button onClick={() => deleteSnapshot(s.id)} className="btn btn-ghost text-[10px] px-2 py-1 text-red-400" title="Sil"><Trash2 size={11} /></button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <button onClick={() => setSnapshotPanelOpen(false)} className="btn text-xs w-full justify-center">
                <Check size={13} /> Kapat
              </button>
            </div>
          )}
        </div>

        {/* IT-17 — Mekânsal Zaman Makinesi aç/kapa */}
        <button
          onClick={() => setTimeMachineActive((a) => !a)}
          className={`btn ${timeMachineActive ? "btn-primary" : "btn-ghost"} text-xs`}
          data-testid="time-machine-toggle"
        >
          <History size={14} /> Zaman Makinesi
        </button>

        {/* IT-17 — AI Harita Asistanı (NL → Query Engine → seçim) */}
        <div className="relative">
          <button
            onClick={() => setAiPanelOpen((o) => !o)}
            className="btn btn-ghost text-xs"
            data-testid="ai-assistant-toggle"
          >
            <Sparkles size={14} /> AI Harita Asistanı
          </button>
          {aiPanelOpen && (
            <div className="absolute left-0 mt-2 w-96 card p-3 z-30 shadow-xl space-y-2" data-testid="ai-assistant-panel">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-1">
                Doğal Dilde Sor
              </div>
              <div className="flex items-center gap-2">
                <input
                  className="input text-xs flex-1"
                  placeholder="ör. Konya'daki en riskli 10 parseli göster"
                  value={aiQuery}
                  onChange={(e) => setAiQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") submitAiQuery(); }}
                  data-testid="ai-assistant-input"
                />
                <button onClick={submitAiQuery} disabled={aiBusy || !aiQuery.trim()} className="btn btn-primary text-xs" data-testid="ai-assistant-submit">
                  {aiBusy ? "…" : "Sor"}
                </button>
              </div>
              {aiResult && (
                <div className="text-xs p-2 rounded bg-[var(--surface-2)]">
                  <div>{aiResult.summary}</div>
                  <div className="text-[var(--text-dim)] mt-1">
                    {aiResult.result_count} parsel haritada seçildi
                    {!aiResult.ai_powered && " · anahtar kelime eşleştirmesi (AI servisi yapılandırılmamış)"}
                  </div>
                </div>
              )}
              <button onClick={() => setAiPanelOpen(false)} className="btn text-xs w-full justify-center">
                <Check size={13} /> Kapat
              </button>
            </div>
          )}
        </div>
      </div>

      {/* IT-17 — Zaman Makinesi slider (açıkken görünür) */}
      {timeMachineActive && (
        <div className="card p-4 mb-4 flex items-center gap-4 flex-wrap" data-testid="time-machine-panel">
          <button
            onClick={() => setTimeMachinePlaying((p) => !p)}
            className="btn btn-ghost text-xs shrink-0"
            data-testid="time-machine-play-toggle"
          >
            {timeMachinePlaying ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <input
            type="range"
            min={0}
            max={TIME_MACHINE_DATES.length - 1}
            value={timeMachineIdx}
            onChange={(e) => { setTimeMachinePlaying(false); setTimeMachineIdx(Number(e.target.value)); }}
            className="flex-1 min-w-[200px]"
            data-testid="time-machine-slider"
          />
          <div className="text-sm shrink-0 min-w-[140px]">
            {ndviLoading ? "Yükleniyor…" : formatTimeMachineDate(TIME_MACHINE_DATES[timeMachineIdx])}
          </div>
          <div className="text-[10px] text-[var(--text-dim)] w-full">
            Uydu/NDVI verisi SİMÜLEDİR (gerçek Sentinel Hub entegrasyonu FAZ 9.5) — harita renkleri
            ve widget'lar seçili tarihteki anlık görüntüyü yansıtır, veritabanındaki güncel değerler ETKİLENMEZ.
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {activeWidgets.map((w) => (
          <WidgetCard key={w.key} widget={w} ctx={ctx} />
        ))}
        {activeWidgets.length === 0 && (
          <div className="col-span-full text-xs text-[var(--text-dim)] p-4 text-center card">
            Hiç widget seçili değil — sağ üstteki "Widget'lar" menüsünden en az bir tanesini açın.
          </div>
        )}
      </div>

      <FilterPanel module="parcels" pageSize={1200} onResults={(items) => setFilterIds(new Set(items.map((i) => i.id)))} />

      {/* IT-15 — Çoklu parsel toplu işlemleri */}
      {selectedIds.size > 0 && (
        <div className="card p-4 mb-4" data-testid="bulk-actions-panel">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
            <div className="text-sm">
              <strong>{selectedIds.size}</strong> parsel seçili — toplu işlem uygulayın
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setBulkPanel((p) => (p === "update" ? null : "update"))}
                className={`btn ${bulkPanel === "update" ? "btn-primary" : "btn-ghost"} text-xs`}
                data-testid="bulk-update-toggle"
              >
                <Wrench size={14} /> Toplu Alan Güncelle
              </button>
              <button
                onClick={() => setBulkPanel((p) => (p === "task" ? null : "task"))}
                className={`btn ${bulkPanel === "task" ? "btn-primary" : "btn-ghost"} text-xs`}
                data-testid="bulk-task-toggle"
              >
                <ListChecks size={14} /> Toplu Görev Oluştur
              </button>
            </div>
          </div>

          {bulkMsg && <div className="text-xs text-[var(--primary)] mb-3">{bulkMsg}</div>}

          {bulkPanel === "update" && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Sulama</label>
                <select className="input" value={bulkForm.irrigation || ""} onChange={(e) => setBulkForm((f) => ({ ...f, irrigation: e.target.value }))}>
                  <option value="">Değiştirme</option>
                  {["Damla", "Yağmurlama", "Karık", "Yok"].map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Toprak Tipi</label>
                <select className="input" value={bulkForm.soil_type || ""} onChange={(e) => setBulkForm((f) => ({ ...f, soil_type: e.target.value }))}>
                  <option value="">Değiştirme</option>
                  {["Killi", "Kumlu", "Tınlı", "Kireçli", "Killi-Tınlı"].map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Risk Seviyesi</label>
                <select className="input" value={bulkForm.risk_level || ""} onChange={(e) => setBulkForm((f) => ({ ...f, risk_level: e.target.value }))}>
                  <option value="">Değiştirme</option>
                  {Object.entries(RISK_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </div>
              <button onClick={submitBulkUpdate} disabled={bulkBusy} className="btn btn-primary text-xs justify-center" data-testid="bulk-update-submit">
                <Check size={14} /> {bulkBusy ? "Uygulanıyor…" : `${selectedIds.size} Parsele Uygula`}
              </button>
            </div>
          )}

          {bulkPanel === "task" && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Görev Tipi</label>
                <select className="input" value={bulkForm.task_type || ""} onChange={(e) => setBulkForm((f) => ({ ...f, task_type: e.target.value }))}>
                  <option value="">Seç...</option>
                  {["toprak işleme", "ekim", "gübreleme", "ilaçlama", "sulama", "hasat", "nakliye"].map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Planlanan Tarih</label>
                <input type="date" className="input" value={bulkForm.scheduled_date || ""} onChange={(e) => setBulkForm((f) => ({ ...f, scheduled_date: e.target.value }))} />
              </div>
              <div className="md:col-span-1">
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Notlar</label>
                <input className="input" value={bulkForm.notes || ""} onChange={(e) => setBulkForm((f) => ({ ...f, notes: e.target.value }))} />
              </div>
              <button
                onClick={submitBulkTask}
                disabled={bulkBusy || !bulkForm.task_type || !bulkForm.scheduled_date}
                className="btn btn-primary text-xs justify-center"
                data-testid="bulk-task-submit"
              >
                <Check size={14} /> {bulkBusy ? "Oluşturuluyor…" : `${selectedIds.size} Parsele Görev Oluştur`}
              </button>
            </div>
          )}
        </div>
      )}

      <div className="card overflow-hidden" style={{ height: 560 }}>
        <MapContainer center={initialView.center} zoom={initialView.zoom} style={{ height: "100%", width: "100%" }}>
          <TileLayer
            attribution={BASEMAPS[basemapKey].attribution}
            url={BASEMAPS[basemapKey].url}
          />
          <MapSync onChange={onMapChange} />

          {/* İdari Sınırlar katmanı — IT-13.6/Parcels.jsx ile aynı desen */}
          {visibleLayers.includes("admin_areas") && adminAreas.map((a) => {
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

          {/* Saha Görevleri katmanı — IT-23 (IT-22'nin field_tasks modeli) */}
          {visibleLayers.includes("field_tasks") && fieldTasksWithCentroid.map((t) => (
            <CircleMarker
              key={t.id}
              center={t.__centroid}
              radius={7}
              pathOptions={{
                color: FIELD_TASK_STATUS_COLOR[t.status] || "#94a3b8",
                fillColor: FIELD_TASK_STATUS_COLOR[t.status] || "#94a3b8",
                fillOpacity: 0.85, weight: 2,
              }}
            >
              <Popup>
                <div style={{ minWidth: 160 }}>
                  <div style={{ fontWeight: 600 }}>{taskTypesById.get(t.task_type_id)?.name || "Görev"}</div>
                  <div style={{ fontSize: 12, opacity: 0.8, marginTop: 2 }}>{TASK_STATUS_LABEL_MAP[t.status] || t.status}</div>
                  {t.planned_date && <div style={{ fontSize: 11, opacity: 0.7, marginTop: 2 }}>Planlanan: {t.planned_date}</div>}
                  <button
                    onClick={() => nav(`/saha-operasyonlari?task=${t.id}`)}
                    className="btn btn-ghost text-[10px] px-2 py-1"
                    style={{ marginTop: 6 }}
                  >
                    Detaya Git
                  </button>
                </div>
              </Popup>
            </CircleMarker>
          ))}

          {/* Şekille seç aracı — IT-15 */}
          <MapDrawTools active={drawSelectActive} mode="select" onCreated={onDrawSelection} />
          {visibleLayers.includes("parcels") && scopedParcels.map((p) => {
            if (!p.geometry) return null;
            const isSelected = selectedIds.has(p.id);
            const color = isSelected ? SELECT_COLOR : (RISK_COLORS[p.risk_level] || "#4ade80");
            return (
              <Polygon
                key={p.id}
                positions={p.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])}
                pathOptions={{ color, fillColor: color, fillOpacity: isSelected ? 0.55 : 0.35, weight: isSelected ? 3 : 1.5 }}
                eventHandlers={{ click: () => toggleSelect(p.id) }}
              >
                <Popup minWidth={220}>
                  {/* IT-16 — zenginleştirilmiş parsel popup'ı (hızlı işlem merkezi) */}
                  <div style={{ minWidth: 220 }}>
                    <div style={{ fontWeight: 600 }}>{p.parcel_code} — {p.name}</div>
                    <div style={{ fontSize: 12, opacity: 0.8 }}>{farmersById.get(p.farmer_id)?.full_name || "—"}</div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>
                      {p.area_dekar?.toFixed(1)} dekar · {p.soil_type} · {p.irrigation}
                    </div>
                    {p.risk_label && (
                      <div style={{ fontSize: 11, marginTop: 4, color: RISK_COLORS[p.risk_level] || "#4ade80" }}>{p.risk_label}</div>
                    )}
                    {latestCycleByParcel.get(p.id) && (
                      <div style={{ fontSize: 11, marginTop: 4, opacity: 0.7 }}>
                        Sezon {latestCycleByParcel.get(p.id).year} · {CYCLE_STATUS_LABELS[latestCycleByParcel.get(p.id).status] || latestCycleByParcel.get(p.id).status}
                      </div>
                    )}

                    <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                      <button onClick={() => nav(moduleDetailPath("parcels", p))} className="btn btn-ghost text-[10px] px-2 py-1">
                        Detaya Git
                      </button>
                      {p.__centroid && (
                        <a
                          href={directionsUrl(p.__centroid)}
                          target="_blank"
                          rel="noreferrer"
                          className="btn btn-ghost text-[10px] px-2 py-1"
                          style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                        >
                          <Navigation size={11} /> Yol Tarifi
                        </a>
                      )}
                      <button
                        onClick={() => { setQuickTaskParcelId(quickTaskParcelId === p.id ? null : p.id); setQuickTaskMsg(""); }}
                        className="btn btn-ghost text-[10px] px-2 py-1"
                        style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                      >
                        <Plus size={11} /> Görev
                      </button>
                      <button
                        onClick={() => { setQuickFieldTaskParcelId(quickFieldTaskParcelId === p.id ? null : p.id); setQuickFieldTaskMsg(""); }}
                        className="btn btn-ghost text-[10px] px-2 py-1"
                        style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                        data-testid={`quick-field-task-btn-${p.id}`}
                      >
                        <Plus size={11} /> Saha Görevi
                      </button>
                    </div>

                    {quickFieldTaskParcelId === p.id && (
                      <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }} data-testid="quick-field-task-form">
                        <select
                          className="input text-[10px]"
                          value={quickFieldTaskForm.task_type_id || ""}
                          onChange={(e) => setQuickFieldTaskForm((f) => ({ ...f, task_type_id: e.target.value }))}
                        >
                          <option value="">Görev tipi seç...</option>
                          {taskTypes.map((tt) => <option key={tt.id} value={tt.id}>{tt.name}</option>)}
                        </select>
                        <select
                          className="input text-[10px]"
                          value={quickFieldTaskForm.assigned_to || ""}
                          onChange={(e) => setQuickFieldTaskForm((f) => ({ ...f, assigned_to: e.target.value }))}
                        >
                          <option value="">Personel seç...</option>
                          {assignableStaff.map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
                        </select>
                        <input
                          type="date"
                          className="input text-[10px]"
                          value={quickFieldTaskForm.planned_date || ""}
                          onChange={(e) => setQuickFieldTaskForm((f) => ({ ...f, planned_date: e.target.value }))}
                        />
                        <button
                          onClick={() => submitQuickFieldTask(p.id)}
                          disabled={quickFieldTaskBusy || !quickFieldTaskForm.task_type_id || !quickFieldTaskForm.assigned_to || !quickFieldTaskForm.planned_date}
                          className="btn btn-primary text-[10px] justify-center"
                          data-testid="submit-quick-field-task"
                        >
                          {quickFieldTaskBusy ? "Oluşturuluyor…" : "Saha Görevi Oluştur"}
                        </button>
                        {quickFieldTaskMsg && <div style={{ fontSize: 10, color: "#ef4444" }}>{quickFieldTaskMsg}</div>}
                      </div>
                    )}

                    {quickTaskParcelId === p.id && (
                      <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                        <select
                          className="input text-[10px]"
                          value={quickTaskForm.task_type || ""}
                          onChange={(e) => setQuickTaskForm((f) => ({ ...f, task_type: e.target.value }))}
                        >
                          <option value="">Görev tipi seç...</option>
                          {["toprak işleme", "ekim", "gübreleme", "ilaçlama", "sulama", "hasat", "nakliye"].map((v) => (
                            <option key={v} value={v}>{v}</option>
                          ))}
                        </select>
                        <input
                          type="date"
                          className="input text-[10px]"
                          value={quickTaskForm.scheduled_date || ""}
                          onChange={(e) => setQuickTaskForm((f) => ({ ...f, scheduled_date: e.target.value }))}
                        />
                        <button
                          onClick={() => submitQuickTask(p.id)}
                          disabled={quickTaskBusy || !quickTaskForm.task_type || !quickTaskForm.scheduled_date}
                          className="btn btn-primary text-[10px] justify-center"
                        >
                          {quickTaskBusy ? "Oluşturuluyor…" : "Oluştur"}
                        </button>
                        {quickTaskMsg && <div style={{ fontSize: 10, color: "#ef4444" }}>{quickTaskMsg}</div>}
                      </div>
                    )}
                  </div>
                </Popup>
              </Polygon>
            );
          })}
        </MapContainer>
      </div>
    </div>
  );
}
