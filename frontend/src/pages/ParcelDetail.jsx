/**
 * PARSEL DETAY SAYFASI
 *
 * Bir parselin tüm bilgilerini gösterir:
 * - Harita üzerinde konumu
 * - Sahip çiftçi bilgisi
 * - Toprak analizleri
 * - Sulama olayları
 * - Verim geçmişi
 * - Ekim geçmişi
 * - Görev listesi
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/api";
import { MapContainer, TileLayer, Polygon } from "react-leaflet";
import { ArrowLeft, MapPin, Droplets, FlaskConical, Sprout, Award, Satellite, Radio, Plane, Pencil, Check, X, Plus, Calendar, Trash2 } from "lucide-react";
import DynamicFieldsSection from "@/components/DynamicFieldsSection";
import DocumentsTab from "@/components/DocumentsTab";
import Breadcrumb from "@/components/Breadcrumb";
import FavoriteButton from "@/components/FavoriteButton";
import { pushRecentlyViewed } from "@/lib/recentlyViewed";
import { QuickAddPanel } from "@/components/QuickAdd";
import { Zap } from "lucide-react";
import GeoFileImport from "@/components/GeoFileImport";
import VisitHistory from "@/components/VisitHistory";
import FarmerSelect from "@/components/FarmerSelect";
import RemoteSensingPanel from "@/components/RemoteSensingPanel";

const RISK_COLORS = { yesil: "#4ade80", sari: "#fbbf24", turuncu: "#fb923c", kirmizi: "#ef4444" };
const SOIL_TYPES = ["Killi", "Kumlu", "Tınlı", "Kireçli", "Killi-Tınlı"];
const IRRIGATION_TYPES = ["Damla", "Yağmurlama", "Karık", "Yok"];
const CYCLE_STATUS_LABELS = { planning: "Planlama", active: "Aktif", harvesting: "Hasat", completed: "Tamamlandı", cancelled: "İptal" };
const CYCLE_STATUS_BADGE = { planning: "badge-neutral", active: "badge-b", harvesting: "badge-c", completed: "badge-a", cancelled: "badge-d" };

export default function ParcelDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [fieldDefs, setFieldDefs] = useState([]);          // IT-02 — Form Yönetimi alan tanımları (parcels)
  const [farmers, setFarmers] = useState([]);              // çiftçi atama seçici için

  // IT-04 — Düzenleme modu
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  // IT-06 — Üretim Sezonları (ProductionCycle)
  const [cycles, setCycles] = useState([]);
  const [showNewCycle, setShowNewCycle] = useState(false);
  const [newCycle, setNewCycle] = useState({ year: new Date().getFullYear(), season: "Ana Ürün", crop: "Şeker Pancarı" });
  const [cycleError, setCycleError] = useState("");
  const [cycleSaving, setCycleSaving] = useState(false);

  useEffect(() => {
    api.get(`/parcels/${id}`).then((r) => {
      setData(r.data);
      pushRecentlyViewed({ module: "parcels", id, label: r.data.parcel.name, path: `/parseller/${id}` });
    });
  }, [id]);
  useEffect(() => {
    api.get("/field-definitions", { params: { module: "parcels" } }).then((r) =>
      setFieldDefs(r.data.filter((f) => f.is_active !== false && f.visible).sort((a, b) => a.order - b.order))
    );
  }, []);
  useEffect(() => {
    api.get("/farmers", { params: { limit: 2000 } })
      .then((r) => setFarmers(Array.isArray(r.data) ? r.data : (r.data?.farmers || [])))
      .catch(() => setFarmers([]));
  }, []);
  const loadCycles = () => api.get("/production-cycles", { params: { parcel_id: id } }).then((r) => setCycles(r.data));
  useEffect(() => { loadCycles(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function createCycle() {
    setCycleSaving(true);
    setCycleError("");
    try {
      await api.post("/production-cycles", {
        farmer_id: data.parcel.farmer_id, parcel_id: id,
        year: Number(newCycle.year), season: newCycle.season, crop: newCycle.crop,
      });
      setShowNewCycle(false);
      setNewCycle({ year: new Date().getFullYear(), season: "Ana Ürün", crop: "Şeker Pancarı" });
      loadCycles();
    } catch (err) {
      setCycleError(err.response?.data?.detail || "Sezon oluşturulamadı");
    } finally {
      setCycleSaving(false);
    }
  }

  function startEdit() {
    setEditForm({
      farmer_id: data.parcel.farmer_id || null,
      name: data.parcel.name, village: data.parcel.village, area_dekar: data.parcel.area_dekar,
      soil_type: data.parcel.soil_type, irrigation: data.parcel.irrigation,
      ...Object.fromEntries(fieldDefs.map((f) => [f.field_key, data.parcel[f.field_key] ?? ""])),
    });
    setSaveError("");
    setEditing(true);
  }

  function cancelEdit() {
    setEditing(false);
    setSaveError("");
  }

  async function saveEdit() {
    setSaving(true);
    setSaveError("");
    try {
      await api.put(`/parcels/${id}`, { ...editForm, area_dekar: Number(editForm.area_dekar) });
      const r = await api.get(`/parcels/${id}`);
      setData(r.data);
      setEditing(false);
    } catch (err) {
      setSaveError(err.response?.data?.detail || "Kaydedilemedi, alanları kontrol edin.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteParcel() {
    if (!window.confirm("Bu parsel silinsin mi?\n(Kayıt arşivlenir — geri alınabilir. Bağlı sözleşme varsa engellenir.)")) return;
    try {
      await api.delete(`/parcels/${id}`);
      nav("/parseller");
    } catch (err) {
      alert(err.response?.data?.detail || "Silinemedi.");
    }
  }

  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const { parcel, farmer, plantings, soil_samples, irrigation_events, yields, tasks, iot_sensors = [], drone_missions = [] } = data;
  const centerLat = parcel.geometry?.coordinates[0][0][1] || 39.5;
  const centerLng = parcel.geometry?.coordinates[0][0][0] || 33.5;
  const riskColor = RISK_COLORS[parcel.risk_level] || "#4ade80";

  return (
    <div className="p-8 max-w-[1600px]" data-testid="parcel-detail-page">
      <Breadcrumb items={[{ label: "Parseller", to: "/parseller" }, { label: parcel.name }]} />

      <button onClick={() => nav("/parseller")} className="btn btn-ghost mb-4 text-sm">
        <ArrowLeft size={14}/> Parsel listesi
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        {/* SOL: HARİTA */}
        <div className="card overflow-hidden lg:col-span-2" style={{ height: 380 }}>
          {parcel.geometry && (
            <MapContainer center={[centerLat, centerLng]} zoom={14} style={{ height: "100%", width: "100%" }}>
              <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap"/>
              <Polygon
                positions={parcel.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])}
                pathOptions={{ color: riskColor, fillColor: riskColor, fillOpacity: 0.5, weight: 3 }}
              />
            </MapContainer>
          )}
        </div>

        {/* SAĞ: ÖZET BİLGİ */}
        <div className="card p-5 space-y-4">
          <div>
            <div className="font-mono text-xs text-[var(--primary)]">{parcel.parcel_code}</div>
            <div className="font-display text-2xl mt-1 flex items-center gap-2">
              {parcel.name}
              <FavoriteButton module="parcels" entityId={id} label={parcel.name} />
            </div>
          </div>
          <div className="text-sm text-[var(--text-dim)] flex items-center gap-2">
            <MapPin size={14}/> {parcel.village} · {parcel.active_season} sezonu
          </div>
          {parcel.risk_level && (
            <div className="flex items-center gap-2 text-sm p-2.5 rounded-lg" style={{ background: `${riskColor}15`, color: riskColor }}>
              <Satellite size={14}/>
              <span className="font-medium">{parcel.risk_label}</span>
              <span className="text-xs opacity-80 ml-auto">NDVI {parcel.ndvi_latest}</span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 pt-3 border-t border-[var(--border)]">
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Alan</div><div className="font-display text-xl">{parcel.area_dekar} <span className="text-xs">da</span></div></div>
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Ürün</div><div className="font-medium">{parcel.current_crop}</div></div>
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Toprak</div><div className="font-medium">{parcel.soil_type}</div></div>
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Sulama</div><div className="font-medium">{parcel.irrigation}</div></div>
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Ekilebilir Alan</div><div className="font-medium">{parcel.ekilebilir_alan_dekar != null ? `${parcel.ekilebilir_alan_dekar} da` : "—"}</div></div>
            <div>
              <div className="text-[10px] text-[var(--text-dim)] uppercase">Ekim Durumu</div>
              <div className="font-medium">
                {parcel.ekim_durumu === "ekili" ? "🌱 Ekili"
                  : parcel.ekim_durumu === "sokuldu" ? "🚜 Söküldü"
                  : parcel.ekim_durumu === "ekili_degil" ? "Ekili değil" : "—"}
                {parcel.son_ndvi != null && <span className="text-[10px] text-[var(--text-dim)]"> · NDVI {parcel.son_ndvi}</span>}
              </div>
              {parcel.crop_status_date && (
                <div className="text-[9px] text-[var(--text-dim)]">
                  {parcel.crop_status_source} · {new Date(parcel.crop_status_date).toLocaleDateString("tr-TR")}
                </div>
              )}
            </div>
          </div>

          <div className="pt-3 border-t border-[var(--border)]">
            <div className="text-[10px] text-[var(--text-dim)] uppercase mb-1">SAHİBİ</div>
            {farmer ? (
              <button onClick={() => nav(`/ciftciler/${farmer.id}`)} className="text-left w-full hover:bg-[var(--surface-2)] p-2 rounded transition-colors">
                <div className="text-sm">{farmer.full_name}</div>
                <div className="text-xs text-[var(--text-dim)]">{farmer.member_no} · {farmer.phone}</div>
              </button>
            ) : (
              <div className="text-sm text-amber-400 p-2 flex items-center gap-2">
                Atanmamış — yukarıdaki <span className="font-medium">"Düzenle"</span> ile çiftçi atayın
              </div>
            )}
          </div>

          {/* #6 — SORUMLU (köyden miras alınır) */}
          <div className="pt-3 border-t border-[var(--border)]">
            <div className="text-[10px] text-[var(--text-dim)] uppercase mb-1">SORUMLU PERSONEL</div>
            {data.responsible ? (
              <div className="p-2">
                <div className="text-sm">{data.responsible.full_name}</div>
                <div className="text-[11px] text-[var(--text-dim)]">
                  {data.responsible.role} · köy: {data.responsible.source_area_name}
                </div>
              </div>
            ) : (
              <div className="text-xs text-[var(--text-dim)] p-2">
                Bu köy için sorumlu atanmamış — İdari Alanlar'dan köye sorumlu personel atayın.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* HIZLI İŞLEMLER — IT-13 (context-aware CRUD: parcel_id/farmer_id otomatik dolar) */}
      <div className="card p-5 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Zap size={16} className="text-[var(--primary)]"/>
          <h3 className="font-display text-lg">Hızlı İşlemler</h3>
        </div>
        <div className="flex flex-wrap gap-3">
          <QuickAddPanel
            title="Yeni Sözleşme"
            testId="quick-contract-add"
            extraModule="contracts"
            fields={[
              { name: "season", label: "Sezon (Yıl)", type: "number", required: true, default: new Date().getFullYear() },
              { name: "variety", label: "Çeşit", required: true },
              { name: "kota_dekar", label: "Kota (dekar)", type: "number", step: "0.1", required: true },
              { name: "kota_ton", label: "Kota (ton)", type: "number", step: "0.1", required: true },
            ]}
            onSubmit={async (v) => {
              await api.post("/contracts", {
                ...v, parcel_id: id, farmer_id: parcel.farmer_id,
                season: Number(v.season), kota_dekar: Number(v.kota_dekar), kota_ton: Number(v.kota_ton),
              });
            }}
          />
          <QuickAddPanel
            title="Yeni Görev"
            testId="quick-task-add"
            fields={[
              { name: "task_type", label: "Görev Tipi", type: "select", required: true,
                options: ["toprak işleme", "ekim", "gübreleme", "ilaçlama", "sulama", "hasat", "nakliye"].map((t) => ({ value: t, label: t })) },
              { name: "scheduled_date", label: "Planlanan Tarih", type: "date", required: true },
              { name: "notes", label: "Notlar", type: "textarea", span2: true },
            ]}
            onSubmit={async (v) => {
              await api.post("/operations/tasks", {
                ...v, parcel_id: id, scheduled_date: new Date(v.scheduled_date).toISOString(),
              });
            }}
          />
        </div>
      </div>

      {/* SINIR İÇE AKTAR — IT-13.5 (SHP/GeoJSON/KML/DXF → WGS84 → parsel geometrisi)
          + IT-16 (TKGM özellikleri algılanırsa il/ilçe/mahalle/ada/parsel de günceller) */}
      <div className="mb-4">
        <GeoFileImport
          onConfirm={async (geometry, tkgmFields) => {
            await api.put(`/parcels/${id}`, { geometry, ...(tkgmFields || {}) });
            const r = await api.get(`/parcels/${id}`);
            setData(r.data);
          }}
        />
      </div>

      {/* ÜRETİM SEZONLARI — IT-06 (ProductionCycle) */}
      <div className="card p-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Calendar size={16} className="text-[var(--primary)]"/>
            <h3 className="font-display text-lg">Üretim Sezonları ({cycles.length})</h3>
          </div>
          {!showNewCycle && (
            <button onClick={() => setShowNewCycle(true)} className="btn btn-ghost text-xs" data-testid="cycle-new-start">
              <Plus size={13}/> Yeni Sezon
            </button>
          )}
        </div>

        {showNewCycle && (
          <div className="p-3 rounded-lg bg-[var(--surface-2)] mb-3 space-y-3">
            {cycleError && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded">{cycleError}</div>}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Yıl *</label>
                <input className="input" type="number" value={newCycle.year}
                       onChange={(e) => setNewCycle((c) => ({ ...c, year: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Sezon</label>
                <input className="input" value={newCycle.season}
                       onChange={(e) => setNewCycle((c) => ({ ...c, season: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Ürün</label>
                <input className="input" value={newCycle.crop}
                       onChange={(e) => setNewCycle((c) => ({ ...c, crop: e.target.value }))} />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => { setShowNewCycle(false); setCycleError(""); }} className="btn btn-ghost text-xs text-red-400">
                <X size={13}/> İptal
              </button>
              <button onClick={createCycle} disabled={cycleSaving} className="btn btn-primary text-xs" data-testid="cycle-new-save">
                <Check size={13}/> {cycleSaving ? "Kaydediliyor…" : "Sezonu Oluştur"}
              </button>
            </div>
          </div>
        )}

        {cycles.length === 0 ? (
          <div className="text-center text-[var(--text-dim)] py-6 text-sm">Bu parsel için henüz üretim sezonu yok</div>
        ) : (
          <div className="space-y-2">
            {cycles.map((c) => (
              <div key={c.id} onClick={() => nav(`/uretim-sezonlari/${c.id}`)}
                   className="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] hover:border-[var(--primary)]/40 cursor-pointer transition-colors"
                   data-testid={`cycle-row-${c.year}`}>
                <div>
                  <div className="text-sm font-medium">{c.year} — {c.season}</div>
                  <div className="text-xs text-[var(--text-dim)]">{c.crop}</div>
                </div>
                <span className={`badge ${CYCLE_STATUS_BADGE[c.status] || "badge-neutral"}`}>
                  {CYCLE_STATUS_LABELS[c.status] || c.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* UZAKTAN ALGILAMA (EOSDA) — tekil parsel: analiz güncelle + NDVI zaman serisi + gün-gün slider */}
      <RemoteSensingPanel parcelId={id} />

      {/* GENEL BİLGİLER — IT-02 dinamik alanlar (Form Yönetimi'nden) + IT-04 düzenleme modu.
          NOT: fieldDefs boş olsa bile kart her zaman render edilir — aksi halde
          "Düzenle" butonuna hiç ulaşılamaz (temel alan düzenleme dinamik alanlardan
          bağımsız olmalı). */}
      <div className="card p-5 mb-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-lg">Genel Bilgiler</h3>
            {!editing ? (
              <div className="flex items-center gap-2">
                <button onClick={startEdit} className="btn btn-ghost text-xs" data-testid="parcel-edit-start">
                  <Pencil size={13}/> Düzenle
                </button>
                <button onClick={deleteParcel} className="btn btn-ghost text-xs text-red-400" data-testid="parcel-delete">
                  <Trash2 size={13}/> Sil
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button onClick={cancelEdit} disabled={saving} className="btn btn-ghost text-xs text-red-400" data-testid="parcel-edit-cancel">
                  <X size={13}/> İptal
                </button>
                <button onClick={saveEdit} disabled={saving} className="btn btn-primary text-xs" data-testid="parcel-edit-save">
                  <Check size={13}/> {saving ? "Kaydediliyor…" : "Kaydet"}
                </button>
              </div>
            )}
          </div>

          {saveError && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-3">{saveError}</div>}

          {editing ? (
            <div className="space-y-5">
              <div>
                <div className="text-xs font-medium text-[var(--primary)] mb-2">Sahibi (Çiftçi)</div>
                <div className="max-w-md">
                  <FarmerSelect
                    farmers={farmers}
                    value={editForm.farmer_id || null}
                    onChange={(fid) => setEditForm((f) => {
                      const far = farmers.find((x) => x.id === fid);
                      // Köy boşsa (atanmamış import edilen parsel) çiftçinin köyünü otomatik doldur.
                      return { ...f, farmer_id: fid, village: f.village || far?.village || "" };
                    })}
                    placeholder="Çiftçi ara ve ata…"
                    testId="parcel-farmer-select"
                  />
                  <p className="text-[10px] text-[var(--text-dim)] mt-1">
                    Atanmamış parseller için çiftçi seçin; bölge otomatik güncellenir.
                  </p>
                </div>
              </div>
              <div>
                <div className="text-xs font-medium text-[var(--primary)] mb-2">Temel Bilgiler</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <label className="text-xs text-[var(--text-dim)] mb-1 block">Parsel Adı *</label>
                    <input className="input" value={editForm.name ?? ""} required
                           onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} />
                  </div>
                  <div>
                    <label className="text-xs text-[var(--text-dim)] mb-1 block">Köy *</label>
                    <input className="input" value={editForm.village ?? ""} required
                           onChange={(e) => setEditForm((f) => ({ ...f, village: e.target.value }))} />
                  </div>
                  <div>
                    <label className="text-xs text-[var(--text-dim)] mb-1 block">Alan (dekar) *</label>
                    <input className="input" type="number" step="0.1" value={editForm.area_dekar ?? ""} required
                           onChange={(e) => setEditForm((f) => ({ ...f, area_dekar: e.target.value }))} />
                  </div>
                  <div>
                    <label className="text-xs text-[var(--text-dim)] mb-1 block">Toprak Tipi *</label>
                    <select className="input" value={editForm.soil_type ?? ""} required
                            onChange={(e) => setEditForm((f) => ({ ...f, soil_type: e.target.value }))}>
                      {SOIL_TYPES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-[var(--text-dim)] mb-1 block">Sulama *</label>
                    <select className="input" value={editForm.irrigation ?? ""} required
                            onChange={(e) => setEditForm((f) => ({ ...f, irrigation: e.target.value }))}>
                      {IRRIGATION_TYPES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                </div>
              </div>
              <DynamicFieldsSection
                module="parcels"
                entityId={id}
                values={editForm}
                onChange={(key, val) => setEditForm((f) => ({ ...f, [key]: val }))}
                title=""
              />
            </div>
          ) : fieldDefs.length === 0 ? (
            <div className="text-[var(--text-dim)] text-sm">Bu modül için henüz ek alan tanımlanmamış.</div>
          ) : (
            Object.entries(
              fieldDefs.reduce((acc, f) => { (acc[f.tab || "Diğer"] = acc[f.tab || "Diğer"] || []).push(f); return acc; }, {})
            ).map(([tabName, defs]) => (
              <div key={tabName} className="mb-4 last:mb-0">
                <div className="text-xs font-medium text-[var(--primary)] mb-2">{tabName}</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-3">
                  {defs.map((f) => {
                    const raw = parcel[f.field_key];
                    let display = raw === undefined || raw === null || raw === "" ? "—" : String(raw);
                    if (typeof raw === "boolean") display = raw ? "Evet" : "Hayır";
                    return (
                      <div key={f.id}>
                        <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider">{f.label}</div>
                        <div className="text-sm mt-0.5">{display}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>

      {/* BELGELER — IT-04 genel doküman yükleme */}
      <div className="mb-4">
        <DocumentsTab module="parcels" entityId={id} />
      </div>

      {/* SEKMELER — Veri tablolarına grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* TOPRAK ANALİZLERİ */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <FlaskConical size={16} className="text-[var(--primary)]"/>
            <h3 className="font-display text-lg">Toprak Analizleri ({soil_samples.length})</h3>
          </div>
          <div className="max-h-[300px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5">Tarih</th><th className="p-2.5">pH</th>
                  <th className="p-2.5">N/P/K</th><th className="p-2.5">Öneri</th>
                </tr>
              </thead>
              <tbody>
                {soil_samples.map((s) => (
                  <tr key={s.id} className="border-b border-[var(--border)]">
                    <td className="p-2.5 text-xs">{s.date}</td>
                    <td className="p-2.5">{s.ph}</td>
                    <td className="p-2.5 text-xs">{s.n_ppm}/{s.p_ppm}/{s.k_ppm}</td>
                    <td className="p-2.5 text-xs text-[var(--primary)]">{s.recommendation}</td>
                  </tr>
                ))}
                {soil_samples.length === 0 && <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Toprak analizi yok</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {/* SULAMA OLAYLARI */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Droplets size={16} className="text-blue-400"/>
            <h3 className="font-display text-lg">Sulama Olayları ({irrigation_events.length})</h3>
          </div>
          <div className="max-h-[300px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5">Tarih</th><th className="p-2.5">Yöntem</th>
                  <th className="p-2.5">Su (m³)</th><th className="p-2.5">Nem</th>
                </tr>
              </thead>
              <tbody>
                {irrigation_events.map((e) => (
                  <tr key={e.id} className="border-b border-[var(--border)]">
                    <td className="p-2.5 text-xs">{e.date}</td>
                    <td className="p-2.5 capitalize">{e.method}</td>
                    <td className="p-2.5 text-[var(--primary)]">{e.water_m3}</td>
                    <td className="p-2.5 text-xs">{e.moisture_before}%→{e.moisture_after}%</td>
                  </tr>
                ))}
                {irrigation_events.length === 0 && <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Sulama kaydı yok</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {/* EKİM GEÇMİŞİ */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Sprout size={16} className="text-emerald-400"/>
            <h3 className="font-display text-lg">Ekim Geçmişi ({plantings.length})</h3>
          </div>
          <div className="max-h-[280px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5">Sezon</th><th className="p-2.5">Çeşit</th>
                  <th className="p-2.5">Ekim</th><th className="p-2.5">Aşama</th>
                </tr>
              </thead>
              <tbody>
                {plantings.map((p) => (
                  <tr key={p.id} className="border-b border-[var(--border)]">
                    <td className="p-2.5 font-medium">{p.season}</td>
                    <td className="p-2.5">{p.variety}</td>
                    <td className="p-2.5 text-xs">{p.planting_date}</td>
                    <td className="p-2.5"><span className="badge badge-b">{p.stage}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* VERİM */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Award size={16} className="text-amber-400"/>
            <h3 className="font-display text-lg">Verim Geçmişi ({yields.length})</h3>
          </div>
          <div className="max-h-[280px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5">Sezon</th><th className="p-2.5">Beklenen</th>
                  <th className="p-2.5">Gerçek</th><th className="p-2.5">Polar</th>
                </tr>
              </thead>
              <tbody>
                {yields.map((y) => (
                  <tr key={y.id} className="border-b border-[var(--border)]">
                    <td className="p-2.5 font-medium">{y.season}</td>
                    <td className="p-2.5 text-[var(--text-dim)]">{y.expected_ton.toFixed(1)} t</td>
                    <td className="p-2.5 text-[var(--primary)]">{y.actual_ton.toFixed(1)} t</td>
                    <td className="p-2.5">%{y.polar_oran}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        {/* IoT SENSÖRLER */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Radio size={16} className="text-violet-400"/>
            <h3 className="font-display text-lg">IoT Sensörler ({iot_sensors.length})</h3>
          </div>
          <div className="max-h-[280px] overflow-y-auto scrollbar p-4 space-y-2">
            {iot_sensors.map((s) => (
              <div key={s.id} className="flex items-center justify-between text-sm p-2 rounded bg-[var(--surface-2)]">
                <div>
                  <div className="font-mono text-xs">{s.sensor_code}</div>
                  <div className="text-xs text-[var(--text-dim)]">Nem %{s.nem_pct} · {s.sicaklik_c}°C</div>
                </div>
                <span className={`badge ${s.status === "aktif" ? "badge-a" : "badge-d"}`}>{s.status}</span>
              </div>
            ))}
            {iot_sensors.length === 0 && <div className="text-center text-[var(--text-dim)] py-6">Bu parselde sensör yok</div>}
          </div>
        </div>

        {/* DRONE GÖREVLERİ */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Plane size={16} className="text-indigo-400"/>
            <h3 className="font-display text-lg">Drone Görevleri ({drone_missions.length})</h3>
          </div>
          <div className="max-h-[280px] overflow-y-auto scrollbar p-4 space-y-2">
            {drone_missions.map((m) => (
              <div key={m.id} className="text-sm p-2 rounded bg-[var(--surface-2)]">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs">{m.mission_code}</span>
                  <span className="text-xs text-[var(--text-dim)]">{m.flight_date?.slice(0, 10)}</span>
                </div>
                <div className="text-xs text-[var(--text-dim)] mt-1">{m.notes}</div>
              </div>
            ))}
            {drone_missions.length === 0 && <div className="text-center text-[var(--text-dim)] py-6">Bu parselde drone görevi yok</div>}
          </div>
        </div>

        {/* ZİYARET GEÇMİŞİ — IT-23 */}
        <VisitHistory parcelId={parcel.id} />
      </div>
    </div>
  );
}
