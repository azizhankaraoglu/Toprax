/**
 * ŞABLON YÖNETİMİ (IT-25 / FAZ 9 — Communication Hub)
 *
 * Ayarlar altında admin tanımlı, kanal başına (SMS/E-Posta/WhatsApp/Push/
 * Sesli Arama) mesaj şablonu kataloğu. Kod gerektirmez — burada tanımlanan
 * şablonlar, kişi kartlarındaki İletişim sekmesinde (CommunicationTab.jsx)
 * otomatik seçenek olarak belirir. `subject`/`body` her güncellemede yeni
 * bir sürüm açar (backend `templates.version` + `template_versions`).
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import { MessagesSquare } from "lucide-react";

export function SablonYonetimi() {
  const [templates, setTemplates] = useState([]);
  const [channels, setChannels] = useState([]);
  const [variables, setVariables] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  const load = () => api.get("/templates", { params: { include_inactive: true } }).then((r) => setTemplates(r.data));

  useEffect(() => {
    load();
    api.get("/channels").then((r) => setChannels(r.data));
    api.get("/templates/variables").then((r) => setVariables(r.data));
  }, []);

  const channelLabel = (key) => channels.find((c) => c.key === key)?.label || key;

  function startEdit(t) {
    setEditingId(t.id);
    setEditForm({ name: t.name, subject: t.subject || "", body: t.body });
  }

  async function saveEdit(id) {
    await api.put(`/templates/${id}`, editForm);
    setEditingId(null);
    load();
  }

  async function toggleActive(t) {
    await api.put(`/templates/${t.id}`, { is_active: !t.is_active });
    load();
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="template-management-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">İLETİŞİM MERKEZİ — AYARLAR</div>
        <h1 className="font-display text-4xl">Şablon Yönetimi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Her kanal için ayrı mesaj şablonu tanımlayın. Dinamik alanlar: {variables.map((v) => `{{${v}}}`).join(", ")}.
          Şablon içeriği değiştirildiğinde eski sürüm otomatik saklanır.
        </p>
      </header>

      <QuickAddPanel
        title="Yeni Şablon"
        testId="template-add"
        fields={[
          { name: "name", label: "Ad", required: true },
          { name: "channel", label: "Kanal", type: "select", required: true,
            options: channels.map((c) => ({ value: c.key, label: c.label })) },
          { name: "subject", label: "Konu (sadece E-Posta)" },
          { name: "body", label: "İçerik", type: "textarea", required: true, span2: true, rows: 4 },
        ]}
        onSubmit={async (v) => {
          await api.post("/templates", { ...v, subject: v.subject || null });
          load();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Ad</th><th className="p-4">Kanal</th><th className="p-4">Sürüm</th>
            <th className="p-4">İçerik</th><th className="p-4">Durum</th><th className="p-4"></th>
          </tr></thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)] align-top">
                {editingId === t.id ? (
                  <td colSpan="6" className="p-4">
                    <div className="space-y-2">
                      <input className="input" value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} />
                      {t.channel === "email" && (
                        <input className="input" placeholder="Konu" value={editForm.subject}
                               onChange={(e) => setEditForm((f) => ({ ...f, subject: e.target.value }))} />
                      )}
                      <textarea className="input" rows={4} value={editForm.body}
                                onChange={(e) => setEditForm((f) => ({ ...f, body: e.target.value }))} />
                      <div className="flex gap-2">
                        <button onClick={() => saveEdit(t.id)} className="btn btn-primary text-sm">Kaydet</button>
                        <button onClick={() => setEditingId(null)} className="btn btn-ghost text-sm">Vazgeç</button>
                      </div>
                    </div>
                  </td>
                ) : (
                  <>
                    <td className="p-4 flex items-center gap-2"><MessagesSquare size={14} className="text-[var(--primary)]"/>{t.name}</td>
                    <td className="p-4 text-[var(--text-dim)]">{channelLabel(t.channel)}</td>
                    <td className="p-4 font-mono text-xs">v{t.version}</td>
                    <td className="p-4 text-xs text-[var(--text-dim)] max-w-[280px] truncate">{t.body}</td>
                    <td className="p-4">
                      <button onClick={() => toggleActive(t)} className={`badge ${t.is_active === false ? "badge-d" : "badge-a"}`}>
                        {t.is_active === false ? "Pasif" : "Aktif"}
                      </button>
                    </td>
                    <td className="p-4">
                      <button onClick={() => startEdit(t)} className="btn btn-ghost text-xs">Düzenle</button>
                    </td>
                  </>
                )}
              </tr>
            ))}
            {templates.length === 0 && (
              <tr><td colSpan="6" className="p-6 text-center text-[var(--text-dim)]">Henüz şablon yok</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
