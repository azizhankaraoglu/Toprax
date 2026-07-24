/**
 * RAPOR OLUŞTURUCU (Denetim raporu #7 / Faz 6 — Elastik Rapor Modülü)
 *
 * Personelin kod yazmadan kendi raporunu tasarlayabildiği ekran: modül seç →
 * kolonları seç → (opsiyonel) Gelişmiş Filtre (FilterPanel.jsx, IT-09 ile
 * AYNI bileşen, "SON HAL #3" entegrasyonlarındaki gibi onFiltersChange ile
 * kullanılıyor) → (opsiyonel) grupla/topla → kaydet → önizle/CSV/PDF indir/
 * paylaş (kanal veya link)/zamanla.
 *
 * Alıcı seçimi bilinçli olarak SADELEŞTİRİLDİ: çiftçi alıcılar için mevcut
 * global arama (/search, IT-10) ile canlı arama var; personel alıcılar için
 * (settings:users_view her role açık olmadığından, bkz. permissions.py)
 * v1'de doğrudan kullanıcı ID'si girilir — tam bir personel seçici bu
 * iterasyonun kapsamı dışı bırakıldı.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import FilterPanel from "@/components/FilterPanel";
import Drawer from "@/components/Drawer";
import {
  FileBarChart2, Plus, Trash2, Eye, Download, FileDown, Share2, Clock,
  X, Copy, PlayCircle, Sparkles,
} from "lucide-react";

const AGG_OPS = [
  { v: "sum", l: "Toplam" }, { v: "avg", l: "Ortalama" }, { v: "count", l: "Adet" },
  { v: "min", l: "Minimum" }, { v: "max", l: "Maksimum" },
];
const CHANNEL_LABELS = { sms: "SMS", email: "E-posta", whatsapp: "WhatsApp", push: "Push", voice: "Sesli Arama" };
const FREQUENCY_LABELS = { gunluk: "Günlük", haftalik: "Haftalık", aylik: "Aylık" };

const emptyForm = {
  name: "", module: "", columns: [], filters: [], logic: "AND",
  group_by: "", aggregations: [], is_shared: false,
};

export default function ReportBuilder() {
  const [templates, setTemplates] = useState([]);
  const [modules, setModules] = useState([]);
  const [fields, setFields] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [aggDraft, setAggDraft] = useState({ field: "", op: "sum", label: "" });
  const [matchCount, setMatchCount] = useState(null);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewTemplate, setPreviewTemplate] = useState(null);

  const [shareOpen, setShareOpen] = useState(false);
  const [shareTemplate, setShareTemplate] = useState(null);
  const [shareRecipients, setShareRecipients] = useState([]);
  const [shareRecipientDraft, setShareRecipientDraft] = useState({ contact_type: "farmer", contact_id: "", channel: "sms" });
  const [farmerQuery, setFarmerQuery] = useState("");
  const [farmerResults, setFarmerResults] = useState([]);
  const [shareExpiresDays, setShareExpiresDays] = useState(7);
  const [shareResult, setShareResult] = useState(null);
  const [sharing, setSharing] = useState(false);

  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleTemplate, setScheduleTemplate] = useState(null);
  const [schedules, setSchedules] = useState([]);
  const [scheduleForm, setScheduleForm] = useState({ frequency: "haftalik", recipients: [], active: true });

  const loadTemplates = () => api.get("/report-templates").then((r) => setTemplates(r.data));

  useEffect(() => {
    loadTemplates();
    api.get("/report-templates/modules").then((r) => setModules(r.data));
    api.get("/report-schedules").then((r) => setSchedules(r.data)).catch(() => setSchedules([]));
  }, []);

  useEffect(() => {
    if (!form.module) { setFields([]); return; }
    api.get(`/query/${form.module}/filterable-fields`).then((r) => setFields(r.data.fields));
  }, [form.module]);

  useEffect(() => {
    if (farmerQuery.trim().length < 2) { setFarmerResults([]); return; }
    const t = setTimeout(() => {
      api.get("/search", { params: { q: farmerQuery, limit: 6 } })
        .then((r) => setFarmerResults(r.data.results?.farmers?.items || []));
    }, 300);
    return () => clearTimeout(t);
  }, [farmerQuery]);

  function toggleColumn(key) {
    setForm((f) => ({
      ...f, columns: f.columns.includes(key) ? f.columns.filter((c) => c !== key) : [...f.columns, key],
    }));
  }

  function addAggregation() {
    if (!aggDraft.field || !aggDraft.label.trim()) return;
    setForm((f) => ({ ...f, aggregations: [...f.aggregations, { ...aggDraft, label: aggDraft.label.trim() }] }));
    setAggDraft({ field: "", op: "sum", label: "" });
  }
  function removeAggregation(idx) {
    setForm((f) => ({ ...f, aggregations: f.aggregations.filter((_, i) => i !== idx) }));
  }

  async function saveTemplate(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/report-templates", form);
      setForm(emptyForm);
      setShowForm(false);
      setMatchCount(null);
      loadTemplates();
    } catch (err) {
      setError(err.response?.data?.detail || "Şablon kaydedilemedi");
    }
  }

  async function deleteTemplate(t) {
    if (!window.confirm(`"${t.name}" şablonu silinsin mi?`)) return;
    await api.delete(`/report-templates/${t.id}`);
    loadTemplates();
  }

  async function seedSamples() {
    await api.post("/report-templates/seed-samples");
    loadTemplates();
  }

  async function openPreview(t) {
    setPreviewTemplate(t);
    setPreviewOpen(true);
    setPreviewData(null);
    const { data } = await api.get(`/report-templates/${t.id}/preview`);
    setPreviewData(data);
  }

  async function downloadFile(t, kind) {
    const { data } = await api.get(`/report-templates/${t.id}/export.${kind}`, { responseType: "blob" });
    const url = URL.createObjectURL(data);
    if (kind === "pdf") {
      window.open(url, "_blank");
    } else {
      const a = document.createElement("a");
      a.href = url; a.download = `${t.name}.csv`; a.click();
    }
  }

  function openShare(t) {
    setShareTemplate(t);
    setShareOpen(true);
    setShareRecipients([]);
    setShareResult(null);
    setShareExpiresDays(7);
  }

  function addShareRecipient() {
    if (!shareRecipientDraft.contact_id) return;
    setShareRecipients((rs) => [...rs, shareRecipientDraft]);
    setShareRecipientDraft({ contact_type: shareRecipientDraft.contact_type, contact_id: "", channel: shareRecipientDraft.channel });
    setFarmerQuery(""); setFarmerResults([]);
  }
  function removeShareRecipient(idx) {
    setShareRecipients((rs) => rs.filter((_, i) => i !== idx));
  }

  async function doShare() {
    setSharing(true);
    try {
      const { data } = await api.post(`/report-templates/${shareTemplate.id}/share`, {
        recipients: shareRecipients, expires_days: shareExpiresDays,
      });
      setShareResult(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Paylaşılamadı");
    } finally {
      setSharing(false);
    }
  }

  function copyLink() {
    if (!shareResult) return;
    const full = `${window.location.origin}${shareResult.link}`;
    navigator.clipboard?.writeText(full);
  }

  function openSchedule(t) {
    setScheduleTemplate(t);
    setScheduleOpen(true);
    setScheduleForm({ frequency: "haftalik", recipients: [], active: true });
  }

  function addScheduleRecipient() {
    if (!shareRecipientDraft.contact_id) return;
    setScheduleForm((f) => ({ ...f, recipients: [...f.recipients, shareRecipientDraft] }));
    setShareRecipientDraft({ contact_type: shareRecipientDraft.contact_type, contact_id: "", channel: shareRecipientDraft.channel });
    setFarmerQuery(""); setFarmerResults([]);
  }
  function removeScheduleRecipient(idx) {
    setScheduleForm((f) => ({ ...f, recipients: f.recipients.filter((_, i) => i !== idx) }));
  }

  async function createSchedule() {
    await api.post("/report-schedules", { template_id: scheduleTemplate.id, ...scheduleForm });
    setScheduleOpen(false);
    api.get("/report-schedules").then((r) => setSchedules(r.data));
  }

  async function deleteSchedule(id) {
    await api.delete(`/report-schedules/${id}`);
    api.get("/report-schedules").then((r) => setSchedules(r.data));
  }

  async function runScheduledTick() {
    await api.post("/reports/run-scheduled");
    api.get("/report-schedules").then((r) => setSchedules(r.data));
  }

  const schedulesByTemplate = schedules.reduce((acc, s) => {
    (acc[s.template_id] = acc[s.template_id] || []).push(s);
    return acc;
  }, {});

  return (
    <div className="p-8 max-w-[1400px]" data-testid="report-builder-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">RAPORLAR</div>
          <h1 className="font-display text-4xl">Rapor Oluşturucu</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Kod yazmadan kendi raporunuzu tasarlayın; kanal (SMS/E-posta/WhatsApp) veya link ile paylaşın,
            periyodik gönderim planlayın.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={runScheduledTick} className="btn btn-ghost text-sm flex items-center gap-1.5" data-testid="run-scheduled-reports-btn">
            <Clock size={14}/> Zamanı Gelenleri Çalıştır
          </button>
          <button onClick={seedSamples} className="btn btn-ghost text-sm flex items-center gap-1.5">
            <Sparkles size={14}/> Örnek Şablonları Yükle
          </button>
          <button onClick={() => setShowForm((s) => !s)} className="btn btn-primary text-sm flex items-center gap-1.5" data-testid="new-report-template-btn">
            <Plus size={14}/> Yeni Şablon
          </button>
        </div>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      {showForm && (
        <form onSubmit={saveTemplate} className="card p-5 mb-6 space-y-4" data-testid="report-template-form">
          <div className="grid grid-cols-2 gap-3">
            <input className="input" placeholder="Şablon adı" required
                   value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}/>
            <select className="input" required value={form.module}
                    onChange={(e) => setForm((f) => ({ ...f, module: e.target.value, columns: [], group_by: "", aggregations: [] }))}>
              <option value="">Modül seç...</option>
              {modules.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>

          {form.module && (
            <>
              <div>
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Kolonlar (boş bırakılırsa tüm alanlar)</div>
                <div className="flex flex-wrap gap-2">
                  {fields.map((f) => (
                    <label key={f.key} className="flex items-center gap-1.5 badge badge-neutral cursor-pointer">
                      <input type="checkbox" checked={form.columns.includes(f.key)} onChange={() => toggleColumn(f.key)}/>
                      {f.label}
                    </label>
                  ))}
                </div>
              </div>

              <FilterPanel
                module={form.module}
                onFiltersChange={(filters, logic) => setForm((f) => ({ ...f, filters, logic }))}
                onResults={(items, total) => setMatchCount(total)}
              />
              {matchCount !== null && (
                <div className="text-xs text-[var(--text-dim)]">Filtreyle eşleşen kayıt: {matchCount}</div>
              )}

              <div>
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Grupla / Topla (opsiyonel)</div>
                <select className="input mb-2" value={form.group_by}
                        onChange={(e) => setForm((f) => ({ ...f, group_by: e.target.value, aggregations: e.target.value ? f.aggregations : [] }))}>
                  <option value="">Gruplama yok</option>
                  {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                </select>

                {form.group_by && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <select className="input flex-1" value={aggDraft.field} onChange={(e) => setAggDraft((d) => ({ ...d, field: e.target.value }))}>
                        <option value="">Toplanacak alan...</option>
                        {fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                      </select>
                      <select className="input w-36" value={aggDraft.op} onChange={(e) => setAggDraft((d) => ({ ...d, op: e.target.value }))}>
                        {AGG_OPS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
                      </select>
                      <input className="input flex-1" placeholder="Sütun başlığı (ör. Toplam Alan)"
                             value={aggDraft.label} onChange={(e) => setAggDraft((d) => ({ ...d, label: e.target.value }))}/>
                      <button type="button" onClick={addAggregation} className="btn btn-ghost text-xs"><Plus size={12}/> Ekle</button>
                    </div>
                    {form.aggregations.map((a, i) => (
                      <div key={i} className="flex items-center gap-2 bg-[var(--surface-2)] rounded-lg p-2 text-sm">
                        <span className="flex-1">{a.label} = {AGG_OPS.find((o) => o.v === a.op)?.l}({fields.find((f) => f.key === a.field)?.label || a.field})</span>
                        <button type="button" onClick={() => removeAggregation(i)} className="text-[var(--text-dim)] hover:text-red-400"><X size={13}/></button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
                <input type="checkbox" checked={form.is_shared} onChange={(e) => setForm((f) => ({ ...f, is_shared: e.target.checked }))}/>
                Tenant içindeki herkesle paylaş (görüntüleme yetkisi olanlar görür)
              </label>
            </>
          )}

          <button type="submit" className="btn btn-primary" data-testid="report-template-submit">Şablonu Kaydet</button>
        </form>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {templates.map((t) => (
          <div key={t.id} className="card p-4" data-testid={`report-template-${t.id}`}>
            <div className="flex items-start justify-between mb-2">
              <div>
                <div className="font-medium flex items-center gap-1.5"><FileBarChart2 size={14} className="text-[var(--primary)]"/>{t.name}</div>
                <div className="text-[11px] text-[var(--text-dim)] mt-0.5">{t.module_label || t.module}</div>
              </div>
              {t.is_shared && <span className="badge badge-neutral text-[10px]">Paylaşılan</span>}
            </div>
            {schedulesByTemplate[t.id]?.length > 0 && (
              <div className="text-[11px] text-[var(--text-dim)] mb-2 flex items-center gap-1">
                <Clock size={11}/> {FREQUENCY_LABELS[schedulesByTemplate[t.id][0].frequency]} zamanlanmış
              </div>
            )}
            <div className="flex flex-wrap gap-1.5 mt-2">
              <button onClick={() => openPreview(t)} className="btn btn-ghost text-xs"><Eye size={12}/> Önizle</button>
              <button onClick={() => downloadFile(t, "csv")} className="btn btn-ghost text-xs"><Download size={12}/> CSV</button>
              <button onClick={() => downloadFile(t, "pdf")} className="btn btn-ghost text-xs"><FileDown size={12}/> PDF</button>
              <button onClick={() => openShare(t)} className="btn btn-ghost text-xs" data-testid={`report-share-${t.id}`}><Share2 size={12}/> Paylaş</button>
              <button onClick={() => openSchedule(t)} className="btn btn-ghost text-xs"><Clock size={12}/> Zamanla</button>
              {t.is_owner !== false && (
                <button onClick={() => deleteTemplate(t)} className="btn btn-ghost text-xs text-red-400"><Trash2 size={12}/></button>
              )}
            </div>
          </div>
        ))}
        {templates.length === 0 && (
          <div className="col-span-full text-center text-[var(--text-dim)] py-10 text-sm card">
            Henüz rapor şablonu yok — "Örnek Şablonları Yükle" veya "Yeni Şablon" ile başlayın.
          </div>
        )}
      </div>

      {/* ÖNİZLEME */}
      <Drawer open={previewOpen} onClose={() => setPreviewOpen(false)} title={previewTemplate?.name || "Önizleme"} width="640px">
        <div className="p-4">
          {!previewData ? (
            <div className="text-sm text-[var(--text-dim)]">Yükleniyor…</div>
          ) : (
            <>
              <div className="text-xs text-[var(--text-dim)] mb-3">
                Toplam {previewData.total} kayıt {previewData.truncated && "(ilk 500 kayıt gösteriliyor)"}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase border-b border-[var(--border)]">
                      {previewData.columns.map((c) => <th key={c} className="p-2">{c}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {previewData.rows.map((row, i) => (
                      <tr key={i} className="border-b border-[var(--border)]">
                        {previewData.columns.map((c) => <td key={c} className="p-2">{String(row[c] ?? "—")}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {previewData.rows.length === 0 && <div className="text-center text-[var(--text-dim)] py-6">Kayıt yok</div>}
              </div>
            </>
          )}
        </div>
      </Drawer>

      {/* PAYLAŞIM */}
      <Drawer open={shareOpen} onClose={() => setShareOpen(false)} title={`Paylaş: ${shareTemplate?.name || ""}`}>
        <div className="p-4 space-y-3">
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Bağlantı süresi (gün)</label>
            <input className="input" type="number" min={1} value={shareExpiresDays} onChange={(e) => setShareExpiresDays(Number(e.target.value))}/>
          </div>

          <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Alıcılar (opsiyonel — boş bırakılırsa sadece bağlantı üretilir)</div>
          <div className="space-y-2">
            <select className="input" value={shareRecipientDraft.contact_type}
                    onChange={(e) => setShareRecipientDraft((d) => ({ ...d, contact_type: e.target.value, contact_id: "" }))}>
              <option value="farmer">Çiftçi</option>
              <option value="personnel">Personel</option>
            </select>
            {shareRecipientDraft.contact_type === "farmer" ? (
              <div className="relative">
                <input className="input" placeholder="Çiftçi ara (ad, telefon, üye no)..." value={farmerQuery}
                       onChange={(e) => { setFarmerQuery(e.target.value); setShareRecipientDraft((d) => ({ ...d, contact_id: "" })); }}/>
                {farmerResults.length > 0 && !shareRecipientDraft.contact_id && (
                  <div className="absolute z-10 w-full bg-[var(--surface)] border border-[var(--border)] rounded-lg mt-1 max-h-40 overflow-y-auto">
                    {farmerResults.map((f) => (
                      <button key={f.id} type="button" className="block w-full text-left px-3 py-1.5 text-sm hover:bg-[var(--surface-2)]"
                              onClick={() => { setShareRecipientDraft((d) => ({ ...d, contact_id: f.id })); setFarmerQuery(f.full_name); setFarmerResults([]); }}>
                        {f.full_name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <input className="input" placeholder="Personel kullanıcı ID"
                     value={shareRecipientDraft.contact_id}
                     onChange={(e) => setShareRecipientDraft((d) => ({ ...d, contact_id: e.target.value }))}/>
            )}
            <div className="flex items-center gap-2">
              <select className="input flex-1" value={shareRecipientDraft.channel} onChange={(e) => setShareRecipientDraft((d) => ({ ...d, channel: e.target.value }))}>
                {Object.entries(CHANNEL_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              <button type="button" onClick={addShareRecipient} className="btn btn-ghost text-xs"><Plus size={12}/> Ekle</button>
            </div>
          </div>
          <div className="space-y-1.5">
            {shareRecipients.map((r, i) => (
              <div key={i} className="flex items-center justify-between bg-[var(--surface-2)] rounded-lg p-2 text-xs">
                <span>{r.contact_type === "farmer" ? "Çiftçi" : "Personel"} · {CHANNEL_LABELS[r.channel]} · {r.contact_id.slice(0, 8)}…</span>
                <button onClick={() => removeShareRecipient(i)} className="text-[var(--text-dim)] hover:text-red-400"><X size={12}/></button>
              </div>
            ))}
          </div>

          <button onClick={doShare} disabled={sharing} className="btn btn-primary w-full" data-testid="report-share-submit">
            {sharing ? "Paylaşılıyor…" : "Paylaş"}
          </button>

          {shareResult && (
            <div className="bg-[var(--surface-2)] rounded-lg p-3 space-y-2">
              <div className="text-xs text-[var(--text-dim)]">Bağlantı ({shareResult.expires_at?.slice(0, 10)} tarihine kadar geçerli):</div>
              <div className="flex items-center gap-2">
                <input className="input flex-1 text-xs" readOnly value={`${window.location.origin}${shareResult.link}`}/>
                <button onClick={copyLink} className="btn btn-ghost text-xs"><Copy size={12}/></button>
              </div>
              {shareResult.results?.length > 0 && (
                <div className="space-y-1">
                  {shareResult.results.map((r, i) => (
                    <div key={i} className="text-xs flex items-center justify-between">
                      <span>{CHANNEL_LABELS[r.channel]} → {r.contact_id.slice(0, 8)}…</span>
                      <span className={`badge ${r.ok ? "badge-a" : "badge-d"} text-[10px]`}>{r.ok ? "Gönderildi" : "Başarısız"}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </Drawer>

      {/* ZAMANLAMA */}
      <Drawer open={scheduleOpen} onClose={() => setScheduleOpen(false)} title={`Zamanla: ${scheduleTemplate?.name || ""}`}>
        <div className="p-4 space-y-3">
          <div>
            <label className="text-xs text-[var(--text-dim)] mb-1 block">Sıklık</label>
            <select className="input" value={scheduleForm.frequency} onChange={(e) => setScheduleForm((f) => ({ ...f, frequency: e.target.value }))}>
              {Object.entries(FREQUENCY_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>

          <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Alıcılar</div>
          <div className="space-y-2">
            <select className="input" value={shareRecipientDraft.contact_type}
                    onChange={(e) => setShareRecipientDraft((d) => ({ ...d, contact_type: e.target.value, contact_id: "" }))}>
              <option value="farmer">Çiftçi</option>
              <option value="personnel">Personel</option>
            </select>
            {shareRecipientDraft.contact_type === "farmer" ? (
              <div className="relative">
                <input className="input" placeholder="Çiftçi ara (ad, telefon, üye no)..." value={farmerQuery}
                       onChange={(e) => { setFarmerQuery(e.target.value); setShareRecipientDraft((d) => ({ ...d, contact_id: "" })); }}/>
                {farmerResults.length > 0 && !shareRecipientDraft.contact_id && (
                  <div className="absolute z-10 w-full bg-[var(--surface)] border border-[var(--border)] rounded-lg mt-1 max-h-40 overflow-y-auto">
                    {farmerResults.map((f) => (
                      <button key={f.id} type="button" className="block w-full text-left px-3 py-1.5 text-sm hover:bg-[var(--surface-2)]"
                              onClick={() => { setShareRecipientDraft((d) => ({ ...d, contact_id: f.id })); setFarmerQuery(f.full_name); setFarmerResults([]); }}>
                        {f.full_name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <input className="input" placeholder="Personel kullanıcı ID"
                     value={shareRecipientDraft.contact_id}
                     onChange={(e) => setShareRecipientDraft((d) => ({ ...d, contact_id: e.target.value }))}/>
            )}
            <div className="flex items-center gap-2">
              <select className="input flex-1" value={shareRecipientDraft.channel} onChange={(e) => setShareRecipientDraft((d) => ({ ...d, channel: e.target.value }))}>
                {Object.entries(CHANNEL_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              <button type="button" onClick={addScheduleRecipient} className="btn btn-ghost text-xs"><Plus size={12}/> Ekle</button>
            </div>
          </div>
          <div className="space-y-1.5">
            {scheduleForm.recipients.map((r, i) => (
              <div key={i} className="flex items-center justify-between bg-[var(--surface-2)] rounded-lg p-2 text-xs">
                <span>{r.contact_type === "farmer" ? "Çiftçi" : "Personel"} · {CHANNEL_LABELS[r.channel]} · {r.contact_id.slice(0, 8)}…</span>
                <button onClick={() => removeScheduleRecipient(i)} className="text-[var(--text-dim)] hover:text-red-400"><X size={12}/></button>
              </div>
            ))}
          </div>

          <button onClick={createSchedule} className="btn btn-primary w-full" data-testid="report-schedule-submit">Zamanlamayı Oluştur</button>

          {schedulesByTemplate[scheduleTemplate?.id]?.length > 0 && (
            <div className="pt-3 border-t border-[var(--border)] space-y-2">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Mevcut Zamanlamalar</div>
              {schedulesByTemplate[scheduleTemplate.id].map((s) => (
                <div key={s.id} className="flex items-center justify-between bg-[var(--surface-2)] rounded-lg p-2 text-xs">
                  <span className="flex items-center gap-1.5"><PlayCircle size={12}/> {FREQUENCY_LABELS[s.frequency]} · {s.recipients.length} alıcı</span>
                  <button onClick={() => deleteSchedule(s.id)} className="text-[var(--text-dim)] hover:text-red-400"><Trash2 size={12}/></button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Drawer>
    </div>
  );
}
