import { AlertTriangle } from "lucide-react";

// bkz. pages/Parcels.jsx RISK_COLORS — aynı sözlük, tek kaynak burada tekrarlanmıyor
// (döngüsel import olmasın diye kopyalanmıştır; ikisi de aynı backend risk_level
// değerlerini — yesil/sari/turuncu/kirmizi — kullanır).
const RISKY_LEVELS = new Set(["turuncu", "kirmizi"]);

export default {
  key: "riskli_parseller",
  title: "Riskli Parseller",
  icon: AlertTriangle,
  accent: "bg-red-500/10 text-red-400",
  compute(ctx) {
    const count = ctx.parcels.filter((p) => RISKY_LEVELS.has(p.risk_level)).length;
    return { value: count };
  },
};
