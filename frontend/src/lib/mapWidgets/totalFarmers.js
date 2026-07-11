import { Users } from "lucide-react";

/**
 * IT-14 — referans widget. ctx.parcels HARİTA GÖRÜNÜMÜNE/filtreye/seçime
 * göre zaten kapsamlanmıştır (bkz. HaritaPaneli.jsx); bu widget sadece
 * o parsellerin sahibi olan BENZERSİZ çiftçi sayısını sayar.
 */
export default {
  key: "toplam_ciftci",
  title: "Toplam Çiftçi",
  icon: Users,
  accent: "bg-[var(--primary)]/10 text-[var(--primary)]",
  compute(ctx) {
    const ids = new Set(ctx.parcels.map((p) => p.farmer_id).filter(Boolean));
    return { value: ids.size };
  },
};
