import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { Bell, Clock, Star, Trash2, CheckCheck, Megaphone } from "lucide-react";
import Drawer from "@/components/Drawer";
import { getRecentlyViewed } from "@/lib/recentlyViewed";
import { moduleDetailPath } from "@/lib/moduleRoutes";

/**
 * IT-12 — Workspace Drawer: Drawer.jsx altyapısını kullanan, sidebar'dan
 * açılan TEK panel — 4 sekme: Bildirimler (zil rozeti ile), Duyurular
 * (backend/announcements.py — açılış popup'ının aynı verisi, geçmişe
 * dönük tekrar okunabilir), Son Açılanlar (localStorage, bkz.
 * lib/recentlyViewed.js), Favoriler (backend/favorites.py).
 * Layout.jsx'e tek satırla eklenir: <WorkspaceDrawer />
 */
const TABS = [
  { id: "bildirimler", label: "Bildirimler", icon: Bell },
  { id: "duyurular", label: "Duyurular", icon: Megaphone },
  { id: "son", label: "Son Açılanlar", icon: Clock },
  { id: "favoriler", label: "Favoriler", icon: Star },
];

export default function WorkspaceDrawer() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("bildirimler");
  const [unreadCount, setUnreadCount] = useState(0);
  const [annUnreadCount, setAnnUnreadCount] = useState(0);
  const [notifs, setNotifs] = useState([]);
  const [announcements, setAnnouncements] = useState([]);
  const [favorites, setFavorites] = useState([]);
  const [recent, setRecent] = useState([]);

  function loadUnreadCount() {
    api.get("/notifications/unread-count").then((r) => setUnreadCount(r.data.count));
  }

  function loadAnnUnreadCount() {
    api.get("/announcements/unread-count").then((r) => setAnnUnreadCount(r.data.count));
  }

  useEffect(() => { loadUnreadCount(); loadAnnUnreadCount(); }, []);

  useEffect(() => {
    if (!open) return;
    if (tab === "bildirimler") api.get("/notifications").then((r) => setNotifs(r.data));
    else if (tab === "duyurular") api.get("/announcements/active", { params: { unread_only: false } }).then((r) => setAnnouncements(r.data));
    else if (tab === "favoriler") api.get("/favorites").then((r) => setFavorites(r.data));
    else if (tab === "son") setRecent(getRecentlyViewed());
  }, [open, tab]);

  async function markAnnouncementRead(a) {
    if (a.is_read) return;
    await api.post(`/announcements/${a.id}/read`);
    setAnnouncements((list) => list.map((x) => (x.id === a.id ? { ...x, is_read: true } : x)));
    loadAnnUnreadCount();
  }

  async function markRead(n) {
    if (n.status === "okundu") return;
    await api.put(`/notifications/${n.id}/read`);
    setNotifs((list) => list.map((x) => (x.id === n.id ? { ...x, status: "okundu" } : x)));
    loadUnreadCount();
  }

  async function markAllRead() {
    await api.post("/notifications/mark-all-read");
    setNotifs((list) => list.map((x) => ({ ...x, status: "okundu" })));
    loadUnreadCount();
  }

  async function removeFavorite(f) {
    await api.delete(`/favorites/${f.id}`);
    setFavorites((list) => list.filter((x) => x.id !== f.id));
  }

  function goToFavorite(f) {
    const path = moduleDetailPath(f.module, { id: f.entity_id });
    if (path) { nav(path); setOpen(false); }
  }

  function goToRecent(r) {
    if (r.path) { nav(r.path); setOpen(false); }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        data-testid="workspace-drawer-trigger"
        className="relative text-[var(--text-dim)] hover:text-white"
        title="Bildirimler, Duyurular, Son Açılanlar, Favoriler"
      >
        <Bell size={16} />
        {(unreadCount + annUnreadCount) > 0 && (
          <span className="absolute -top-1.5 -right-1.5 min-w-[15px] h-[15px] px-[3px] rounded-full bg-red-500 text-white text-[9px] flex items-center justify-center">
            {(unreadCount + annUnreadCount) > 99 ? "99+" : unreadCount + annUnreadCount}
          </span>
        )}
      </button>

      <Drawer open={open} onClose={() => setOpen(false)} title="Çalışma Alanı">
        <div className="flex border-b border-[var(--border)]">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs ${
                tab === t.id ? "text-[var(--primary)] border-b-2 border-[var(--primary)]" : "text-[var(--text-dim)]"
              }`}
            >
              <t.icon size={13} /> {t.label}
              {t.id === "bildirimler" && unreadCount > 0 && (
                <span className="badge badge-d text-[9px] px-1.5">{unreadCount}</span>
              )}
              {t.id === "duyurular" && annUnreadCount > 0 && (
                <span className="badge badge-d text-[9px] px-1.5">{annUnreadCount}</span>
              )}
            </button>
          ))}
        </div>

        {tab === "bildirimler" && (
          <div>
            {notifs.length > 0 && (
              <div className="p-2 border-b border-[var(--border)] flex justify-end">
                <button onClick={markAllRead} className="btn text-xs"><CheckCheck size={13} /> Tümünü okundu işaretle</button>
              </div>
            )}
            {notifs.length === 0 ? (
              <div className="p-6 text-center text-[var(--text-dim)] text-sm">Bildirim yok.</div>
            ) : notifs.map((n) => (
              <button
                key={n.id}
                onClick={() => markRead(n)}
                className={`w-full text-left p-3 border-b border-[var(--border)] hover:bg-[var(--surface-2)] ${n.status !== "okundu" ? "bg-[var(--primary)]/5" : ""}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-medium">{n.title}</div>
                  {n.status !== "okundu" && <span className="w-2 h-2 rounded-full bg-[var(--primary)] mt-1.5 shrink-0" />}
                </div>
                <div className="text-xs text-[var(--text-dim)] mt-0.5">{n.message}</div>
                <div className="text-[10px] text-[var(--text-dim)] mt-1">{new Date(n.created_at).toLocaleString("tr-TR")}</div>
              </button>
            ))}
          </div>
        )}

        {tab === "duyurular" && (
          announcements.length === 0 ? (
            <div className="p-6 text-center text-[var(--text-dim)] text-sm">Aktif duyuru yok.</div>
          ) : announcements.map((a) => (
            <button
              key={a.id}
              onClick={() => markAnnouncementRead(a)}
              className={`w-full text-left p-3 border-b border-[var(--border)] hover:bg-[var(--surface-2)] ${!a.is_read ? "bg-[var(--primary)]/5" : ""}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="text-sm font-medium flex items-center gap-1.5">
                  {a.priority === "kritik" && <span className="badge badge-d text-[9px]">KRİTİK</span>}
                  {a.priority === "onemli" && <span className="badge badge-c text-[9px]">ÖNEMLİ</span>}
                  {a.title}
                </div>
                {!a.is_read && <span className="w-2 h-2 rounded-full bg-[var(--primary)] mt-1.5 shrink-0" />}
              </div>
              <div className="text-xs text-[var(--text-dim)] mt-0.5 whitespace-pre-wrap">{a.body}</div>
              <div className="text-[10px] text-[var(--text-dim)] mt-1">
                {a.created_by} · {new Date(a.created_at).toLocaleString("tr-TR")}
              </div>
            </button>
          ))
        )}

        {tab === "son" && (
          recent.length === 0 ? (
            <div className="p-6 text-center text-[var(--text-dim)] text-sm">Henüz görüntülenen kayıt yok.</div>
          ) : recent.map((r) => (
            <button key={`${r.module}-${r.id}`} onClick={() => goToRecent(r)}
                    className="w-full text-left p-3 border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
              <div className="text-sm">{r.label}</div>
              <div className="text-[10px] text-[var(--text-dim)] mt-0.5">{new Date(r.viewedAt).toLocaleString("tr-TR")}</div>
            </button>
          ))
        )}

        {tab === "favoriler" && (
          favorites.length === 0 ? (
            <div className="p-6 text-center text-[var(--text-dim)] text-sm">Henüz favori eklenmedi.</div>
          ) : favorites.map((f) => (
            <div key={f.id} className="flex items-center border-b border-[var(--border)]">
              <button onClick={() => goToFavorite(f)} className="flex-1 text-left p-3 hover:bg-[var(--surface-2)]">
                <div className="text-sm">{f.label}</div>
                <div className="text-[10px] text-[var(--text-dim)] mt-0.5">{new Date(f.created_at).toLocaleString("tr-TR")}</div>
              </button>
              <button onClick={() => removeFavorite(f)} className="p-3 text-[var(--text-dim)] hover:text-red-400">
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </Drawer>
    </>
  );
}
