import { useEffect, useState } from "react";
import api from "@/api";
import { MessageSquare, Mail, MessageCircle, Bell, Phone, Send, History } from "lucide-react";

/**
 * IT-25 — Kişi Kartı İletişim Sekmesi. Çiftçi/personel kartlarına eklenir:
 * kanal seçilir (SMS/E-Posta/WhatsApp/Push/Sesli Arama) → opsiyonel şablon
 * seçilir (seçilirse içerik/konu salt-okunur, gönderim sırasında backend'de
 * {{FarmerName}} vb. değişkenler render edilir) → gönderilir → aşağıdaki
 * timeline'a düşer. VisitHistory.jsx ile AYNI kalıp (contactId/contactType
 * prop'una göre kendi verisini çeker).
 *
 * Kullanım: <CommunicationTab contactType="farmer" contactId={...} contactName={...} />
 */
const CHANNEL_ICONS = { sms: MessageSquare, email: Mail, whatsapp: MessageCircle, push: Bell, voice: Phone };
const STATUS_BADGE = { gonderildi: "badge-b", teslim_edildi: "badge-a", okundu: "badge-a", basarisiz: "badge-d" };
const STATUS_LABELS = { gonderildi: "Gönderildi", teslim_edildi: "Teslim Edildi", okundu: "Okundu", basarisiz: "Başarısız" };

export default function CommunicationTab({ contactType, contactId, contactName }) {
  const [channels, setChannels] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [activeChannel, setActiveChannel] = useState(null);
  const [templateId, setTemplateId] = useState("");
  const [content, setContent] = useState("");
  const [subject, setSubject] = useState("");
  const [recipient, setRecipient] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const loadTimeline = () =>
    api.get(`/contacts/${contactId}/timeline`, { params: { contact_type: contactType } })
      .then((r) => setTimeline(r.data)).catch(() => setTimeline([]));

  useEffect(() => {
    api.get("/channels").then((r) => setChannels(r.data)).catch(() => setChannels([]));
    api.get("/templates").then((r) => setTemplates(r.data)).catch(() => setTemplates([]));
    loadTimeline();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contactId, contactType]);

  function openChannel(key) {
    setActiveChannel(key === activeChannel ? null : key);
    setTemplateId("");
    setContent("");
    setSubject("");
    setRecipient("");
    setError("");
  }

  function pickTemplate(tid) {
    setTemplateId(tid);
    const t = templates.find((x) => x.id === tid);
    setContent(t ? t.body : "");
    setSubject(t ? (t.subject || "") : "");
  }

  async function send() {
    setSending(true);
    setError("");
    try {
      await api.post("/communications/send", {
        channel: activeChannel,
        contact_type: contactType,
        contact_id: contactId,
        template_id: templateId || null,
        content: templateId ? null : content,
        subject: templateId ? null : subject,
        recipient_override: recipient || null,
      });
      setActiveChannel(null);
      loadTimeline();
    } catch (err) {
      setError(err.response?.data?.detail || "Gönderilemedi");
    } finally {
      setSending(false);
    }
  }

  const channelTemplates = templates.filter((t) => t.channel === activeChannel);

  return (
    <div className="space-y-4" data-testid="communication-tab">
      <div className="card p-5">
        <h3 className="font-display text-lg mb-4">İletişim Gönder</h3>
        <div className="flex flex-wrap gap-2 mb-4">
          {channels.map((c) => {
            const Icon = CHANNEL_ICONS[c.key] || Send;
            return (
              <button key={c.key} onClick={() => openChannel(c.key)}
                      className={`btn text-sm flex items-center gap-1.5 ${activeChannel === c.key ? "btn-primary" : "btn-ghost"}`}
                      data-testid={`comm-channel-${c.key}`}>
                <Icon size={14}/> {c.label}
              </button>
            );
          })}
        </div>

        {activeChannel && (
          <div className="bg-[var(--surface-2)] rounded-lg p-4 space-y-3" data-testid="comm-send-form">
            {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded">{error}</div>}
            <div>
              <label className="text-xs text-[var(--text-dim)] mb-1 block">Şablon (opsiyonel)</label>
              <select className="input" value={templateId} onChange={(e) => pickTemplate(e.target.value)}>
                <option value="">Serbest metin</option>
                {channelTemplates.map((t) => <option key={t.id} value={t.id}>{t.name} (v{t.version})</option>)}
              </select>
            </div>
            {activeChannel === "email" && (
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1 block">Konu</label>
                <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} disabled={!!templateId} />
              </div>
            )}
            <div>
              <label className="text-xs text-[var(--text-dim)] mb-1 block">İçerik</label>
              <textarea className="input" rows={3} value={content} onChange={(e) => setContent(e.target.value)} disabled={!!templateId} />
              {templateId && (
                <div className="text-[10px] text-[var(--text-dim)] mt-1">
                  Şablon içeriği kullanılıyor — gönderim sırasında {"{{FarmerName}}"} vb. değişkenler otomatik doldurulur.
                </div>
              )}
            </div>
            <div>
              <label className="text-xs text-[var(--text-dim)] mb-1 block">Alıcı (boş bırakılırsa kayıttaki numara/adres kullanılır)</label>
              <input className="input" value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder={contactName} />
            </div>
            <div className="flex gap-2">
              <button onClick={send} disabled={sending || (!templateId && !content)} className="btn btn-primary text-sm" data-testid="comm-send-submit">
                {sending ? "Gönderiliyor…" : "Gönder"}
              </button>
              <button onClick={() => setActiveChannel(null)} className="btn btn-ghost text-sm">Vazgeç</button>
            </div>
          </div>
        )}
      </div>

      <div className="card p-5">
        <h3 className="font-display text-lg mb-4 flex items-center gap-2"><History size={16} className="text-[var(--primary)]"/>İletişim Geçmişi ({timeline.length})</h3>
        <div className="space-y-2">
          {timeline.map((c) => {
            const Icon = CHANNEL_ICONS[c.channel] || Send;
            return (
              <div key={c.id} className="p-3 bg-[var(--surface-2)] rounded-lg text-sm">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-medium"><Icon size={13}/> {c.template_name || "Serbest metin"}</div>
                  <span className={`badge ${STATUS_BADGE[c.status] || "badge-neutral"}`}>{STATUS_LABELS[c.status] || c.status}</span>
                </div>
                {c.subject && <div className="text-xs text-[var(--text-dim)] mt-1">Konu: {c.subject}</div>}
                <div className="text-xs text-[var(--text-dim)] mt-1">{c.content}</div>
                <div className="text-[10px] text-[var(--text-dim)] mt-1.5 flex gap-3">
                  <span>{c.sent_by}</span>
                  <span>{(c.sent_at || "").slice(0, 16).replace("T", " ")}</span>
                  {c.recipient && <span>→ {c.recipient}</span>}
                </div>
              </div>
            );
          })}
          {timeline.length === 0 && <div className="text-center text-[var(--text-dim)] py-6 text-sm">Henüz iletişim kaydı yok</div>}
        </div>
      </div>
    </div>
  );
}
