/**
 * BİLDİRİM DETAYI (SON HAL #8) — route /bildirimler/:id
 *
 * "Bildirime tıklandığında detaylarını gösterecek bildirim sayfasına
 * yönlendir" talebi: WorkspaceDrawer.jsx'teki (sol menü altındaki zil)
 * ve Bildirimler (Other.jsx) listesindeki her satır artık buraya gider.
 * Yeni bir bildirim şeması İCAT EDİLMEDİ — mevcut `notifications`
 * dokümanının TÜM alanları (title/message/channel/status/type/created_at
 * + varsa farmer_id/form_id gibi ilişkili kayıt referansları) okunur.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/api";
import { ArrowLeft, Bell, CheckCheck } from "lucide-react";
import { moduleDetailPath } from "@/lib/moduleRoutes";

const CHANNEL_BADGE = { sms: "badge-b", whatsapp: "badge-a", push: "badge-c", in_app: "badge-neutral" };

// Bildirim dokümanında görülebilen, bilinen "ilişkili kayıt" alanları —
// bulunursa ilgili modülün detay sayfasına bir kısayol gösterilir.
const RELATED_LINKS = [
  { key: "farmer_id", module: "farmers", label: "Çiftçi Kaydı" },
  { key: "parcel_id", module: "parcels", label: "Parsel Kaydı" },
  { key: "contract_id", module: "contracts", label: "Sözleşme Kaydı" },
];

export default function NotificationDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [notif, setNotif] = useState(null);
  const [error, setError] = useState("");

  const load = () => api.get(`/notifications/${id}`).then((r) => setNotif(r.data)).catch((err) => {
    setError(err.response?.data?.detail || "Bildirim bulunamadı.");
  });
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function markRead() {
    await api.put(`/notifications/${id}/read`);
    load();
  }

  if (error) {
    return (
      <div className="p-8 max-w-[800px]" data-testid="notification-detail-page">
        <button onClick={() => nav("/bildirimler")} className="btn btn-ghost text-xs mb-4"><ArrowLeft size={13} /> Bildirimlere Dön</button>
        <div className="card p-6 text-sm text-red-400">{error}</div>
      </div>
    );
  }

  if (!notif) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const relatedLinks = RELATED_LINKS
    .filter((r) => notif[r.key])
    .map((r) => ({ ...r, path: moduleDetailPath(r.module, { id: notif[r.key] }) }))
    .filter((r) => r.path);

  return (
    <div className="p-8 max-w-[800px]" data-testid="notification-detail-page">
      <button onClick={() => nav("/bildirimler")} className="btn btn-ghost text-xs mb-4"><ArrowLeft size={13} /> Bildirimlere Dön</button>

      <div className="card p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-[var(--primary)]/10 flex items-center justify-center shrink-0">
              <Bell size={18} className="text-[var(--primary)]" />
            </div>
            <div>
              <h1 className="font-display text-2xl">{notif.title}</h1>
              <div className="text-xs text-[var(--text-dim)] mt-0.5">{new Date(notif.created_at).toLocaleString("tr-TR")}</div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className={`badge ${CHANNEL_BADGE[notif.channel] || "badge-neutral"}`}>{notif.channel || "in_app"}</span>
            <span className={`badge ${notif.status === "okundu" ? "badge-a" : "badge-c"}`}>{notif.status}</span>
          </div>
        </div>

        <p className="text-sm leading-relaxed break-words whitespace-pre-wrap">{notif.message}</p>

        {notif.status !== "okundu" && (
          <button onClick={markRead} className="btn btn-primary text-xs mt-4" data-testid="notif-detail-mark-read">
            <CheckCheck size={13} /> Okundu İşaretle
          </button>
        )}

        {relatedLinks.length > 0 && (
          <div className="mt-6 pt-4 border-t border-[var(--border)]">
            <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">İlgili Kayıtlar</div>
            <div className="flex flex-wrap gap-2">
              {relatedLinks.map((r) => (
                <button key={r.key} onClick={() => nav(r.path)} className="btn text-xs">{r.label}</button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-[var(--border)] text-[11px] text-[var(--text-dim)] font-mono">
          Tip: {notif.type || "—"}
        </div>
      </div>
    </div>
  );
}
