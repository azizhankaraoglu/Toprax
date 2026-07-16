/**
 * INTEGRATION HUB (IT-32 / FAZ 11 — Platform Core)
 *
 * backend/integration_hub.py'nin admin ekranı — AutomationRules.jsx'in
 * "kural + son çalışmalar" kalıbıyla AYNI aile: burada kural bir
 * WebhookRule (event → URL + header), "son çalışmalar" yerine bir
 * kuralın "Test Et" butonuyla tetiklenen tekil bir teslimat sonucu var.
 * Üstte ayrıca INTEGRATION_REGISTRY'nin salt-okunur envanteri gösterilir
 * (hangi kategori hangi modülden geçiyor — kabul kriterinin "en az 3
 * entegrasyon Hub üzerinden geçiyor" maddesinin görünür kanıtı).
 */
import { Fragment, useEffect, useState } from "react";
import api from "@/api";
import { Cable, Webhook, Plus, Trash2, PlayCircle, Sparkles, MessagesSquare, Satellite } from "lucide-react";

const CATEGORY_ICON = { ai: Sparkles, iletisim: MessagesSquare, mekansal: Satellite };

const emptyForm = { name: "", event_type: "", target_url: "", headersText: "" };

export default function IntegrationHub() {
  const [registry, setRegistry] = useState([]);
  const [eventTypes, setEventTypes] = useState([]);
  const [rules, setRules] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [deliveries, setDeliveries] = useState([]);
  const [testingId, setTestingId] = useState(null);

  const loadRules = () => api.get("/webhook-rules").then((r) => setRules(r.data));

  useEffect(() => {
    api.get("/integration-hub/registry").then((r) => setRegistry(r.data));
    api.get("/integration-hub/event-types").then((r) => setEventTypes(r.data));
    loadRules();
  }, []);

  const eventLabels = Object.fromEntries(eventTypes.map((e) => [e.key, e.label]));

  function parseHeaders(text) {
    const headers = {};
    text.split("\n").forEach((line) => {
      const idx = line.indexOf(":");
      if (idx > 0) headers[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
    });
    return headers;
  }

  async function submitRule(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/webhook-rules", {
        name: form.name, event_type: form.event_type, target_url: form.target_url,
        headers: parseHeaders(form.headersText),
      });
      setForm(emptyForm);
      loadRules();
    } catch (err) {
      setError(err.response?.data?.detail || "Webhook kuralı oluşturulamadı");
    }
  }

  async function toggleActive(rule) {
    if (rule.is_active) {
      await api.delete(`/webhook-rules/${rule.id}`);
    } else {
      await api.put(`/webhook-rules/${rule.id}`, { is_active: true });
    }
    loadRules();
  }

  async function testRule(rule) {
    setTestingId(rule.id);
    try {
      await api.post(`/webhook-rules/${rule.id}/test`);
      await toggleDeliveries(rule, true);
    } finally {
      setTestingId(null);
    }
  }

  async function toggleDeliveries(rule, forceOpen) {
    if (!forceOpen && expandedId === rule.id) {
      setExpandedId(null);
      return;
    }
    const r = await api.get(`/webhook-rules/${rule.id}/deliveries`);
    setDeliveries(r.data);
    setExpandedId(rule.id);
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="integration-hub-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FAZ 11 — PLATFORM CORE</div>
        <h1 className="font-display text-4xl flex items-center gap-2"><Cable size={28}/> Integration Hub</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Toprax dışarıya doğrudan bağlanmaz — tüm 3. parti çağrılar aşağıdaki envanterden geçer.
          Webhook kuralları ile iş olaylarını dış sistemlere bildirin.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
        {registry.map((r) => {
          const Icon = CATEGORY_ICON[r.category] || Cable;
          return (
            <div key={r.category} className="card p-4">
              <div className="flex items-center gap-2 mb-2">
                <Icon size={16} className="text-[var(--primary)]"/>
                <span className="font-medium text-sm">{r.label}</span>
              </div>
              <div className="text-[10px] text-[var(--text-dim)] mb-2">{r.module}</div>
              <div className="flex flex-wrap gap-1.5">
                {r.implementations.map((i) => <span key={i} className="badge badge-neutral text-[10px]">{i}</span>)}
              </div>
            </div>
          );
        })}
      </div>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      <form onSubmit={submitRule} className="card p-5 mb-6 space-y-3" data-testid="webhook-rule-form">
        <h3 className="font-display text-lg flex items-center gap-2"><Webhook size={16} className="text-[var(--primary)]"/>Yeni Webhook Kuralı</h3>
        <div className="grid grid-cols-2 gap-3">
          <input className="input" placeholder="Kural adı" required
                 value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}/>
          <select className="input" required value={form.event_type}
                  onChange={(e) => setForm((f) => ({ ...f, event_type: e.target.value }))}>
            <option value="">Olay seç...</option>
            {eventTypes.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}
          </select>
        </div>
        <input className="input" placeholder="Hedef URL (https://...)" required
               value={form.target_url} onChange={(e) => setForm((f) => ({ ...f, target_url: e.target.value }))}/>
        <textarea className="input" rows={2} placeholder={"Header'lar (opsiyonel, satır başına bir tane)\nAuthorization: Bearer xxx"}
                  value={form.headersText} onChange={(e) => setForm((f) => ({ ...f, headersText: e.target.value }))}/>
        <button type="submit" className="btn btn-primary" data-testid="webhook-rule-submit">Kuralı Oluştur</button>
      </form>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Ad</th><th className="p-4">Olay</th><th className="p-4">Hedef URL</th>
            <th className="p-4">Durum</th><th className="p-4"></th>
          </tr></thead>
          <tbody>
            {rules.map((r) => (
              <Fragment key={r.id}>
                <tr className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                  <td className="p-4">{r.name}</td>
                  <td className="p-4 text-xs text-[var(--text-dim)]">{eventLabels[r.event_type] || r.event_type}</td>
                  <td className="p-4 text-xs text-[var(--text-dim)] max-w-xs truncate">{r.target_url}</td>
                  <td className="p-4">
                    <button onClick={() => toggleActive(r)} className={`badge ${r.is_active === false ? "badge-d" : "badge-a"}`}>
                      {r.is_active === false ? "Pasif" : "Aktif"}
                    </button>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-1.5 justify-end">
                      <button onClick={() => testRule(r)} disabled={testingId === r.id} className="btn btn-ghost text-xs" data-testid={`webhook-test-${r.id}`}>
                        <PlayCircle size={12}/> {testingId === r.id ? "Test ediliyor…" : "Test Et"}
                      </button>
                      <button onClick={() => toggleDeliveries(r)} className="btn btn-ghost text-xs">
                        {expandedId === r.id ? "Gizle" : "Teslimatlar"}
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedId === r.id && (
                  <tr className="border-b border-[var(--border)] bg-[var(--surface-2)]">
                    <td colSpan="5" className="p-4">
                      <div className="space-y-1.5">
                        {deliveries.map((d) => (
                          <div key={d.id} className="flex items-center justify-between text-xs">
                            <span>{(d.attempted_at || "").replace("T", " ").slice(0, 19)} — {d.status_code ?? "—"}</span>
                            <span className={`badge ${d.ok ? "badge-a" : "badge-d"} text-[10px]`}>
                              {d.ok ? "Başarılı" : (d.error || "Başarısız")}
                            </span>
                          </div>
                        ))}
                        {deliveries.length === 0 && <div className="text-xs text-[var(--text-dim)]">Henüz teslimat yok</div>}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {rules.length === 0 && (
              <tr><td colSpan="5" className="p-6 text-center text-[var(--text-dim)]">Henüz webhook kuralı yok</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
