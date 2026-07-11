/**
 * BİZE ULAŞIN / CASE YÖNETİMİ (IT-28 / FAZ 9 devam)
 *
 * SupportRequest (IT-18) ile KARIŞTIRILMAMALI — Case genel bir konu/talep
 * kaydıdır (şikayet/öneri/hastalık bildirimi/teknik destek/...). İki yönlü
 * mesajlaşma + field_ops.py'ye (Task) köprü + kişi kartı timeline entegrasyonu
 * (communications.py'nin /contacts/{id}/timeline'ı case'leri de döndürür).
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { Inbox, Plus, Send, ListChecks, UserCog } from "lucide-react";

const STATUS_LABELS = {
  yeni: "Yeni", atandi: "Atandı", inceleniyor: "İnceleniyor",
  bilgi_bekleniyor: "Bilgi Bekleniyor", cevaplandi: "Cevaplandı",
  cozuldu: "Çözüldü", kapatildi: "Kapatıldı", iptal_edildi: "İptal Edildi",
};
const NEXT_STATUS = {
  yeni: ["atandi", "iptal_edildi"],
  atandi: ["inceleniyor", "iptal_edildi"],
  inceleniyor: ["bilgi_bekleniyor", "cevaplandi", "iptal_edildi"],
  bilgi_bekleniyor: ["cevaplandi", "inceleniyor", "iptal_edildi"],
  cevaplandi: ["inceleniyor", "cozuldu", "iptal_edildi"],
  cozuldu: ["kapatildi", "inceleniyor"],
  kapatildi: [], iptal_edildi: [],
};

export default function CaseManagement() {
  const [cases, setCases] = useState([]);
  const [categories, setCategories] = useState([]);
  const [users, setUsers] = useState([]);
  const [taskTypes, setTaskTypes] = useState([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [form, setForm] = useState({ subject: "", category_id: "", description: "", priority: "orta" });
  const [selected, setSelected] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState("");
  const [assignTo, setAssignTo] = useState("");
  const [taskForm, setTaskForm] = useState({ task_type_id: "", assigned_to: "" });
  const [error, setError] = useState("");

  function loadCases() {
    const params = statusFilter ? { status: statusFilter } : {};
    api.get("/cases", { params }).then((r) => setCases(r.data));
  }
  useEffect(() => { loadCases(); }, [statusFilter]);
  useEffect(() => {
    api.get("/case-categories").then((r) => setCategories(r.data));
    api.get("/users").then((r) => setUsers(r.data)).catch(() => {});
    api.get("/task-types").then((r) => setTaskTypes(r.data)).catch(() => {});
  }, []);

  async function seedCategories() {
    await api.post("/case-categories/seed-defaults");
    api.get("/case-categories").then((r) => setCategories(r.data));
  }

  async function submitCase(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/cases", form);
      setForm({ subject: "", category_id: "", description: "", priority: "orta" });
      loadCases();
    } catch (err) { setError(err.response?.data?.detail || "Case oluşturulamadı"); }
  }

  async function openCase(c) {
    setSelected(c);
    setTaskForm({ task_type_id: "", assigned_to: c.assigned_to || "" });
    const r = await api.get(`/cases/${c.id}/messages`);
    setMessages(r.data);
  }

  async function transition(status) {
    setError("");
    try {
      const r = await api.put(`/cases/${selected.id}/transition`, { status });
      setSelected(r.data);
      loadCases();
    } catch (err) { setError(err.response?.data?.detail || "Durum değiştirilemedi"); }
  }

  async function assign() {
    setError("");
    try {
      const r = await api.put(`/cases/${selected.id}/assign`, { assigned_to: assignTo });
      if (r.data.status === "onay_bekliyor") {
        setError("Atama onay zincirine düştü — 'Onay Bekleyenlerim' ekranından karar bekleniyor.");
      } else {
        setSelected(r.data);
      }
      loadCases();
    } catch (err) { setError(err.response?.data?.detail || "Atama yapılamadı"); }
  }

  async function sendMessage() {
    if (!newMessage.trim()) return;
    const r = await api.post(`/cases/${selected.id}/messages`, { message: newMessage, attachments: [] });
    setMessages((m) => [...m, r.data]);
    setNewMessage("");
    loadCases();
  }

  async function createTask() {
    setError("");
    try {
      await api.post(`/cases/${selected.id}/create-task`, taskForm);
      setError("");
      alert("Görev oluşturuldu (Saha Operasyonları > Görev Yönetimi'nden görülebilir).");
    } catch (err) { setError(err.response?.data?.detail || "Görev oluşturulamadı"); }
  }

  const categoryName = (id) => categories.find((c) => c.id === id)?.name || id;

  return (
    <div className="p-8 max-w-[1500px] flex gap-6" data-testid="case-management-page">
      <div className="flex-1 min-w-0">
        <header className="mb-6">
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">İLETİŞİM MERKEZİ</div>
          <h1 className="font-display text-4xl">Bize Ulaşın (Case Yönetimi)</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Şikayet, öneri, hastalık/zararlı bildirimi, teknik destek gibi tüm konular tek modelde.
          </p>
        </header>

        {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

        {categories.length === 0 && (
          <button onClick={seedCategories} className="btn btn-ghost text-xs mb-4">Varsayılan Kategorileri Yükle</button>
        )}

        <form onSubmit={submitCase} className="card p-5 mb-6 space-y-3" data-testid="case-form">
          <h3 className="font-display text-lg flex items-center gap-2"><Plus size={16} className="text-[var(--primary)]" />Yeni Case</h3>
          <div className="grid grid-cols-3 gap-3">
            <input className="input" placeholder="Konu" required
                   value={form.subject} onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))} />
            <select className="input" required value={form.category_id}
                    onChange={(e) => setForm((f) => ({ ...f, category_id: e.target.value }))}>
              <option value="">Kategori seç...</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select className="input" value={form.priority} onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}>
              <option value="dusuk">Düşük</option><option value="orta">Orta</option><option value="yuksek">Yüksek</option>
            </select>
          </div>
          <textarea className="input w-full" rows={2} placeholder="Açıklama"
                    value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} />
          <button type="submit" className="btn btn-primary text-sm">Oluştur</button>
        </form>

        <div className="flex gap-2 mb-3">
          {["", "yeni", "atandi", "inceleniyor", "bilgi_bekleniyor", "cevaplandi", "cozuldu", "kapatildi"].map((s) => (
            <button key={s} onClick={() => setStatusFilter(s)}
                    className={`btn text-xs ${statusFilter === s ? "btn-primary" : "btn-ghost"}`}>
              {s === "" ? "Tümü" : STATUS_LABELS[s]}
            </button>
          ))}
        </div>

        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-4">Konu</th><th className="p-4">Kategori</th><th className="p-4">Öncelik</th><th className="p-4">Durum</th>
            </tr></thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} onClick={() => openCase(c)}
                    className={`border-b border-[var(--border)] hover:bg-[var(--surface-2)] cursor-pointer ${selected?.id === c.id ? "bg-[var(--surface-2)]" : ""}`}
                    data-testid={`case-row-${c.id}`}>
                  <td className="p-4">{c.subject}</td>
                  <td className="p-4 text-xs text-[var(--text-dim)]">{categoryName(c.category_id)}</td>
                  <td className="p-4 text-xs">{c.priority}</td>
                  <td className="p-4"><span className="badge badge-neutral">{STATUS_LABELS[c.status] || c.status}</span></td>
                </tr>
              ))}
              {cases.length === 0 && (
                <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Case bulunamadı</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected && (
        <div className="w-[380px] shrink-0 card p-4 h-fit sticky top-4" data-testid="case-detail-panel">
          <h3 className="font-display text-lg mb-1">{selected.subject}</h3>
          <div className="text-xs text-[var(--text-dim)] mb-3">{STATUS_LABELS[selected.status]}</div>

          <div className="mb-3">
            <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider mb-1">Durum Değiştir</div>
            <div className="flex flex-wrap gap-1.5">
              {(NEXT_STATUS[selected.status] || []).map((s) => (
                <button key={s} onClick={() => transition(s)} className="btn btn-ghost text-[11px]">{STATUS_LABELS[s]}</button>
              ))}
            </div>
          </div>

          <div className="mb-3 flex items-center gap-2">
            <UserCog size={13} className="text-[var(--text-dim)]" />
            <select className="input text-xs flex-1" value={assignTo} onChange={(e) => setAssignTo(e.target.value)}>
              <option value="">Kullanıcı seç...</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.email}</option>)}
            </select>
            <button onClick={assign} className="btn btn-ghost text-xs">Ata</button>
          </div>

          <div className="mb-3 p-2 rounded bg-[var(--surface-2)]">
            <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider mb-1 flex items-center gap-1">
              <ListChecks size={12} /> Saha Görevi Oluştur
            </div>
            <select className="input text-xs w-full mb-1" value={taskForm.task_type_id}
                    onChange={(e) => setTaskForm((f) => ({ ...f, task_type_id: e.target.value }))}>
              <option value="">Görev tipi seç...</option>
              {taskTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <select className="input text-xs w-full mb-1" value={taskForm.assigned_to}
                    onChange={(e) => setTaskForm((f) => ({ ...f, assigned_to: e.target.value }))}>
              <option value="">Atanacak personel...</option>
              {users.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.email}</option>)}
            </select>
            <button onClick={createTask} disabled={!taskForm.task_type_id || !taskForm.assigned_to} className="btn btn-primary text-xs w-full justify-center disabled:opacity-30">
              Görev Oluştur
            </button>
          </div>

          <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider mb-1 flex items-center gap-1"><Inbox size={12} /> Mesajlaşma</div>
          <div className="max-h-64 overflow-y-auto space-y-2 mb-2">
            {messages.map((m) => (
              <div key={m.id} className={`text-xs p-2 rounded ${m.sender_type === "farmer" ? "bg-[var(--primary)]/10" : "bg-[var(--surface-2)]"}`}>
                <div className="font-medium">{m.sender_name}</div>
                <div>{m.message}</div>
              </div>
            ))}
            {messages.length === 0 && <div className="text-xs text-[var(--text-dim)]">Henüz mesaj yok</div>}
          </div>
          <div className="flex gap-2">
            <input className="input text-xs flex-1" placeholder="Yanıt yaz..." value={newMessage}
                   onChange={(e) => setNewMessage(e.target.value)} onKeyDown={(e) => e.key === "Enter" && sendMessage()} />
            <button onClick={sendMessage} className="btn btn-primary text-xs"><Send size={12} /></button>
          </div>
        </div>
      )}
    </div>
  );
}
