import { useEffect } from "react";
import { X } from "lucide-react";

/**
 * IT-12 — Genel Drawer (yan panel) altyapısı. Sağdan kayan bir panel:
 * backdrop'a tıklama VEYA ESC ile kapanır. İçerik `children` olarak verilir
 * — Workspace Drawer (bildirimler/son açılanlar/favoriler) bunun üzerine
 * kurulu, ama herhangi bir başka amaç için de (ör. IT-13'ün context-aware
 * CRUD'u) doğrudan kullanılabilir.
 *
 * Kullanım:
 *   <Drawer open={open} onClose={() => setOpen(false)} title="Başlık">
 *     ...içerik...
 *   </Drawer>
 */
export default function Drawer({ open, onClose, title, children, width = "420px" }) {
  useEffect(() => {
    if (!open) return;
    function onKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div
        className="relative h-full bg-[var(--surface)] border-l border-[var(--border)] flex flex-col shadow-2xl"
        style={{ width, maxWidth: "100vw" }}
      >
        <div className="p-4 border-b border-[var(--border)] flex items-center justify-between">
          <h3 className="font-display text-lg">{title}</h3>
          <button onClick={onClose} className="text-[var(--text-dim)] hover:text-white"><X size={18} /></button>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar">{children}</div>
      </div>
    </div>
  );
}
