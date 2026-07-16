/**
 * DUYURU YÖNETİMİ
 *
 * Yöneticinin tüm kullanıcılara (personel + çiftçi) yayınladığı, açılış
 * popup'ında (AnnouncementPopup.jsx) gösterilen ve Bildirimler
 * çekmecesinin "Duyurular" sekmesinde (WorkspaceDrawer.jsx) geçmişe
 * dönük görülebilen duyuruları oluşturur/düzenler/pasifleştirir.
 * TemplateManagement.jsx (Şablon Yönetimi) ile AYNI liste+QuickAddPanel
 * kalıbı — yeni bir UI deseni icat edilmedi.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import { Megaphone } from "lucide-react";

const PRIORITY_LABELS = { normal: "Normal", onemli: "Önemli", kritik: "Kritik" };
const PRIORITY_BADGE = { normal: "badge-neutral", onemli: "badge-c", kritik: "badge-d" };

export default function AnnouncementManagement() {
  const [announcements, setAnnouncements] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});

  const load = () => api.get("/announcements").then((r) => setAnnouncements(r.data));

  useEffect(() => { load(); }, []);

  function startEdit(a) {
    setEditingId(a.id);
    setEditForm({ title: a.title, body: a.body, priority: a.priority });
  }

  async function saveEdit(id) {
    await api.put(`/announcements/${id}`, editForm);
    setEditingId(null);
    load();
  }

  async function toggleActive(a) {
    await api.put(`/announcements/${a.id}`, { is_active: !a.is_active });
    load();
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="announcement-management-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SİSTEM</div>
        <h1 className="font-display text-4xl">Duyuru Yönetimi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Yayınladığınız duyuru, ilgili kullanıcı bir sonraki girişinde (veya panele girdiğinde)
          popup olarak görür; "Okudum" dedikten sonra bir daha o kullanıcıya çıkmaz. Çiftçi portalı
          dahil TÜM kullanıcılara gösterilir.
        </p>
      </header>

      <QuickAddPanel
        title="Yeni Duyuru"
        testId="announcement-add"
        fields={[
          { name: "title", label: "Başlık", required: true },
          { name: "priority", label: "Öncelik", type: "select", required: true, default: "normal",
            options: Object.entries(PRIORITY_LABELS).map(([value, label]) => ({ value, label })) },
          { name: "body", label: "İçerik", type: "textarea", required: true, span2: true, rows: 4 },
        ]}
        onSubmit={async (v) => {
          await api.post("/announcements", v);
          load();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Başlık</th><th className="p-4">Öncelik</th>
            <th className="p-4">İçerik</th><th className="p-4">Yayınlayan</th>
            <th className="p-4">Durum</th><th className="p-4"></th>
          </tr></thead>
          <tbody>
            {announcements.map((a) => (
              <tr key={a.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)] align-top">
                {editingId === a.id ? (
                  <td colSpan="6" className="p-4">
                    <div className="space-y-2">
                      <input className="input" value={editForm.title} onChange={(e) => setEditForm((f) => ({ ...f, title: e.target.value }))} />
                      <select className="input" value={editForm.priority} onChange={(e) => setEditForm((f) => ({ ...f, priority: e.target.value }))}>
                        {Object.entries(PRIORITY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                      <textarea className="input" rows={4} value={editForm.body}
                                onChange={(e) => setEditForm((f) => ({ ...f, body: e.target.value }))} />
                      <div className="flex gap-2">
                        <button onClick={() => saveEdit(a.id)} className="btn btn-primary text-sm">Kaydet</button>
                        <button onClick={() => setEditingId(null)} className="btn btn-ghost text-sm">Vazgeç</button>
                      </div>
                    </div>
                  </td>
                ) : (
                  <>
                    <td className="p-4 flex items-center gap-2"><Megaphone size={14} className="text-[var(--primary)]"/>{a.title}</td>
                    <td className="p-4"><span className={`badge ${PRIORITY_BADGE[a.priority] || "badge-neutral"}`}>{PRIORITY_LABELS[a.priority] || a.priority}</span></td>
                    <td className="p-4 text-xs text-[var(--text-dim)] max-w-[320px] truncate">{a.body}</td>
                    <td className="p-4 text-xs text-[var(--text-dim)]">{a.created_by}</td>
                    <td className="p-4">
                      <button onClick={() => toggleActive(a)} className={`badge ${a.is_active === false ? "badge-d" : "badge-a"}`}>
                        {a.is_active === false ? "Pasif" : "Aktif"}
                      </button>
                    </td>
                    <td className="p-4">
                      <button onClick={() => startEdit(a)} className="btn btn-ghost text-xs">Düzenle</button>
                    </td>
                  </>
                )}
              </tr>
            ))}
            {announcements.length === 0 && (
              <tr><td colSpan="6" className="p-6 text-center text-[var(--text-dim)]">Henüz duyuru yok</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
