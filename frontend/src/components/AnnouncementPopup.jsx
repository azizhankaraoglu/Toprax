import { useEffect, useState } from "react";
import api from "@/api";
import { Megaphone, X, AlertTriangle } from "lucide-react";

/**
 * Açılışta gösterilen duyuru popup'ı — backend/announcements.py'nin
 * `GET /announcements/active` (unread_only=true, varsayılan) ucundan
 * o kullanıcının henüz OKUMADIĞI aktif duyuruları çeker. Birden fazla
 * varsa sırayla (en yeni önce) gösterir, "Okudum" her birini
 * `POST /announcements/{id}/read` ile işaretleyip bir sonrakine geçer.
 * Kuyruk boşsa hiçbir şey render ETMEZ (sessiz no-op) — WorkspaceDrawer.jsx'in
 * "Duyurular" sekmesi AYNI veriyi geçmişe dönük (okundu dahil) gösterir.
 */
export default function AnnouncementPopup() {
  const [queue, setQueue] = useState([]);
  const [marking, setMarking] = useState(false);

  useEffect(() => {
    api.get("/announcements/active").then((r) => setQueue(r.data)).catch(() => {});
  }, []);

  if (queue.length === 0) return null;
  const current = queue[0];

  async function dismiss() {
    setMarking(true);
    try {
      await api.post(`/announcements/${current.id}/read`);
    } catch {
      // yine de kuyruktan çıkar — kullanıcıyı bloklamamak için sessizce yut
    } finally {
      setMarking(false);
      setQueue((q) => q.slice(1));
    }
  }

  const isKritik = current.priority === "kritik";
  const isOnemli = current.priority === "onemli";

  return (
    <div className="fixed inset-0 bg-black/70 z-[100] flex items-center justify-center p-4 fade-in" data-testid="announcement-popup">
      <div className="card max-w-md w-full p-6">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <div
              className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
                isKritik ? "bg-red-500/15 text-red-400" : isOnemli ? "bg-amber-500/15 text-amber-400" : "bg-[var(--primary)]/15 text-[var(--primary)]"
              }`}
            >
              {isKritik ? <AlertTriangle size={18} /> : <Megaphone size={18} />}
            </div>
            <div>
              <div className="text-[10px] tracking-widest text-[var(--text-dim)]">
                {isKritik ? "KRİTİK DUYURU" : isOnemli ? "ÖNEMLİ DUYURU" : "DUYURU"}
              </div>
              <h3 className="font-display text-lg leading-tight">{current.title}</h3>
            </div>
          </div>
          <button onClick={dismiss} className="text-[var(--text-dim)] hover:text-white shrink-0" aria-label="Kapat" data-testid="announcement-popup-close">
            <X size={18} />
          </button>
        </div>

        <p className="text-sm text-[var(--text-dim)] whitespace-pre-wrap leading-relaxed mb-1">{current.body}</p>
        <div className="text-[10px] text-[var(--text-dim)] mt-2">
          {current.created_by} · {new Date(current.created_at).toLocaleString("tr-TR")}
        </div>

        <div className="flex items-center justify-between mt-5">
          <div className="text-xs text-[var(--text-dim)]">
            {queue.length > 1 ? `${queue.length} duyurudan 1'i` : ""}
          </div>
          <button
            onClick={dismiss}
            disabled={marking}
            data-testid="announcement-popup-read"
            className="btn btn-primary px-5"
          >
            Okudum
          </button>
        </div>
      </div>
    </div>
  );
}
