import { Sprout } from "lucide-react";

const NON_TERMINAL_STATUSES = new Set(["planning", "active", "harvesting"]);

export default {
  key: "aktif_uretim_sezonlari",
  title: "Aktif Üretim Sezonları",
  icon: Sprout,
  accent: "bg-lime-500/10 text-lime-400",
  compute(ctx) {
    const count = ctx.productionCycles.filter(
      (pc) => ctx.parcelIds.has(pc.parcel_id) && NON_TERMINAL_STATUSES.has(pc.status)
    ).length;
    return { value: count };
  },
};
