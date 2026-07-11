import api from "@/api";
import { Tractor, Users2, ListChecks, Wrench } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { QuickAddPanel } from "@/components/QuickAdd";
import { useFetch } from "@/hooks/use-fetch";

// Refactoring notu (2026-07-11): 6 bagimsiz useState+useEffect+api.get
// kalibi useFetch hook'una tasindi (bkz. hooks/use-fetch.js) -- DAVRANIS
// AYNI: mount'ta bir kere fetch, loadAll() mutasyon sonrasi 4 listeyi
// yeniden ceker (oncekiyle birebir), parcels/regions bir kere yuklenir.
export default function Operasyon() {
  const summaryQ = useFetch("/operations/summary");
  const tasksQ = useFetch("/operations/tasks", { initialData: [] });
  const machinesQ = useFetch("/operations/machines", { initialData: [] });
  const workersQ = useFetch("/operations/workers", { initialData: [] });
  const parcelsQ = useFetch("/parcels", { params: { limit: 500 }, initialData: [] });
  const regionsQ = useFetch("/regions", { initialData: [] });

  const summary = summaryQ.data;
  const tasks = tasksQ.data;
  const machines = machinesQ.data;
  const workers = workersQ.data;
  const parcels = parcelsQ.data;
  const regions = regionsQ.data;

  const loadAll = () => {
    summaryQ.reload();
    tasksQ.reload();
    machinesQ.reload();
    workersQ.reload();
  };

  if (!summary) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const byType = Object.entries(summary.by_type).map(([name, value]) => ({ name, value }));
  const statusBadge = {
    "planlı": "badge-c",
    "devam ediyor": "badge-b",
    "tamamlandı": "badge-a",
    "iptal": "badge-d"
  };
  const machineStatusBadge = {
    "aktif": "badge-a",
    "bakım": "badge-c",
    "boşta": "badge-neutral"
  };

  return (
    <div className="p-8 max-w-[1600px]" data-testid="operasyon-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">M16 · MODÜL</div>
        <h1 className="font-display text-4xl">Operasyon Yönetimi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">Görev planlama, makine takibi, işçi vardiya</p>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="card p-5">
          <ListChecks className="text-[var(--primary)] mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Toplam Görev</div>
          <div className="font-display text-3xl">{summary.tasks_total}</div>
        </div>
        <div className="card p-5">
          <Tractor className="text-blue-400 mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Aktif Makine</div>
          <div className="font-display text-3xl">{summary.machines_active}</div>
          <div className="text-xs text-[var(--text-dim)]">/ {summary.machines_total} toplam</div>
        </div>
        <div className="card p-5">
          <Wrench className="text-amber-400 mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Bakımda</div>
          <div className="font-display text-3xl">{summary.machines_maintenance}</div>
        </div>
        <div className="card p-5">
          <Users2 className="text-emerald-400 mb-2"/>
          <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">Tamamlanan</div>
          <div className="font-display text-3xl">{summary.by_status["tamamlandı"] || 0}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        <div className="card p-5 lg:col-span-2">
          <h3 className="font-display text-lg mb-4">Görev Tipine Göre Dağılım</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={byType}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
              <XAxis dataKey="name" stroke="#97a8a0" />
              <YAxis stroke="#97a8a0" />
              <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
              <Bar dataKey="value" fill="#4ade80" radius={[6, 6, 0, 0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card p-5">
          <h3 className="font-display text-lg mb-4">Görev Durumu</h3>
          <div className="space-y-3">
            {Object.entries(summary.by_status).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <span className={`badge ${statusBadge[k] || "badge-neutral"}`}>{k}</span>
                <div className="font-display text-xl">{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* GÖREV EKLE */}
      <QuickAddPanel
        title="Yeni Görev"
        testId="task-add"
        fields={[
          { name: "task_type", label: "Görev Tipi", type: "select", required: true,
            options: ["toprak işleme", "ekim", "gübreleme", "ilaçlama", "sulama", "hasat", "nakliye"].map((t) => ({ value: t, label: t })) },
          { name: "parcel_id", label: "Parsel", type: "select", required: true,
            options: parcels.map((p) => ({ value: p.id, label: `${p.parcel_code} — ${p.name}` })) },
          { name: "scheduled_date", label: "Planlanan Tarih", type: "date", required: true },
          { name: "machine_id", label: "Makine (opsiyonel)", type: "select",
            options: machines.map((m) => ({ value: m.id, label: `${m.type} — ${m.model}` })) },
          { name: "worker_id", label: "İşçi (opsiyonel)", type: "select",
            options: workers.map((w) => ({ value: w.id, label: w.full_name })) },
          { name: "notes", label: "Notlar", type: "textarea", span2: true },
        ]}
        onSubmit={async (v) => {
          await api.post("/operations/tasks", {
            ...v,
            scheduled_date: new Date(v.scheduled_date).toISOString(),
            machine_id: v.machine_id || null,
            worker_id: v.worker_id || null,
          });
          loadAll();
        }}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)]">
            <h3 className="font-display text-lg">Son Görevler</h3>
          </div>
          <div className="max-h-[420px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider sticky top-0 bg-[var(--surface)]">
                  <th className="p-3">Tip</th>
                  <th className="p-3">Tarih</th>
                  <th className="p-3">Durum</th>
                </tr>
              </thead>
              <tbody>
                {tasks.slice(0, 30).map((t) => (
                  <tr key={t.id} className="border-b border-[var(--border)]">
                    <td className="p-3 capitalize">{t.task_type}</td>
                    <td className="p-3 text-[var(--text-dim)]">{new Date(t.scheduled_date).toLocaleDateString("tr-TR")}</td>
                    <td className="p-3"><span className={`badge ${statusBadge[t.status]}`}>{t.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)]">
            <h3 className="font-display text-lg">Makine Filosu</h3>
          </div>
          <div className="max-h-[420px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider sticky top-0 bg-[var(--surface)]">
                  <th className="p-3">Tip</th>
                  <th className="p-3">Model</th>
                  <th className="p-3">Saat</th>
                  <th className="p-3">Durum</th>
                </tr>
              </thead>
              <tbody>
                {machines.slice(0, 30).map((m) => (
                  <tr key={m.id} className="border-b border-[var(--border)]">
                    <td className="p-3">{m.type}</td>
                    <td className="p-3 text-[var(--text-dim)] text-xs">{m.model}</td>
                    <td className="p-3 font-mono text-xs">{m.total_hours}h</td>
                    <td className="p-3"><span className={`badge ${machineStatusBadge[m.status]}`}>{m.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* MAKİNE EKLE */}
      <QuickAddPanel
        title="Yeni Makine"
        testId="machine-add"
        fields={[
          { name: "type", label: "Tip", required: true },
          { name: "model", label: "Model", required: true },
          { name: "serial_no", label: "Seri No", required: true },
          { name: "region_id", label: "Bölge", type: "select", required: true,
            options: regions.map((r) => ({ value: r.id, label: r.name })) },
          { name: "owner", label: "Sahiplik", type: "select", default: "kooperatif",
            options: [{ value: "kooperatif", label: "Kooperatif" }, { value: "çiftçi", label: "Çiftçi" }] },
          { name: "status", label: "Durum", type: "select", default: "aktif",
            options: [{ value: "aktif", label: "Aktif" }, { value: "bakım", label: "Bakım" }, { value: "boşta", label: "Boşta" }] },
        ]}
        onSubmit={async (v) => { await api.post("/operations/machines", { ...v, total_hours: 0 }); loadAll(); }}
      />

      {/* İŞÇİ EKLE + LİSTE */}
      <QuickAddPanel
        title="Yeni İşçi"
        testId="worker-add"
        fields={[
          { name: "full_name", label: "Ad Soyad", required: true },
          { name: "phone", label: "Telefon", required: true },
          { name: "region_id", label: "Bölge", type: "select", required: true,
            options: regions.map((r) => ({ value: r.id, label: r.name })) },
          { name: "skill", label: "Uzmanlık", type: "select", required: true,
            options: ["traktör sürücüsü", "saha işçisi", "biçerdöver operatörü", "ekipman uzmanı"].map((s) => ({ value: s, label: s })) },
          { name: "daily_wage", label: "Günlük Ücret (₺)", type: "number", required: true },
        ]}
        onSubmit={async (v) => { await api.post("/operations/workers", { ...v, daily_wage: Number(v.daily_wage) }); loadAll(); }}
      />

      <div className="card overflow-hidden">
        <div className="p-4 border-b border-[var(--border)]">
          <h3 className="font-display text-lg">İşçiler ({workers.length})</h3>
        </div>
        <div className="max-h-[300px] overflow-y-auto scrollbar">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider sticky top-0 bg-[var(--surface)]">
                <th className="p-3">Ad Soyad</th><th className="p-3">Telefon</th><th className="p-3">Uzmanlık</th><th className="p-3">Günlük Ücret</th><th className="p-3">Durum</th>
              </tr>
            </thead>
            <tbody>
              {workers.slice(0, 40).map((w) => (
                <tr key={w.id} className="border-b border-[var(--border)]">
                  <td className="p-3">{w.full_name}</td>
                  <td className="p-3 font-mono text-xs">{w.phone}</td>
                  <td className="p-3 capitalize">{w.skill}</td>
                  <td className="p-3">₺{w.daily_wage}</td>
                  <td className="p-3"><span className="badge badge-a">{w.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
