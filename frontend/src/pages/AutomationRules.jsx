/**
 * OTOMASYON KURALLARI (IT-24 / FAZ 8 TAMAMLANDI)
 *
 * backend/automation.py'nin admin ekranı — kod yazmadan "event_type + koşul
 * -> TaskType + personel" kuralı tanımlanır. Koşul builder'ı (field/value
 * satırları, ekle/sil) QuickAddPanel'in düz alan listesine SIĞMADIĞI için
 * (FilterPanel.jsx'in AND koşul satırlarıyla AYNI aile) bilinçli olarak
 * kendi basit formu yazıldı — yeni bir genel bileşen İCAT EDİLMEDİ, sadece
 * bu ekrana özel küçük bir satır listesi.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { Zap, Plus, Trash2, History } from "lucide-react";

const PRIORITY_LABELS = { dusuk: "Düşük", normal: "Normal", yuksek: "Yüksek" };

const emptyForm = { name: "", event_type: "", conditions: [], task_type_id: "", assigned_to: "", priority: "normal" };

export default function AutomationRules() {
  const [rules, setRules] = useState([]);
  const [eventTypes, setEventTypes] = useState([]);
  const [taskTypes, setTaskTypes] = useState([]);
  const [staff, setStaff] = useState([]);
  const [runs, setRuns] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");

  const load = () => api.get("/automation/rules").then((r) => setRules(r.data));

  useEffect(() => {
    load();
    api.get("/automation/event-types").then((r) => setEventTypes(r.data));
    api.get("/task-types").then((r) => setTaskTypes(r.data));
    api.get("/field-ops/assignable-users").then((r) => setStaff(r.data));
    api.get("/automation/rule-runs").then((r) => setRuns(r.data));
  }, []);

  const taskTypesById = new Map(taskTypes.map((t) => [t.id, t]));
  const staffById = new Map(staff.map((s) => [s.id, s]));
  const eventLabels = Object.fromEntries(eventTypes.map((e) => [e.key, e.label]));

  function addCondition() {
    setForm((f) => ({ ...f, conditions: [...f.conditions, { field: "", value: "" }] }));
  }
  function updateCondition(idx, key, value) {
    setForm((f) => ({ ...f, conditions: f.conditions.map((c, i) => (i === idx ? { ...c, [key]: value } : c)) }));
  }
  function removeCondition(idx) {
    setForm((f) => ({ ...f, conditions: f.conditions.filter((_, i) => i !== idx) }));
  }

  async function submitRule(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/automation/rules", {
        ...form,
        conditions: form.conditions.filter((c) => c.field && c.value),
      });
      setForm(emptyForm);
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Kural oluşturulamadı");
    }
  }

  async function toggleActive(rule) {
    if (rule.is_active) {
      await api.delete(`/automation/rules/${rule.id}`);
    } else {
      await api.put(`/automation/rules/${rule.id}`, { is_active: true });
    }
    load();
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="automation-rules-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SAHA OPERASYONLARI — OTOMASYON</div>
        <h1 className="font-display text-4xl">Otomasyon Kuralları</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Bir olay (ör. "Toprak Analizi Tamamlandı") gerçekleştiğinde, koşullar sağlanırsa otomatik
          bir saha görevi açılır — kod yazmadan, sadece burada tanımlanarak.
        </p>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      <form onSubmit={submitRule} className="card p-5 mb-6 space-y-3" data-testid="automation-rule-form">
        <h3 className="font-display text-lg flex items-center gap-2"><Zap size={16} className="text-[var(--primary)]"/>Yeni Kural</h3>
        <div className="grid grid-cols-2 gap-3">
          <input className="input" placeholder="Kural adı" required
                 value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}/>
          <select className="input" required value={form.event_type}
                  onChange={(e) => setForm((f) => ({ ...f, event_type: e.target.value }))}>
            <option value="">Olay seç...</option>
            {eventTypes.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}
          </select>
          <select className="input" required value={form.task_type_id}
                  onChange={(e) => setForm((f) => ({ ...f, task_type_id: e.target.value }))}>
            <option value="">Oluşturulacak görev tipi...</option>
            {taskTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <select className="input" required value={form.assigned_to}
                  onChange={(e) => setForm((f) => ({ ...f, assigned_to: e.target.value }))}>
            <option value="">Atanacak personel...</option>
            {staff.map((s) => <option key={s.id} value={s.id}>{s.full_name} ({s.role})</option>)}
          </select>
          <select className="input" value={form.priority}
                  onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}>
            {Object.entries(PRIORITY_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>

        <div>
          <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">
            Koşullar (opsiyonel — boşsa olayın HER örneğinde tetiklenir)
          </div>
          <div className="space-y-2">
            {form.conditions.map((c, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <input className="input flex-1" placeholder="alan (ör. support_type_id)"
                       value={c.field} onChange={(e) => updateCondition(idx, "field", e.target.value)}/>
                <span className="text-[var(--text-dim)] text-xs">=</span>
                <input className="input flex-1" placeholder="değer"
                       value={c.value} onChange={(e) => updateCondition(idx, "value", e.target.value)}/>
                <button type="button" onClick={() => removeCondition(idx)} className="btn btn-ghost text-red-400 px-2">
                  <Trash2 size={14}/>
                </button>
              </div>
            ))}
          </div>
          <button type="button" onClick={addCondition} className="btn btn-ghost text-xs mt-2">
            <Plus size={12}/> Koşul Ekle
          </button>
        </div>

        <button type="submit" className="btn btn-primary" data-testid="automation-rule-submit">Kuralı Oluştur</button>
      </form>

      <div className="card overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Ad</th><th className="p-4">Olay</th><th className="p-4">Koşullar</th>
            <th className="p-4">Görev Tipi</th><th className="p-4">Personel</th><th className="p-4">Öncelik</th><th className="p-4">Durum</th>
          </tr></thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4">{r.name}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{eventLabels[r.event_type] || r.event_type}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">
                  {(r.conditions || []).length === 0 ? "—" : r.conditions.map((c) => `${c.field}=${c.value}`).join(", ")}
                </td>
                <td className="p-4">{taskTypesById.get(r.task_type_id)?.name || r.task_type_id}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{staffById.get(r.assigned_to)?.full_name || r.assigned_to}</td>
                <td className="p-4"><span className="badge badge-neutral">{PRIORITY_LABELS[r.priority] || r.priority}</span></td>
                <td className="p-4">
                  <button onClick={() => toggleActive(r)} className={`badge ${r.is_active === false ? "badge-d" : "badge-a"}`}>
                    {r.is_active === false ? "Pasif" : "Aktif"}
                  </button>
                </td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr><td colSpan="7" className="p-6 text-center text-[var(--text-dim)]">Henüz otomasyon kuralı yok</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card p-5">
        <h3 className="font-display text-lg mb-3 flex items-center gap-2"><History size={16} className="text-[var(--primary)]"/>Son Otomatik Görev Üretimleri</h3>
        <div className="space-y-2">
          {runs.map((run) => (
            <div key={run.id} className="flex items-center justify-between text-sm border-b border-[var(--border)] pb-2">
              <div>
                <span className="font-medium">{run.rule_name}</span>
                <span className="text-[var(--text-dim)] text-xs ml-2">{eventLabels[run.event_type] || run.event_type}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`badge ${run.status === "created" ? "badge-a" : "badge-d"} text-[10px]`}>
                  {run.status === "created" ? "Görev Oluşturuldu" : "Atlandı"}
                </span>
                <span className="text-[var(--text-dim)] text-xs">{(run.ran_at || "").replace("T", " ").slice(0, 16)}</span>
              </div>
            </div>
          ))}
          {runs.length === 0 && <div className="text-sm text-[var(--text-dim)] py-4 text-center">Henüz otomatik çalışma yok</div>}
        </div>
      </div>
    </div>
  );
}
