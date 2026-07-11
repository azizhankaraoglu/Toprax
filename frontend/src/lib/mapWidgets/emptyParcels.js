import { CircleDashed } from "lucide-react";

const NON_TERMINAL_STATUSES = new Set(["planning", "active", "harvesting"]);

/**
 * "Boş" = üzerinde devam eden (planning/active/harvesting) bir üretim
 * sezonu OLMAYAN parsel — hiç sezonu olmayan VEYA tüm sezonları
 * completed/cancelled ile kapanmış parseller de buraya dahildir.
 */
export default {
  key: "bos_parseller",
  title: "Boş Parseller",
  icon: CircleDashed,
  accent: "bg-[var(--text-dim)]/10 text-[var(--text-dim)]",
  compute(ctx) {
    const activeParcelIds = new Set(
      ctx.productionCycles.filter((pc) => NON_TERMINAL_STATUSES.has(pc.status)).map((pc) => pc.parcel_id)
    );
    const count = ctx.parcels.filter((p) => !activeParcelIds.has(p.id)).length;
    return { value: count };
  },
};
