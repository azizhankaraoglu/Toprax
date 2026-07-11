import { ClipboardList } from "lucide-react";

// bkz. backend/data_entry.py TaskUpdate.status: "planlı" | "devam ediyor" | "tamamlandı" | "iptal"
const PENDING_TASK_STATUSES = new Set(["planlı", "devam ediyor"]);

export default {
  key: "gorev_bekleyen_parseller",
  title: "Görev Bekleyen Parseller",
  icon: ClipboardList,
  accent: "bg-violet-500/10 text-violet-400",
  compute(ctx) {
    const pendingParcelIds = new Set(
      ctx.tasks.filter((t) => PENDING_TASK_STATUSES.has(t.status)).map((t) => t.parcel_id)
    );
    const count = ctx.parcels.filter((p) => pendingParcelIds.has(p.id)).length;
    return { value: count };
  },
};
