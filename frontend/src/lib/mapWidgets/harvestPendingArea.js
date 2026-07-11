import { Target } from "lucide-react";

export default {
  key: "hasat_bekleyen_alan",
  title: "Hasat Bekleyen Alanlar",
  icon: Target,
  accent: "bg-amber-500/10 text-amber-400",
  compute(ctx) {
    const harvestParcelIds = new Set(
      ctx.productionCycles.filter((pc) => pc.status === "harvesting").map((pc) => pc.parcel_id)
    );
    const sum = ctx.parcels
      .filter((p) => harvestParcelIds.has(p.id))
      .reduce((s, p) => s + (p.area_dekar || 0), 0);
    return { value: Math.round(sum), suffix: "dekar" };
  },
};
