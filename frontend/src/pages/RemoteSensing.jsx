/**
 * UZAKTAN ALGILAMA (Remote Sensing / EOSDA) — FAZ 9.5 / IT-28.1
 *
 * backend/remote_sensing paketinin yönetim yüzeyi: sağlayıcı durumu,
 * Monitoring özeti (EOSDA trial kotası dahil), Tarama Politikaları (admin
 * kural tanımlar — Communication Policy deseni), Task kuyruğu, "Politikasız
 * Parseller" uyarısı. EOSDA API key'i Ayarlar > Entegrasyonlar'dan girilir
 * (Karar 3) — bu ekran ayrı bir key alanı İCAT ETMEZ.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { Satellite, Activity, ListChecks, AlertTriangle, RefreshCw, Plus } from "lucide-react";

const fmt = (n) => new Intl.NumberFormat("tr-TR").format(n ?? 0);

const FREQ_OPTIONS = [
  { value: "gunluk", label: "Günlük" },
  { value: "iki_gunde_bir", label: "İki günde bir" },
  { value: "haftada_bir", label: "Haftada bir" },
  { value: "ayda_bir", label: "Ayda bir" },
  { value: "manuel_only", label: "Sadece manuel" },
];

function KPI({ icon: Icon, label, value, suffix, accent }) {
  return (
    <div className="card p-5">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${accent || "bg-[var(--primary)]/10 text-[var(--primary)]"}`}>
        <Icon size={20} />
      </div>
      <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">{label}</div>
      <div className="font-display text-3xl mt-1">{value}{suffix && <span className="text-base text-[var(--text-dim)] ml-1">{suffix}</span>}</div>
    </div>
  );
}

export default function RemoteSensing() {
  const [status, setStatus] = useState(null);
  const [mon, setMon] = useState(null);
  const [policies, setPolicies] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [uncovered, setUncovered] = useState([]);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", frequency: "haftada_bir", priority: 0, indices: "ndvi" });

  const load = () => {
    api.get("/remote-sensing/providers/status").then((r) => setStatus(r.data)).catch(() => {});
    api.get("/remote-sensing/monitoring").then((r) => setMon(r.data)).catch(() => {});
    api.get("/remote-sensing/policies").then((r) => setPolicies(r.data)).catch(() => {});
    api.get("/remote-sensing/tasks", { params: { limit: 30 } }).then((r) => setTasks(r.data)).catch(() => {});
    api.get("/remote-sensing/uncovered-parcels").then((r) => setUncovered(r.data)).catch(() => {});
  };
  useEffect(load, []);

  const createPolicy = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/remote-sensing/policies", {
        name: form.name,
        frequency: form.frequency,
        priority: Number(form.priority) || 0,
        indices: form.indices.split(",").map((s) => s.trim()).filter(Boolean),
        filter: {},
        is_active: true,
      });
      setForm({ name: "", frequency: "haftada_bir", priority: 0, indices: "ndvi" });
      load();
    } catch (err) {
      alert("Hata: " + (err.response?.data?.detail || err.message));
    } finally { setBusy(false); }
  };

  const runScheduler = async () => {
    setBusy(true);
    try { await api.post("/remote-sensing/scheduler/run"); load(); }
    catch (err) { alert("Hata: " + (err.response?.data?.detail || err.message)); }
    finally { setBusy(false); }
  };

  return (
    <div className="p-8 max-w-[1600px]" data-testid="remote-sensing-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FAZ 9.5 · IT-28.1</div>
          <h1 className="font-display text-4xl">Uzaktan Algılama</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">EOSDA entegrasyonu · Tarama Politikaları · İzleme</p>
        </div>
        <button onClick={runScheduler} disabled={busy} className="btn btn-primary" data-testid="run-scheduler">
          <RefreshCw size={16}/> Tarama Turu Çalıştır
        </button>
      </header>

      {/* Sağlayıcı durumu */}
      {status && (
        <div className="card p-4 mb-4 flex items-center gap-3">
          <Satellite size={18} className="text-[var(--primary)]"/>
          <div className="text-sm">
            Aktif sağlayıcı: <span className="font-medium">{status.active_provider}</span>
            <span className={`badge ml-2 ${status.is_real ? "badge-a" : "badge-neutral"}`}>
              {status.is_real ? "GERÇEK" : "MOCK"}
            </span>
            {!status.enabled && <span className="text-[var(--text-dim)] ml-2">· Entegrasyon pasif (Ayarlar › Entegrasyonlar › EOSDA)</span>}
          </div>
        </div>
      )}

      {/* Monitoring KPI */}
      {mon && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <KPI icon={Activity} label="Toplam API Çağrısı" value={fmt(mon.total_api_calls)} />
          <KPI icon={ListChecks} label="Başarılı / Hatalı" value={`${fmt(mon.success)} / ${fmt(mon.failed)}`} accent="bg-emerald-500/10 text-emerald-400" />
          <KPI icon={RefreshCw} label="Bekleyen" value={fmt(mon.pending)} accent="bg-amber-500/10 text-amber-400" />
          <KPI icon={AlertTriangle} label="Trial Kalan" value={fmt(mon.trial_remaining)} suffix={`/${fmt(mon.trial_request_limit)}`} accent="bg-red-500/10 text-red-400" />
        </div>
      )}

      {/* Politikasız Parseller uyarısı */}
      {uncovered.length > 0 && (
        <div className="card p-4 mb-6 bg-amber-500/10 border border-amber-500/30">
          <div className="flex items-center gap-2 text-amber-400 font-medium text-sm">
            <AlertTriangle size={16}/> {uncovered.length} parsel hiçbir tarama politikasına dahil değil
          </div>
          <div className="text-xs text-[var(--text-dim)] mt-1">
            Her parsel en az bir politikaya düşmeli — bir "hepsi (filtre boş)" varsayılan politikası tanımlayın.
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* Tarama Politikaları */}
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">Tarama Politikaları</h3>
          <form onSubmit={createPolicy} className="grid grid-cols-2 gap-2 mb-4" data-testid="policy-form">
            <input className="input col-span-2" placeholder="Politika adı" required
              value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <select className="input" value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })}>
              {FREQ_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <input className="input" type="number" placeholder="Öncelik" value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })} />
            <input className="input col-span-2" placeholder="İndeksler (ör. ndvi, ndre)"
              value={form.indices} onChange={(e) => setForm({ ...form, indices: e.target.value })} />
            <button type="submit" disabled={busy} className="btn btn-primary col-span-2 justify-center">
              <Plus size={14}/> Politika Ekle
            </button>
          </form>
          <div className="space-y-2 max-h-[300px] overflow-y-auto scrollbar">
            {policies.map((p) => (
              <div key={p.id} className="flex items-center justify-between p-2.5 bg-[var(--surface-2)] rounded-lg text-sm">
                <div>
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-[var(--text-dim)]">{p.frequency} · {(p.indices || []).join(", ")} · öncelik {p.priority}</div>
                </div>
                <span className={`badge ${p.is_active ? "badge-a" : "badge-neutral"}`}>{p.is_active ? "aktif" : "pasif"}</span>
              </div>
            ))}
            {policies.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Henüz politika yok</div>}
          </div>
        </div>

        {/* Task kuyruğu */}
        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">Task Kuyruğu (son 30)</h3>
          <div className="space-y-2 max-h-[380px] overflow-y-auto scrollbar">
            {tasks.map((t) => (
              <div key={t.id} className="flex items-center justify-between p-2.5 bg-[var(--surface-2)] rounded-lg text-sm">
                <div>
                  <div className="font-mono text-xs">{t.task_type} · {t.trigger}</div>
                  <div className="text-xs text-[var(--text-dim)]">{(t.parcel_id || "").slice(0, 8)} · {t.api_calls || 0} çağrı</div>
                </div>
                <span className={`badge ${t.state === "completed" ? "badge-a" : t.state === "failed" ? "badge-d" : "badge-c"}`}>{t.state}</span>
              </div>
            ))}
            {tasks.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Henüz task yok</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
