import { Wheat } from "lucide-react";

const PLANTED_STATUSES = new Set(["active", "harvesting"]);

/**
 * "Ekili" = production_cycles.status "active" veya "harvesting" (fiilen
 * toprağa girmiş) — "planning" (henüz ekilmemiş, sadece planlanmış) hariç
 * tutulur, bkz. production_cycles.py STATUS_LABELS.
 */
export default {
  key: "toplam_ekili_alan",
  title: "Toplam Ekili Alan",
  icon: Wheat,
  accent: "bg-emerald-500/10 text-emerald-400",
  compute(ctx) {
    const plantedParcelIds = new Set(
      ctx.productionCycles.filter((pc) => PLANTED_STATUSES.has(pc.status)).map((pc) => pc.parcel_id)
    );
    const sum = ctx.parcels
      .filter((p) => plantedParcelIds.has(p.id))
      .reduce((s, p) => s + (p.area_dekar || 0), 0);
    return { value: Math.round(sum), suffix: "dekar" };
  },
};
