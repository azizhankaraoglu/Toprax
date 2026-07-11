import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

/**
 * IT-12 — Genel breadcrumb. items: [{ label, to? }] — son öğe `to` almasa
 * bile normaldir (mevcut sayfa, tıklanamaz).
 *
 * Kullanım: <Breadcrumb items={[{ label: "Çiftçiler", to: "/ciftciler" }, { label: farmer.full_name }]} />
 */
export default function Breadcrumb({ items }) {
  return (
    <nav className="flex items-center gap-1.5 text-xs text-[var(--text-dim)] mb-3" aria-label="breadcrumb">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight size={12} />}
          {item.to ? (
            <Link to={item.to} className="hover:text-[var(--primary)]">{item.label}</Link>
          ) : (
            <span className="text-white">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
