/**
 * ONAY BEKLEYENLERİM + ONAY ZİNCİRİ KURALLARI (IT-07b / FAZ 3 devam)
 *
 * Modül-bağımsız tek liste: approval.py'nin farklı process'lerden (Destek
 * Talebi, Kampanya, Case Atama, ...) ürettiği bekleyen onayların HEPSİ
 * burada, süreç etiketiyle görünür (ROADMAP kabul kriteri: "en az 2 farklı
 * modülden gelen onay kayıtlarını tek listede, modül etiketiyle gösteriyor").
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { CheckCircle2, XCircle, Settings2, Plus } from "lucide-react";

const TARGET_TYPES = [
  { v: "role", l: "Role Göre" },
  { v: "hierarchy", l: "Talep Sahibinin Yöneticisi" },
  { v: "user", l: "Belirli Kullanıcı" },
];

function emptyRule() {
  return { process: "", name: "", steps: [{ order: 1, target_type: "role", target_value: "" }] };
}

export default function PendingApprovals() {
  const [pending, setPending] = useState([]);
  const [rules, setRules] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [roles, setRoles] = useState([]);
  const [users, setUsers] = useState([]);
  const [ruleForm, setRuleForm] = useState(emptyRule());
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [note, setNote] = useState({});
  const [error, setError] = useState("");
  const [canManageRules, setCanManageRules] = useState(true);

  function loadPending() { api.get("/approvals/pending").then((r) => setPending(r.data)); }
  function loadRules() {
    api.get("/approval-chains").then((r) => setRules(r.data)).catch(() => setCanManageRules(false));
    api.get("/approval-chains/processes").then((r) => setProcesses(r.data)).catch(() => {});
  }

  useEffect(() => {
    loadPending();
    loadRules();
    api.get("/users/roles").then((r) => setRoles(r.data.built_in || [])).catch(() => {});
    api.get("/users").then((r) => setUsers(r.data)).catch(() => {});
  }, []);

  async function decide(instanceId, decision) {
    setError("");
    try {
      await api.post(`/approvals/${instanceId}/decide`, { decision, note: note[instanceId] || "" });
      loadPending();
    } catch (err) { setError(err.response?.data?.detail || "Karar kaydedilemedi"); }
  }

  function updateStep(idx, patch) {
    setRuleForm((f) => {
      const steps = f.steps.map((s, i) => (i === idx ? { ...s, ...patch } : s));
      return { ...f, steps };
    });
  }
  function addStep() {
    setRuleForm((f) => ({ ...f, steps: [...f.steps, { order: f.steps.length + 1, target_type: "role", target_value: "" }] }));
  }

  async function submitRule(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/approval-chains", ruleForm);
      setRuleForm(emptyRule());
      setShowRuleForm(false);
      loadRules();
    } catch (err) { setError(err.response?.data?.detail || "Onay kuralı oluşturulamadı"); }
  }

  const processLabel = (key) => processes.find((p) => p.key === key)?.label || key;

  return (
    <div className="p-8 max-w-[1400px]" data-testid="pending-approvals-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">ORGANİZASYON</div>
        <h1 className="font-display text-4xl">Onay Bekleyenlerim</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Hangi modülden gelirse gelsin (Destek Talebi, Kampanya, Case atama...) sizden onay bekleyen tüm kayıtlar.
        </p>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      <div className="card overflow-hidden mb-8">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Süreç</th><th className="p-4">Adım</th><th className="p-4">Talep Eden</th><th className="p-4">Not</th><th className="p-4"></th>
          </tr></thead>
          <tbody>
            {pending.map((p) => (
              <tr key={p.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4"><span className="badge badge-neutral">{p.process_label || processLabel(p.process)}</span></td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{p.current_step_index + 1} / {p.steps.length}</td>
                <td className="p-4 text-xs font-mono">{p.requester_user_id}</td>
                <td className="p-4">
                  <input className="input text-xs w-full" placeholder="Karar notu (opsiyonel)"
                         value={note[p.id] || ""} onChange={(e) => setNote((n) => ({ ...n, [p.id]: e.target.value }))} />
                </td>
                <td className="p-4 flex gap-2">
                  <button onClick={() => decide(p.id, "onayla")} className="btn btn-primary text-xs" data-testid={`approve-${p.id}`}>
                    <CheckCircle2 size={12} /> Onayla
                  </button>
                  <button onClick={() => decide(p.id, "reddet")} className="btn btn-ghost text-xs text-red-400" data-testid={`reject-${p.id}`}>
                    <XCircle size={12} /> Reddet
                  </button>
                </td>
              </tr>
            ))}
            {pending.length === 0 && (
              <tr><td colSpan="5" className="p-6 text-center text-[var(--text-dim)]">Onay bekleyen kayıt yok</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {canManageRules && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-lg flex items-center gap-2"><Settings2 size={16} className="text-[var(--primary)]" />Onay Zinciri Kuralları</h3>
            <button onClick={() => setShowRuleForm((s) => !s)} className="btn btn-ghost text-xs"><Plus size={12} /> Yeni Kural</button>
          </div>

          {showRuleForm && (
            <form onSubmit={submitRule} className="space-y-3 mb-4 p-3 rounded bg-[var(--surface-2)]">
              <div className="grid grid-cols-2 gap-3">
                <select className="input text-sm" required value={ruleForm.process}
                        onChange={(e) => setRuleForm((f) => ({ ...f, process: e.target.value }))}>
                  <option value="">Süreç seç...</option>
                  {processes.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
                </select>
                <input className="input text-sm" placeholder="Kural adı" required
                       value={ruleForm.name} onChange={(e) => setRuleForm((f) => ({ ...f, name: e.target.value }))} />
              </div>
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Adımlar (sırayla)</div>
              {ruleForm.steps.map((s, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <span className="text-xs w-6">{idx + 1}.</span>
                  <select className="input text-xs w-44" value={s.target_type}
                          onChange={(e) => updateStep(idx, { target_type: e.target.value, target_value: "" })}>
                    {TARGET_TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
                  </select>
                  {s.target_type === "role" && (
                    <select className="input text-xs flex-1" value={s.target_value} onChange={(e) => updateStep(idx, { target_value: e.target.value })}>
                      <option value="">Rol seç...</option>
                      {roles.map((r) => <option key={r.key || r} value={r.key || r}>{r.label || r}</option>)}
                    </select>
                  )}
                  {s.target_type === "user" && (
                    <select className="input text-xs flex-1" value={s.target_value} onChange={(e) => updateStep(idx, { target_value: e.target.value })}>
                      <option value="">Kullanıcı seç...</option>
                      {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.email}</option>)}
                    </select>
                  )}
                  {s.target_type === "hierarchy" && (
                    <input className="input text-xs flex-1" disabled value="requester_manager (talep sahibinin doğrudan yöneticisi)"
                           onChange={() => updateStep(idx, { target_value: "requester_manager" })} />
                  )}
                </div>
              ))}
              <div className="flex gap-2">
                <button type="button" onClick={addStep} className="btn btn-ghost text-xs"><Plus size={12} /> Adım Ekle</button>
                <button type="submit" className="btn btn-primary text-xs">Kuralı Kaydet</button>
              </div>
            </form>
          )}

          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-3">Süreç</th><th className="p-3">Kural</th><th className="p-3">Adım Sayısı</th><th className="p-3">Durum</th>
            </tr></thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id} className="border-b border-[var(--border)]">
                  <td className="p-3">{processLabel(r.process)}</td>
                  <td className="p-3">{r.name}</td>
                  <td className="p-3 text-xs text-[var(--text-dim)]">{r.steps.length}</td>
                  <td className="p-3"><span className={`badge ${r.is_active === false ? "badge-d" : "badge-a"}`}>{r.is_active === false ? "Pasif" : "Aktif"}</span></td>
                </tr>
              ))}
              {rules.length === 0 && (
                <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Henüz onay kuralı tanımlı değil — tanımlanmadıkça ilgili süreçler doğrudan (onaysız) işler.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
