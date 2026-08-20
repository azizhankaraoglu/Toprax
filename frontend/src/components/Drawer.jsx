import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

/**
 * IT-12 — Genel Drawer (yan panel) altyapısı. Sağdan kayan bir panel:
 * backdrop'a tıklama VEYA ESC ile kapanır. İçerik `children` olarak verilir
 * — Workspace Drawer (bildirimler/son açılanlar/favoriler) bunun üzerine
 * kurulu, ama herhangi bir başka amaç için de (ör. IT-13'ün context-aware
 * CRUD'u) doğrudan kullanılabilir.
 *
 * `document.body`'e portal ile render edilir (2026-08-20'de bulunan gerçek
 * bug: WorkspaceDrawer, Layout.jsx'in `<aside>`'ı İÇİNDE render ediliyordu;
 * `<aside>` her zaman bir Tailwind translate-x-* sınıfı taşıdığından
 * (mobilde açık/kapalı geçişi için) computed `transform` identity matrix
 * bile olsa `position:fixed` bir atanın CSS'te YENİ bir containing block
 * oluşturmasına yol açar — bu panelin `fixed inset-0`'ı artık viewport'a
 * değil o 256px'lik sidebar kutusuna göre konumlanıp sola taşarak
 * kırpılıyordu, "bildirim alanı yarım geliyor" şikayetinin kök nedeni
 * buydu). Portal, Drawer'ı hangi ata ağacına gömülürse gömülsün bu sınıf
 * hataların TAMAMINDAN bağışık kılar.
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

  return createPortal(
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
    </div>,
    document.body
  );
}
