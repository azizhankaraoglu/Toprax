/**
 * EKİM KAYDI (SON HAL) — route /ekim (eski adı "Ekim Planlama", Other.jsx'ten
 * kendi dosyasına taşındı ve büyütüldü).
 *
 * Yenilikler:
 *  - Sezon seçilebilir (2025 hardcode kalktı)
 *  - Tekil ekleme: parsel artık aranabilir ParcelPicker ile (QuickAddPanel
 *    "parcel" alan tipi)
 *  - TOPLU EKİM: FilterPanel (Query Engine, module="parcels") ile parsel
 *    filtrele → checkbox çoklu seç → ortak form → POST /plantings/bulk-create
 *  - TOPLU SİLME: liste satırlarında checkbox → POST /plantings/bulk-delete
 *  - ?parcel=<id> query param'ı listeyi o parsele filtreler (ContractDetail
 *    ve Parseller popup'ındaki "Ekim detayına git" buradan gelir)
 */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import RowActions from "@/components/RowActions";
import BulkParcelSelect from "@/components/BulkParcelSelect";
import FilterPanel from "@/components/FilterPanel";
import EkimPlanlama from "@/pages/EkimPlanlama";
import { Sprout, Trash2, Layers, X, ClipboardList, Sparkles } from "lucide-react";

const STAGE_OPTS = [
  { value: "ekim", label: "Ekim" }, { value: "gelişim", label: "Gelişim" },
  { value: "olgunlaşma", label: "Olgunlaşma" }, { value: "hasat", label: "Hasat" },
];
const stageBadge = { ekim: "badge-b", gelişim: "badge-c", olgunlaşma: "badge-c", hasat: "badge-a" };

// ---- Toplu ekim bölümü ----------------------------------------------------
function BulkPlantingSection({ season, onCreated }) {
  const [open, setOpen] = useState(false);
  const [selIds, setSelIds] = useState([]);
  const [form, setForm] = useState({
    variety: "", planting_date: "", expected_harvest_date: "", stage: "ekim",
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const sel = new Set(selIds);

  async function submit() {
    if (sel.size === 0) { setMsg("Önce parsel seçin."); return; }
    if (!form.variety || !form.planting_date || !form.expected_harvest_date) {
      setMsg("Çeşit, ekim tarihi ve beklenen hasat zorunlu."); return;
    }
    setBusy(true); setMsg("");
    try {
      const { data } = await api.post("/plantings/bulk-create", {
        parcel_ids: selIds, season: Number(season), ...form,
      });
      setMsg(`${data.created_count} ekim kaydı oluşturuldu` +
        (data.skipped.length ? `, ${data.skipped.length} parsel atlandı.` : "."));
      onCreated();
    } catch (err) {
      setMsg(err.response?.data?.detail || "Toplu kayıt başarısız.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn btn-ghost mb-4 ml-2" data-testid="bulk-planting-open">
        <Layers size={15} /> Toplu Ekim Kaydı
      </button>
    );
  }

  return (
    <div className="card p-4 mb-4 w-full" data-testid="bulk-planting-panel">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-display text-lg flex items-center gap-2"><Layers size={17} /> Toplu Ekim Kaydı</h3>
        <button onClick={() => setOpen(false)} className="text-xs text-[var(--text-dim)] hover:text-white">Kapat</button>
      </div>
      <p className="text-xs text-[var(--text-dim)] mb-3">
        1) Gelişmiş filtreyle parselleri bulun → 2) checkbox ile seçin → 3) ortak alanları doldurup uygulayın.
        Her parsel için ayrı ekim kaydı açılır (çiftçi parselden türetilir).
      </p>

      <BulkParcelSelect onSelectionChange={setSelIds} testId="bulk-planting" />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-4 items-end">
        <div>
          <label className="text-xs text-[var(--text-dim)] block mb-1">Çeşit *</label>
          <input className="input" value={form.variety}
                 onChange={(e) => setForm({ ...form, variety: e.target.value })} data-testid="bulk-variety" />
        </div>
        <div>
          <label className="text-xs text-[var(--text-dim)] block mb-1">Ekim Tarihi *</label>
          <input className="input" type="date" value={form.planting_date}
                 onChange={(e) => setForm({ ...form, planting_date: e.target.value })} />
        </div>
        <div>
          <label className="text-xs text-[var(--text-dim)] block mb-1">Beklenen Hasat *</label>
          <input className="input" type="date" value={form.expected_harvest_date}
                 onChange={(e) => setForm({ ...form, expected_harvest_date: e.target.value })} />
        </div>
        <div>
          <label className="text-xs text-[var(--text-dim)] block mb-1">Aşama</label>
          <select className="input" value={form.stage}
                  onChange={(e) => setForm({ ...form, stage: e.target.value })}>
            {STAGE_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <button className="btn btn-primary" disabled={busy || sel.size === 0}
                onClick={submit} data-testid="bulk-planting-submit">
          {busy ? "Kaydediliyor…" : `${sel.size} Parsele Uygula`}
        </button>
      </div>
      {msg && <div className="text-xs mt-2 text-[var(--primary)]" data-testid="bulk-planting-msg">{msg}</div>}
    </div>
  );
}

// ---- Ana sayfa ------------------------------------------------------------
export default function EkimKaydi() {
  const [params, setParams] = useSearchParams();
  const parcelFilter = params.get("parcel") || "";
  // Denetim düzeltmesi (2026-07-24) — "Ekim Karar Motoru" ayrı bir üst
  // menü öğesi OLMAKTAN ÇIKARILDI, bu modülün (Ekim Planlama) altına
  // alındı: SahaOperasyonlari.jsx'in `?view=raporlar` deseniyle AYNI
  // (IT-41 emsali) — eski `/ekim-planlama` route'u App.js'te bu görünüme
  // yönlendirir, eski linkler kırılmaz.
  const view = params.get("view") === "karar-motoru" ? "karar-motoru" : "kayitlar";
  const setView = (v) => setParams((p) => {
    const next = new URLSearchParams(p);
    if (v === "kayitlar") next.delete("view"); else next.set("view", v);
    return next;
  });
  const [season, setSeason] = useState(2025);
  const [plantings, setPlantings] = useState([]);
  const [parcelsById, setParcelsById] = useState(new Map());
  const [sel, setSel] = useState(new Set());
  const [busyDelete, setBusyDelete] = useState(false);

  // 2026-08-20 (OTURUM-DEVAM madde 14) — çiftçinin mobilden gönderdiği ekim
  // beyanları burada onaylanır/reddedilir; onaylanana kadar HİÇBİR resmi
  // listede görünmezler (bkz. backend/data_entry.py review endpoint'i).
  const [pending, setPending] = useState([]);
  const [pendingBusy, setPendingBusy] = useState(null);
  const loadPending = () => api.get("/plantings/pending-review").then((r) => setPending(r.data)).catch(() => {});
  useEffect(() => { loadPending(); }, []);
  async function reviewPlanting(id, decision) {
    setPendingBusy(id);
    try {
      await api.put(`/plantings/${id}/review`, { decision });
      setPending((prev) => prev.filter((p) => p.id !== id));
      if (decision === "onayla") load();
    } finally {
      setPendingBusy(null);
    }
  }

  const load = () => {
    const p = { season: Number(season) };
    if (parcelFilter) p.parcel_id = parcelFilter;
    return api.get("/plantings", { params: p }).then((r) => { setPlantings(r.data); setSel(new Set()); });
  };
  useEffect(() => { load(); }, [season, parcelFilter]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.get("/parcels", { params: { limit: 2000 } })
      .then((r) => setParcelsById(new Map((Array.isArray(r.data) ? r.data : []).map((p) => [p.id, p]))))
      .catch(() => {});
  }, []);

  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const visible = useMemo(() => plantings.slice(0, 200), [plantings]);
  const toggleAll = () => setSel((s) => (s.size === visible.length ? new Set() : new Set(visible.map((p) => p.id))));

  async function bulkDelete() {
    if (sel.size === 0) return;
    if (!window.confirm(`${sel.size} ekim kaydı silinsin mi?\n(Kayıtlar arşivlenir — geri alınabilir.)`)) return;
    setBusyDelete(true);
    try {
      await api.post("/plantings/bulk-delete", { planting_ids: [...sel] });
      await load();
    } finally {
      setBusyDelete(false);
    }
  }

  const filterParcelName = parcelFilter ? (parcelsById.get(parcelFilter)?.name || "seçili parsel") : null;

  return (
    <div className="p-8" data-testid="ekim-page">
      <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">EKİM PLANLAMA</div>
      <div className="flex items-end justify-between flex-wrap gap-3 mb-4">
        <h1 className="font-display text-4xl flex items-center gap-3">
          <Sprout size={30} className="text-[var(--primary)]" /> Ekim Planlama
        </h1>
        {view === "kayitlar" && (
          <div className="flex items-center gap-2">
            <label className="text-xs text-[var(--text-dim)]">Sezon</label>
            <select className="input w-28" value={season} onChange={(e) => setSeason(Number(e.target.value))}
                    data-testid="ekim-season-select">
              {[2023, 2024, 2025, 2026, 2027].map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* Denetim düzeltmesi (2026-07-24) — Ekim Karar Motoru artık bu
          modülün (Ekim Planlama) bir SEKMESİ, ayrı bir üst menü öğesi değil. */}
      <div className="mb-6 flex flex-wrap gap-2">
        <button onClick={() => setView("kayitlar")}
                className={`btn ${view === "kayitlar" ? "btn-primary" : "btn-ghost"} text-sm`} data-testid="ekim-view-kayitlar">
          <ClipboardList size={14} /> Ekim Kayıtları
        </button>
        <button onClick={() => setView("karar-motoru")}
                className={`btn ${view === "karar-motoru" ? "btn-primary" : "btn-ghost"} text-sm`} data-testid="ekim-view-karar-motoru">
          <Sparkles size={14} /> Karar Motoru
        </button>
      </div>

      {view === "karar-motoru" && <EkimPlanlama />}

      {view === "kayitlar" && <>

      {parcelFilter && (
        <div className="card p-3 mb-4 flex items-center gap-2 text-sm" data-testid="ekim-parcel-filter-chip">
          <span className="text-[var(--text-dim)]">Parsel filtresi:</span>
          <b>{filterParcelName}</b>
          <button className="text-[var(--text-dim)] hover:text-white ml-1"
                  onClick={() => setParams({})} title="Filtreyi kaldır"><X size={14} /></button>
        </div>
      )}

      {pending.length > 0 && (
        <div className="card p-4 mb-4 border-l-4 border-[var(--warning,#F59E0B)]" data-testid="planting-pending-review">
          <h3 className="text-sm font-medium mb-3">Onay Bekleyen Çiftçi Ekim Beyanları ({pending.length})</h3>
          <div className="space-y-2">
            {pending.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 border-b border-[var(--border)] pb-2 text-sm">
                <div>
                  <div>{parcelsById.get(p.parcel_id)?.name || p.parcel_id} — {p.variety} ({p.season})</div>
                  <div className="text-xs text-[var(--text-dim)]">Ekim: {p.planting_date} · Beklenen hasat: {p.expected_harvest_date}</div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button onClick={() => reviewPlanting(p.id, "onayla")} disabled={pendingBusy === p.id}
                          className="btn btn-primary text-xs" data-testid={`planting-approve-${p.id}`}>Onayla</button>
                  <button onClick={() => reviewPlanting(p.id, "reddet")} disabled={pendingBusy === p.id}
                          className="btn btn-ghost text-xs text-red-400" data-testid={`planting-reject-${p.id}`}>Reddet</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-start flex-wrap">
        <QuickAddPanel
          title="Yeni Ekim Kaydı"
          testId="planting-add"
          extraModule="plantings"
          fields={[
            { name: "parcel_id", label: "Parsel (il/ilçe/mahalle/ada/ad ile ara)", type: "parcel", required: true, span2: true },
            { name: "season", label: "Sezon", type: "number", required: true, default: 2025 },
            { name: "variety", label: "Çeşit", required: true },
            { name: "planting_date", label: "Ekim Tarihi", type: "date", required: true },
            { name: "expected_harvest_date", label: "Beklenen Hasat", type: "date", required: true },
            { name: "stage", label: "Aşama", type: "select", default: "ekim", options: STAGE_OPTS },
          ]}
          onSubmit={async (v) => { await api.post("/plantings", { ...v, season: Number(v.season) }); load(); }}
        />
        <BulkPlantingSection season={season} onCreated={load} />
      </div>

      {sel.size > 0 && (
        <div className="card p-3 mb-3 flex items-center gap-3" data-testid="planting-bulk-bar">
          <span className="text-sm">{sel.size} kayıt seçili</span>
          <button className="btn btn-ghost text-xs text-red-400" onClick={bulkDelete}
                  disabled={busyDelete} data-testid="planting-bulk-delete">
            <Trash2 size={13} /> {busyDelete ? "Siliniyor…" : "Seçilenleri Sil"}
          </button>
        </div>
      )}

      {/* SON HAL #3 — gelişmiş arama (Query Engine, module="plantings").
          Not: sonuçlar `plantings` state'inin üzerine yazar; sezon/parsel
          filtre çubuğu ayrı bir mekanizma olarak durur (load() ile döner). */}
      <FilterPanel module="plantings" onResults={(items) => setPlantings(items)} />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4 w-8">
              <input type="checkbox" checked={sel.size === visible.length && visible.length > 0}
                     onChange={toggleAll} data-testid="planting-select-all" />
            </th>
            <th className="p-4">Parsel</th><th className="p-4">Çeşit</th><th className="p-4">Ekim Tarihi</th>
            <th className="p-4">Beklenen Hasat</th><th className="p-4">Aşama</th><th className="p-4 text-right">İşlem</th>
          </tr></thead>
          <tbody>
            {visible.map((p) => (
              <tr key={p.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4">
                  <input type="checkbox" checked={sel.has(p.id)} onChange={() => toggle(p.id)}
                         data-testid="planting-row-check" />
                </td>
                <td className="p-4">{parcelsById.get(p.parcel_id)?.name || "—"}</td>
                <td className="p-4">{p.variety}</td>
                <td className="p-4 text-[var(--text-dim)]">{p.planting_date}</td>
                <td className="p-4 text-[var(--text-dim)]">{p.expected_harvest_date}</td>
                <td className="p-4"><span className={`badge ${stageBadge[p.stage] || "badge-neutral"}`}>{p.stage}</span></td>
                <td className="p-4">
                  <div className="flex justify-end">
                    <RowActions
                      entityLabel="ekim kaydı"
                      values={p}
                      fields={[
                        { name: "stage", label: "Aşama", type: "select", options: STAGE_OPTS },
                        { name: "expected_harvest_date", label: "Beklenen Hasat", type: "date" },
                        { name: "actual_harvest_date", label: "Gerçek Hasat", type: "date" },
                      ]}
                      onSave={async (v) => {
                        await api.put(`/plantings/${p.id}`, {
                          stage: v.stage || null,
                          expected_harvest_date: v.expected_harvest_date || null,
                          actual_harvest_date: v.actual_harvest_date || null,
                        });
                        load();
                      }}
                      onDelete={async () => { await api.delete(`/plantings/${p.id}`); load(); }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && (
          <p className="p-6 text-sm text-[var(--text-dim)]">Bu sezonda ekim kaydı yok.</p>
        )}
      </div>
      </>}
    </div>
  );
}
