/**
 * KAMPANYALAR (IT-26 / FAZ 9 devam — Segment + Kampanya + Planlı Gönderim +
 * Onay + Retry/Fallback)
 *
 * Segment seçimi AYRI bir ekran İCAT ETMEDİ — Farmers.jsx'teki "Gelişmiş
 * Filtre" (FilterPanel.jsx, IT-09) ile kaydedilen Kayıtlı Sorgular'dan
 * module="farmers" olanları listeler (backend campaigns.py bunu doğrudan
 * saved_queries koleksiyonundan çözer). Kanal zinciri (retry/fallback
 * sırası) AutomationRules.jsx'teki koşul listesiyle AYNI aile: seç+ekle,
 * chip'ler sırayla gösterilir, sıra = ekleme sırası = deneme önceliği.
 */
import { Fragment, useEffect, useState } from "react";
import api from "@/api";
import { Megaphone, Plus, X, PlayCircle, CheckCircle2, Clock } from "lucide-react";

const STATUS_BADGE = { taslak: "badge-neutral", planlandi: "badge-c", yayinda: "badge-b", tamamlandi: "badge-a", iptal_edildi: "badge-d" };
const STATUS_LABELS = { taslak: "Taslak", planlandi: "Planlandı", yayinda: "Yayında", tamamlandi: "Tamamlandı", iptal_edildi: "İptal Edildi" };

const emptyForm = { name: "", channel_chain: [], segment_query_id: "", template_ids: {}, requires_approval: false, scheduled_at: "" };

export default function CampaignManagement() {
  const [campaigns, setCampaigns] = useState([]);
  const [segments, setSegments] = useState([]);
  const [channels, setChannels] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [channelToAdd, setChannelToAdd] = useState("");
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [results, setResults] = useState([]);

  const load = () => api.get("/campaigns").then((r) => setCampaigns(r.data));

  useEffect(() => {
    load();
    api.get("/saved-queries", { params: { module: "farmers" } }).then((r) => setSegments(r.data));
    api.get("/channels").then((r) => setChannels(r.data));
    api.get("/templates").then((r) => setTemplates(r.data));
  }, []);

  const channelLabel = (key) => channels.find((c) => c.key === key)?.label || key;
  const segmentsById = new Map(segments.map((s) => [s.id, s]));

  function addChainChannel() {
    if (!channelToAdd || form.channel_chain.includes(channelToAdd)) return;
    setForm((f) => ({ ...f, channel_chain: [...f.channel_chain, channelToAdd] }));
    setChannelToAdd("");
  }
  function removeChainChannel(ch) {
    setForm((f) => ({
      ...f, channel_chain: f.channel_chain.filter((c) => c !== ch),
      template_ids: Object.fromEntries(Object.entries(f.template_ids).filter(([k]) => k !== ch)),
    }));
  }
  function setChannelTemplate(ch, templateId) {
    setForm((f) => ({ ...f, template_ids: { ...f.template_ids, [ch]: templateId } }));
  }

  async function submitCampaign(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/campaigns", {
        ...form,
        scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null,
      });
      setForm(emptyForm);
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Kampanya oluşturulamadı");
    }
  }

  async function transition(id, status) {
    try {
      await api.put(`/campaigns/${id}/transition`, { status });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Durum değiştirilemedi");
    }
  }

  async function approve(id) {
    await api.post(`/campaigns/${id}/approve`);
    load();
  }

  async function runScheduledTick() {
    await api.post("/campaigns/run-scheduled");
    load();
  }

  async function toggleResults(campaign) {
    if (expandedId === campaign.id) {
      setExpandedId(null);
      return;
    }
    const r = await api.get(`/campaigns/${campaign.id}/results`);
    setResults(r.data);
    setExpandedId(campaign.id);
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="campaign-management-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">İLETİŞİM MERKEZİ</div>
          <h1 className="font-display text-4xl">Kampanyalar</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Bir segmente (Çiftçiler ekranındaki Kayıtlı Sorgular'dan) çoklu kanal, planlı ve
            retry/fallback zincirli toplu gönderim yapın.
          </p>
        </div>
        <button onClick={runScheduledTick} className="btn btn-ghost text-sm flex items-center gap-1.5" data-testid="run-scheduled-btn">
          <Clock size={14}/> Zamanı Gelenleri Çalıştır
        </button>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      <form onSubmit={submitCampaign} className="card p-5 mb-6 space-y-3" data-testid="campaign-form">
        <h3 className="font-display text-lg flex items-center gap-2"><Megaphone size={16} className="text-[var(--primary)]"/>Yeni Kampanya</h3>
        <div className="grid grid-cols-2 gap-3">
          <input className="input" placeholder="Kampanya adı" required
                 value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}/>
          <select className="input" required value={form.segment_query_id}
                  onChange={(e) => setForm((f) => ({ ...f, segment_query_id: e.target.value }))}>
            <option value="">Segment (Kayıtlı Sorgu) seç...</option>
            {segments.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        {segments.length === 0 && (
          <div className="text-xs text-[var(--text-dim)]">
            Henüz "farmers" modülü için Kayıtlı Sorgu yok — Çiftçiler ekranında "Gelişmiş Filtre" ile bir filtre kaydedin.
          </div>
        )}

        <div>
          <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">
            Kanal Zinciri (retry/fallback — sıradaki kanal bir öncekinin başarısız olması durumunda denenir)
          </div>
          <div className="flex items-center gap-2 mb-2">
            <select className="input flex-1" value={channelToAdd} onChange={(e) => setChannelToAdd(e.target.value)}>
              <option value="">Kanal seç...</option>
              {channels.filter((c) => !form.channel_chain.includes(c.key)).map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
            <button type="button" onClick={addChainChannel} className="btn btn-ghost text-xs"><Plus size={12}/> Ekle</button>
          </div>
          <div className="space-y-2">
            {form.channel_chain.map((ch, idx) => (
              <div key={ch} className="flex items-center gap-2 bg-[var(--surface-2)] rounded-lg p-2">
                <span className="badge badge-neutral text-[10px]">{idx + 1}</span>
                <span className="text-sm flex-1">{channelLabel(ch)}</span>
                <select className="input flex-1" value={form.template_ids[ch] || ""}
                        onChange={(e) => setChannelTemplate(ch, e.target.value)}>
                  <option value="">Şablon seç...</option>
                  {templates.filter((t) => t.channel === ch).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <button type="button" onClick={() => removeChainChannel(ch)} className="text-[var(--text-dim)] hover:text-red-400">
                  <X size={14}/>
                </button>
              </div>
            ))}
            {form.channel_chain.length === 0 && <div className="text-xs text-[var(--text-dim)]">Henüz kanal eklenmedi</div>}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <label className="text-xs text-[var(--text-dim)] flex items-center gap-2">
            <input type="checkbox" checked={form.requires_approval}
                   onChange={(e) => setForm((f) => ({ ...f, requires_approval: e.target.checked }))}/>
            Gönderim için yönetici onayı gerekli
          </label>
          <div className="flex items-center gap-2">
            <label className="text-xs text-[var(--text-dim)]">Planlı gönderim (opsiyonel):</label>
            <input type="datetime-local" className="input" value={form.scheduled_at}
                   onChange={(e) => setForm((f) => ({ ...f, scheduled_at: e.target.value }))}/>
          </div>
        </div>

        <button type="submit" className="btn btn-primary" data-testid="campaign-submit">Kampanyayı Oluştur</button>
      </form>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Ad</th><th className="p-4">Segment</th><th className="p-4">Kanal Zinciri</th>
            <th className="p-4">Durum</th><th className="p-4">Sonuç</th><th className="p-4"></th>
          </tr></thead>
          <tbody>
            {campaigns.map((c) => (
              <Fragment key={c.id}>
                <tr className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                  <td className="p-4">{c.name}</td>
                  <td className="p-4 text-xs text-[var(--text-dim)]">{segmentsById.get(c.segment_query_id)?.name || "—"}</td>
                  <td className="p-4 text-xs text-[var(--text-dim)]">{c.channel_chain.map(channelLabel).join(" → ")}</td>
                  <td className="p-4">
                    <span className={`badge ${STATUS_BADGE[c.status] || "badge-neutral"}`}>{STATUS_LABELS[c.status] || c.status}</span>
                    {c.requires_approval && !c.approved && c.status !== "tamamlandi" && (
                      <span className="badge badge-d text-[10px] ml-1">Onay Bekliyor</span>
                    )}
                  </td>
                  <td className="p-4 text-xs text-[var(--text-dim)]">
                    {c.result_summary ? `${c.result_summary.sent}/${c.result_summary.total} başarılı` : "—"}
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-1.5 justify-end">
                      {c.requires_approval && !c.approved && c.status !== "tamamlandi" && c.status !== "iptal_edildi" && (
                        <button onClick={() => approve(c.id)} className="btn btn-ghost text-xs" data-testid={`campaign-approve-${c.id}`}>
                          <CheckCircle2 size={12}/> Onayla
                        </button>
                      )}
                      {c.status === "taslak" && (
                        <button onClick={() => transition(c.id, "planlandi")} className="btn btn-ghost text-xs">Planla</button>
                      )}
                      {(c.status === "taslak" || c.status === "planlandi") && (
                        <button onClick={() => transition(c.id, "yayinda")} className="btn btn-primary text-xs" data-testid={`campaign-send-${c.id}`}>
                          <PlayCircle size={12}/> Şimdi Gönder
                        </button>
                      )}
                      {(c.status === "taslak" || c.status === "planlandi") && (
                        <button onClick={() => transition(c.id, "iptal_edildi")} className="btn btn-ghost text-xs text-red-400">İptal</button>
                      )}
                      {c.status === "tamamlandi" && (
                        <button onClick={() => toggleResults(c)} className="btn btn-ghost text-xs">
                          {expandedId === c.id ? "Gizle" : "Sonuçlar"}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                {expandedId === c.id && (
                  <tr className="border-b border-[var(--border)] bg-[var(--surface-2)]">
                    <td colSpan="6" className="p-4">
                      <div className="space-y-1.5">
                        {results.map((r) => (
                          <div key={r.id} className="flex items-center justify-between text-xs">
                            <span>{channelLabel(r.channel)} → {r.recipient || "—"}</span>
                            <span className={`badge ${r.status === "basarisiz" ? "badge-d" : "badge-a"} text-[10px]`}>
                              {r.status === "basarisiz" ? "Başarısız" : "Teslim Edildi"}
                            </span>
                          </div>
                        ))}
                        {results.length === 0 && <div className="text-xs text-[var(--text-dim)]">Kayıt yok</div>}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {campaigns.length === 0 && (
              <tr><td colSpan="6" className="p-6 text-center text-[var(--text-dim)]">Henüz kampanya yok</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
