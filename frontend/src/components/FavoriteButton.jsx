import { useEffect, useState } from "react";
import api from "@/api";
import { Star } from "lucide-react";

/**
 * IT-12 — Bir entity kaydını (çiftçi/parsel/...) favorileme yıldızı.
 * Saved Queries'in (IT-09) sorgu favorilerinden AYRI bir sistem (bkz.
 * backend/favorites.py) — bu, tek bir KAYDI favoriler.
 *
 * Kullanım: <FavoriteButton module="farmers" entityId={id} label={farmer.full_name} />
 */
export default function FavoriteButton({ module, entityId, label }) {
  const [isFavorite, setIsFavorite] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/favorites", { params: { module } }).then((r) => {
      setIsFavorite(r.data.some((f) => f.entity_id === entityId));
    });
  }, [module, entityId]);

  async function toggle() {
    setLoading(true);
    try {
      if (isFavorite) {
        await api.delete(`/favorites/by-entity/${module}/${entityId}`);
        setIsFavorite(false);
      } else {
        await api.post("/favorites", { module, entity_id: entityId, label });
        setIsFavorite(true);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={loading}
      data-testid={`favorite-button-${module}-${entityId}`}
      title={isFavorite ? "Favorilerden çıkar" : "Favorilere ekle"}
      className={isFavorite ? "text-amber-400" : "text-[var(--text-dim)] hover:text-amber-400"}
    >
      <Star size={18} fill={isFavorite ? "currentColor" : "none"} />
    </button>
  );
}
