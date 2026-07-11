import { Map as MapIcon } from "lucide-react";

export default {
  key: "toplam_parsel",
  title: "Toplam Parsel",
  icon: MapIcon,
  accent: "bg-blue-500/10 text-blue-400",
  compute(ctx) {
    return { value: ctx.parcels.length };
  },
};
