/**
 * AI YÖNETİŞİMİ (2026-08-19)
 *
 * backend/ai_governance.py'nin admin ekranı — TÜM AI çıktısının prompt,
 * kural (guardrail) ve kaynak (RAG) otoritesi. Dört sekme, PlatformCore.jsx'in
 * sekme kalıbıyla AYNI görsel dil (yeni tasarım dili İCAT EDİLMEZ — CLAUDE.md
 * konvansiyon #9):
 *
 *   Sistem Promptları · Guardrail'ler · Bilgi Bankası (RAG) · Test Konsolu
 *
 * Bu ekran `adminTierOnly`'dir (Layout.jsx) VE backend ayrıca
 * `ai_governance:view/manage` izinlerini zorunlu kılar — menüden gizlemek tek
 * başına bir güvenlik önlemi DEĞİLDİR.
 */
import { useEffect, useRef, useState } from "react";
import api from "@/api";
import {
  Brain, ShieldAlert, BookOpen, TerminalSquare, Save, Trash2, Upload,
  RefreshCw, Plus, AlertTriangle, CheckCircle2, Loader2, FileText,
} from "lucide-react";

const RAG_MODE_LABEL = {
  embedding: { label: "Anlamsal (embedding)", cls: "badge-a" },
  keyword: { label: "Anahtar kelime (embedding modeli yok)", cls: "badge-c" },
  bos: { label: "Kaynak bulunamadı", cls: "badge-neutral" },
};

const errText = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(", ");
  return e?.message || "Bilinmeyen hata";
};

export default function AiGovernance() {
  const [tab, setTab] = useState("prompts");
  const [msg, setMsg] = useState(null); // {kind:"ok"|"err", text}
  const flash = (kind, text) => { setMsg({ kind, text }); setTimeout(() => setMsg(null), 6000); };

  return (
    <div className="p-8 max-w-[1400px]" data-testid="ai-governance-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">AI YÖNETİŞİMİ</div>
        <h1 className="font-display text-4xl flex items-center gap-2">
          <Brain size={28} /> Prompt &amp; Bilgi Bankası Yönetimi
        </h1>
        <p className="text-[var(--text-dim)] text-sm mt-1 max-w-3xl">
          Platformdaki <b>tüm</b> yapay zekâ çıktısının en üst düzey yöneticisi. Sistem
          promptları modelin kimliğini, guardrail'ler nelerin yanıtlanmayacağını, bilgi
          bankası ise modelin hangi kurum belgelerine dayanacağını belirler.
        </p>
      </header>

      {msg && (
        <div className={`card p-3 mb-4 text-sm flex items-center gap-2 ${
          msg.kind === "ok" ? "text-[var(--primary)]" : "text-red-400"}`}>
          {msg.kind === "ok" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          {msg.text}
        </div>
      )}

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <button onClick={() => setTab("prompts")} className={`btn text-sm ${tab === "prompts" ? "btn-primary" : "btn-ghost"}`}><Brain size={14} /> Sistem Promptları</button>
        <button onClick={() => setTab("rails")} className={`btn text-sm ${tab === "rails" ? "btn-primary" : "btn-ghost"}`}><ShieldAlert size={14} /> Guardrail'ler</button>
        <button onClick={() => setTab("rag")} className={`btn text-sm ${tab === "rag" ? "btn-primary" : "btn-ghost"}`}><BookOpen size={14} /> Bilgi Bankası (RAG)</button>
        <button onClick={() => setTab("test")} className={`btn text-sm ${tab === "test" ? "btn-primary" : "btn-ghost"}`}><TerminalSquare size={14} /> Test Konsolu</button>
      </div>

      {tab === "prompts" && <PromptsTab flash={flash} />}
      {tab === "rails" && <GuardrailsTab flash={flash} />}
      {tab === "rag" && <RagTab flash={flash} />}
      {tab === "test" && <TestTab flash={flash} />}
    </div>
  );
}

/* =====================================================================
   SEKME 1 — SİSTEM PROMPTLARI
   ===================================================================== */
function PromptsTab({ flash }) {
  const [rows, setRows] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [saving, setSaving] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/ai-governance/prompts")
    .then((r) => {
      setRows(r.data || []);
      setDrafts(Object.fromEntries((r.data || []).map((p) => [p.scope, p.body || ""])));
    })
    .catch((e) => flash("err", errText(e)));

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  async function save(scope) {
    setSaving(scope);
    try {
      await api.put(`/ai-governance/prompts/${scope}`, { scope, body: drafts[scope] || "", is_active: true });
      flash("ok", `"${scope}" promptu kaydedildi.`);
      load();
    } catch (e) { flash("err", errText(e)); } finally { setSaving(null); }
  }

  async function seed() {
    setBusy(true);
    try {
      const r = await api.post("/ai-governance/seed-defaults");
      flash("ok", `Varsayılanlar yüklendi — ${r.data.prompts_created} prompt, ${r.data.guardrails_created} guardrail eklendi.`);
      load();
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="card p-4 flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-[var(--text-dim)] max-w-2xl">
          <b>Global</b> prompt her AI çağrısının başına eklenir; kapsam promptu onun ardına
          gelir. Gövde değiştiğinde eski sürüm otomatik arşivlenir.
        </p>
        <button className="btn btn-ghost text-xs" onClick={seed} disabled={busy}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Varsayılanları Yükle
        </button>
      </div>

      {rows.map((p) => (
        <div key={p.scope} className="card p-4" data-testid={`prompt-${p.scope}`}>
          <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
            <div>
              <div className="font-medium">{p.label}</div>
              <div className="text-xs text-[var(--text-dim)]">
                kapsam: <code>{p.scope}</code>
                {p.version ? ` · sürüm ${p.version}` : " · henüz tanımlanmadı"}
                {p.updated_by ? ` · son düzenleyen ${p.updated_by}` : ""}
              </div>
            </div>
            <button className="btn btn-primary text-xs" onClick={() => save(p.scope)}
                    disabled={saving === p.scope}>
              {saving === p.scope ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Kaydet
            </button>
          </div>
          <textarea
            className="input w-full font-mono text-xs"
            rows={p.scope === "global" ? 8 : 4}
            value={drafts[p.scope] ?? ""}
            placeholder="Bu kapsam için sistem promptu…"
            onChange={(e) => setDrafts((d) => ({ ...d, [p.scope]: e.target.value }))}
          />
        </div>
      ))}
    </div>
  );
}

/* =====================================================================
   SEKME 2 — GUARDRAIL'LER
   ===================================================================== */
const EMPTY_RAIL = {
  name: "", description: "", scopes: [],
  blocked_input: "", blocked_output: "",
  policy_text: "", required_notice: "", refusal_message: "",
  is_regex: false,
};

function GuardrailsTab({ flash }) {
  const [rows, setRows] = useState([]);
  const [scopes, setScopes] = useState([]);
  const [form, setForm] = useState(EMPTY_RAIL);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/ai-governance/guardrails")
    .then((r) => setRows(r.data || [])).catch((e) => flash("err", errText(e)));

  useEffect(() => {
    load();
    api.get("/ai-governance/scopes").then((r) => setScopes(r.data || [])).catch(() => {});
    /* eslint-disable-next-line */
  }, []);

  const toList = (s) => (s || "").split(",").map((x) => x.trim()).filter(Boolean);

  async function submit() {
    if (!form.name.trim()) return flash("err", "Kural adı zorunlu.");
    setBusy(true);
    const payload = {
      ...form,
      blocked_input: toList(form.blocked_input),
      blocked_output: toList(form.blocked_output),
    };
    try {
      if (editing) await api.put(`/ai-governance/guardrails/${editing}`, payload);
      else await api.post("/ai-governance/guardrails", payload);
      flash("ok", editing ? "Kural güncellendi." : "Kural eklendi.");
      setForm(EMPTY_RAIL); setEditing(null); load();
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  function edit(r) {
    setEditing(r.id);
    setForm({
      name: r.name || "", description: r.description || "", scopes: r.scopes || [],
      blocked_input: (r.blocked_input || []).join(", "),
      blocked_output: (r.blocked_output || []).join(", "),
      policy_text: r.policy_text || "", required_notice: r.required_notice || "",
      refusal_message: r.refusal_message || "", is_regex: !!r.is_regex,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function remove(r) {
    if (!window.confirm(`"${r.name}" kuralı pasife alınsın mı?`)) return;
    try { await api.delete(`/ai-governance/guardrails/${r.id}`); flash("ok", "Kural pasife alındı."); load(); }
    catch (e) { flash("err", errText(e)); }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="card p-4">
        <div className="font-medium mb-3">{editing ? "Kuralı Düzenle" : "Yeni Guardrail"}</div>
        <div className="grid md:grid-cols-2 gap-3">
          <label className="text-xs">Kural Adı *
            <input className="input w-full mt-1" value={form.name}
                   onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="text-xs">Açıklama
            <input className="input w-full mt-1" value={form.description}
                   onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </label>
          <label className="text-xs">Engellenen SORU ifadeleri (virgülle)
            <input className="input w-full mt-1" placeholder="tc kimlik, iban, kredi kartı"
                   value={form.blocked_input}
                   onChange={(e) => setForm({ ...form, blocked_input: e.target.value })} />
          </label>
          <label className="text-xs">Engellenen YANIT ifadeleri (virgülle)
            <input className="input w-full mt-1" value={form.blocked_output}
                   onChange={(e) => setForm({ ...form, blocked_output: e.target.value })} />
          </label>
          <label className="text-xs md:col-span-2">Politika metni (sistem promptuna eklenir)
            <textarea className="input w-full mt-1" rows={2} value={form.policy_text}
                      onChange={(e) => setForm({ ...form, policy_text: e.target.value })} />
          </label>
          <label className="text-xs">Zorunlu uyarı (yanıtın sonuna eklenir)
            <textarea className="input w-full mt-1" rows={2} value={form.required_notice}
                      onChange={(e) => setForm({ ...form, required_notice: e.target.value })} />
          </label>
          <label className="text-xs">Red mesajı (engellendiğinde gösterilir)
            <textarea className="input w-full mt-1" rows={2} value={form.refusal_message}
                      onChange={(e) => setForm({ ...form, refusal_message: e.target.value })} />
          </label>
        </div>

        <div className="mt-3">
          <div className="text-xs text-[var(--text-dim)] mb-1">
            Geçerli kapsamlar (hiçbiri seçilmezse <b>tüm</b> kapsamlarda geçerli)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {scopes.map((s) => {
              const on = form.scopes.includes(s.key);
              return (
                <button key={s.key} type="button"
                        onClick={() => setForm({
                          ...form,
                          scopes: on ? form.scopes.filter((x) => x !== s.key) : [...form.scopes, s.key],
                        })}
                        className={`px-2 py-1 rounded text-[11px] ${on ? "bg-[var(--primary)] text-black" : "bg-[var(--surface-2)] text-[var(--text-dim)]"}`}>
                  {s.key}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center gap-3 mt-3">
          <label className="text-xs flex items-center gap-2">
            <input type="checkbox" checked={form.is_regex}
                   onChange={(e) => setForm({ ...form, is_regex: e.target.checked })} />
            İfadeler regex olarak yorumlansın
          </label>
          <button className="btn btn-primary text-xs" onClick={submit} disabled={busy}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} {editing ? "Güncelle" : "Ekle"}
          </button>
          {editing && (
            <button className="btn btn-ghost text-xs" onClick={() => { setEditing(null); setForm(EMPTY_RAIL); }}>
              Vazgeç
            </button>
          )}
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-[var(--text-dim)] uppercase">
            <tr className="border-b border-[var(--border)]">
              <th className="text-left p-3">Kural</th>
              <th className="text-left p-3">Kapsam</th>
              <th className="text-left p-3">Engeller</th>
              <th className="text-left p-3">Durum</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} className="p-5 text-sm text-[var(--text-dim)]">
                Henüz kural yok. "Sistem Promptları" sekmesindeki "Varsayılanları Yükle"
                düğmesi 3 hazır kural ekler.
              </td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-[var(--border)]">
                <td className="p-3">
                  <div className="font-medium">{r.name}</div>
                  <div className="text-xs text-[var(--text-dim)]">{r.description}</div>
                </td>
                <td className="p-3 text-xs">{(r.scopes || []).join(", ") || "tümü"}</td>
                <td className="p-3 text-xs">
                  {(r.blocked_input || []).length > 0 && <div>soru: {(r.blocked_input || []).join(", ")}</div>}
                  {(r.blocked_output || []).length > 0 && <div>yanıt: {(r.blocked_output || []).join(", ")}</div>}
                  {r.required_notice && <div className="text-[var(--text-dim)]">+ zorunlu uyarı</div>}
                </td>
                <td className="p-3">
                  <span className={`badge ${r.is_active ? "badge-a" : "badge-neutral"}`}>
                    {r.is_active ? "Aktif" : "Pasif"}
                  </span>
                </td>
                <td className="p-3 text-right whitespace-nowrap">
                  <button className="btn btn-ghost text-xs" onClick={() => edit(r)}>Düzenle</button>
                  {r.is_active && (
                    <button className="btn btn-ghost text-xs text-red-400" onClick={() => remove(r)}>
                      <Trash2 size={12} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* =====================================================================
   SEKME 3 — BİLGİ BANKASI (RAG)
   ===================================================================== */
function RagTab({ flash }) {
  const [docs, setDocs] = useState([]);
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState(null);
  const fileRef = useRef();

  const load = () => api.get("/ai-governance/rag/documents")
    .then((r) => setDocs(r.data || [])).catch((e) => flash("err", errText(e)));

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const tagList = () => tags.split(",").map((t) => t.trim()).filter(Boolean);

  async function addText() {
    if (!title.trim() || !text.trim()) return flash("err", "Başlık ve metin zorunlu.");
    setBusy(true);
    try {
      const r = await api.post("/ai-governance/rag/documents/text", { title, text, tags: tagList() });
      flash("ok", `"${r.data.title}" eklendi — ${r.data.chunk_count} bölüm, ${r.data.embedded_chunks} vektör.`);
      setTitle(""); setText(""); setTags(""); load();
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  async function upload(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true);
    const fd = new FormData();
    fd.append("file", f);
    fd.append("title", title || f.name);
    fd.append("tags", tags);
    try {
      const r = await api.post("/ai-governance/rag/documents/upload", fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      flash("ok", `"${r.data.title}" yüklendi — ${r.data.chunk_count} bölüm, ${r.data.embedded_chunks} vektör.`);
      setTitle(""); setTags(""); load();
    } catch (err) { flash("err", errText(err)); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  async function remove(d) {
    if (!window.confirm(`"${d.title}" bilgi bankasından silinsin mi? Bölümleri kalıcı olarak silinir.`)) return;
    try { await api.delete(`/ai-governance/rag/documents/${d.id}`); flash("ok", "Belge silindi."); load(); }
    catch (e) { flash("err", errText(e)); }
  }

  async function reindex(d) {
    setBusy(true);
    try {
      const r = await api.post(`/ai-governance/rag/documents/${d.id}/reindex`);
      flash("ok", `${r.data.embedded}/${r.data.chunks} bölüm yeniden vektörlendi.`);
      load();
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  async function search() {
    if (!query.trim()) return;
    setBusy(true);
    try { setPreview((await api.post("/ai-governance/rag/search", { question: query, scope: "chat" })).data); }
    catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="card p-4">
        <div className="font-medium mb-1">Belge Ekle</div>
        <p className="text-xs text-[var(--text-dim)] mb-3">
          Yüklenen içerik parçalara bölünür ve yerel model ile vektörlenir. Bu belgeler
          AI yanıtlarının dayanağı olur — model bunlarla çelişen bilgi üretmemeye zorlanır.
          Desteklenen dosyalar: txt, md, csv, json, yaml (pdf/docx sunucuda ilgili
          kütüphane kuruluysa).
        </p>
        <div className="grid md:grid-cols-2 gap-3 mb-3">
          <label className="text-xs">Başlık
            <input className="input w-full mt-1" value={title}
                   onChange={(e) => setTitle(e.target.value)} placeholder="Örn. Sulama Politikası 2026" />
          </label>
          <label className="text-xs">Etiketler (virgülle — getirmeyi daraltmak için)
            <input className="input w-full mt-1" value={tags}
                   onChange={(e) => setTags(e.target.value)} placeholder="sulama, politika" />
          </label>
        </div>
        <textarea className="input w-full text-xs" rows={5} value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Metni buraya yapıştırın veya aşağıdan dosya yükleyin…" />
        <div className="flex items-center gap-2 mt-3 flex-wrap">
          <button className="btn btn-primary text-xs" onClick={addText} disabled={busy}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Metni Ekle
          </button>
          <input ref={fileRef} type="file" className="hidden" onChange={upload}
                 accept=".txt,.md,.csv,.json,.yaml,.yml,.log,.pdf,.docx" />
          <button className="btn btn-ghost text-xs" onClick={() => fileRef.current?.click()} disabled={busy}>
            <Upload size={14} /> Dosya Yükle
          </button>
        </div>
      </div>

      <div className="card p-4">
        <div className="font-medium mb-2">Getirmeyi Dene (model çalıştırmaz)</div>
        <div className="flex gap-2 flex-wrap">
          <input className="input flex-1 min-w-[240px]" value={query}
                 onChange={(e) => setQuery(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && search()}
                 placeholder="Örn. hasattan önce sulama ne zaman kesilir" />
          <button className="btn btn-ghost text-xs" onClick={search} disabled={busy}>Ara</button>
        </div>
        {preview && (
          <div className="mt-3">
            <span className={`badge ${RAG_MODE_LABEL[preview.rag_mode]?.cls || "badge-neutral"}`}>
              {RAG_MODE_LABEL[preview.rag_mode]?.label || preview.rag_mode}
            </span>
            <div className="mt-2 flex flex-col gap-2">
              {(preview.sources || []).map((s, i) => (
                <div key={i} className="text-xs bg-[var(--surface-2)] rounded p-2">
                  <div className="text-[var(--text-dim)] mb-1">
                    {s.document_title} · bölüm {s.chunk_index} · skor {s.score}
                  </div>
                  {s.excerpt}…
                </div>
              ))}
              {(preview.sources || []).length === 0 && (
                <div className="text-xs text-[var(--text-dim)]">Eşleşen kaynak bulunamadı.</div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-[var(--text-dim)] uppercase">
            <tr className="border-b border-[var(--border)]">
              <th className="text-left p-3">Belge</th>
              <th className="text-left p-3">Etiket</th>
              <th className="text-left p-3">Bölüm</th>
              <th className="text-left p-3">İndeks</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {docs.length === 0 && (
              <tr><td colSpan={5} className="p-5 text-sm text-[var(--text-dim)]">
                Bilgi bankası boş. Yukarıdan bir belge ekleyin.
              </td></tr>
            )}
            {docs.map((d) => (
              <tr key={d.id} className="border-b border-[var(--border)]">
                <td className="p-3">
                  <div className="font-medium flex items-center gap-2">
                    <FileText size={14} /> {d.title}
                  </div>
                  <div className="text-xs text-[var(--text-dim)]">
                    {d.source} · {d.char_count} karakter · {d.created_by}
                  </div>
                </td>
                <td className="p-3 text-xs">{(d.tags || []).join(", ") || "—"}</td>
                <td className="p-3 text-xs">{d.embedded_chunks}/{d.chunk_count} vektörlü</td>
                <td className="p-3">
                  <span className={`badge ${d.index_mode === "embedding" ? "badge-a" : "badge-c"}`}>
                    {d.index_mode === "embedding" ? "Anlamsal" : "Anahtar kelime"}
                  </span>
                </td>
                <td className="p-3 text-right whitespace-nowrap">
                  {d.is_active && (
                    <>
                      <button className="btn btn-ghost text-xs" onClick={() => reindex(d)} disabled={busy}>
                        <RefreshCw size={12} /> Yeniden İndeksle
                      </button>
                      <button className="btn btn-ghost text-xs text-red-400" onClick={() => remove(d)}>
                        <Trash2 size={12} />
                      </button>
                    </>
                  )}
                  {!d.is_active && <span className="badge badge-neutral">Silindi</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* =====================================================================
   SEKME 4 — TEST KONSOLU
   ===================================================================== */
function TestTab({ flash }) {
  const [scopes, setScopes] = useState([]);
  const [scope, setScope] = useState("chat");
  const [question, setQuestion] = useState("");
  const [useRag, setUseRag] = useState(true);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    api.get("/ai-governance/scopes").then((r) => setScopes(r.data || [])).catch(() => {});
    api.get("/ai-governance/logs", { params: { limit: 20 } })
      .then((r) => setLogs(r.data || [])).catch(() => {});
  }, []);

  async function run() {
    if (!question.trim()) return;
    setBusy(true); setRes(null);
    try {
      const r = await api.post("/ai-governance/test", { scope, question, use_rag: useRag });
      setRes(r.data);
      api.get("/ai-governance/logs", { params: { limit: 20 } })
        .then((x) => setLogs(x.data || [])).catch(() => {});
    } catch (e) { flash("err", errText(e)); } finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="card p-4">
        <p className="text-xs text-[var(--text-dim)] mb-3">
          Buradaki çağrı, canlı AI çağrılarıyla <b>birebir aynı</b> yoldan geçer:
          prompt birleştirme → bilgi bankası getirme → girdi kuralı → model → çıktı kuralı.
          Yayına almadan önce kuralları burada doğrulayın.
        </p>
        <div className="flex gap-2 flex-wrap items-center mb-2">
          <select className="input w-auto" value={scope} onChange={(e) => setScope(e.target.value)}>
            {scopes.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
          <label className="text-xs flex items-center gap-2">
            <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />
            Bilgi bankasını kullan
          </label>
        </div>
        <textarea className="input w-full" rows={3} value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Soruyu yazın…" />
        <button className="btn btn-primary text-xs mt-3" onClick={run} disabled={busy}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <TerminalSquare size={14} />} Çalıştır
        </button>
      </div>

      {res && (
        <div className="card p-4">
          <div className="flex items-center gap-2 flex-wrap mb-3">
            {res.blocked
              ? <span className="badge badge-d">Engellendi: {res.blocked_by} ("{res.matched}")</span>
              : <span className="badge badge-a">İzin verildi</span>}
            <span className={`badge ${RAG_MODE_LABEL[res.rag_mode]?.cls || "badge-neutral"}`}>
              {RAG_MODE_LABEL[res.rag_mode]?.label || res.rag_mode}
            </span>
            <span className="badge badge-neutral">
              {res.ai_powered ? `model: ${res.routed_as || "?"}` : "model çalışmadı"}
            </span>
          </div>
          {res.error && <div className="text-xs text-red-400 mb-2">Hata: {res.error}</div>}
          <div className="whitespace-pre-wrap text-sm">{res.answer || "—"}</div>
          {(res.sources || []).length > 0 && (
            <div className="mt-3 pt-3 border-t border-[var(--border)]">
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Kullanılan Kaynaklar</div>
              {res.sources.map((s, i) => (
                <div key={i} className="text-xs text-[var(--text-dim)]">
                  • {s.document_title} — bölüm {s.chunk_index} (skor {s.score})
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="card overflow-x-auto">
        <div className="p-3 text-xs text-[var(--text-dim)] uppercase tracking-wider">Son AI Çağrıları (denetim izi)</div>
        <table className="w-full text-sm">
          <thead className="text-xs text-[var(--text-dim)] uppercase">
            <tr className="border-b border-[var(--border)]">
              <th className="text-left p-3">Tarih</th>
              <th className="text-left p-3">Kapsam</th>
              <th className="text-left p-3">Soru</th>
              <th className="text-left p-3">Sonuç</th>
              <th className="text-left p-3">Süre</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-b border-[var(--border)]">
                <td className="p-3 text-xs whitespace-nowrap">
                  {new Date(l.created_at).toLocaleString("tr-TR")}
                </td>
                <td className="p-3 text-xs">{l.scope}</td>
                <td className="p-3 text-xs max-w-[320px] truncate" title={l.question}>{l.question}</td>
                <td className="p-3">
                  {l.blocked
                    ? <span className="badge badge-d">Engellendi</span>
                    : <span className="badge badge-a">Yanıtlandı</span>}
                  <span className="text-xs text-[var(--text-dim)] ml-2">{l.source_count} kaynak</span>
                </td>
                <td className="p-3 text-xs">{l.duration_ms} ms</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr><td colSpan={5} className="p-5 text-sm text-[var(--text-dim)]">Henüz kayıt yok.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
