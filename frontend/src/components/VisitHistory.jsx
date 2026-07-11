import { useEffect, useState } from "react";
import api from "@/api";
import { History } from "lucide-react";

/**
 * IT-23 — Ziyaret Geçmişi sekmesi. Visit kayıtlarından türetilir (backend
 * create_visit'in task'tan denormalize ettiği farmer_id/parcel_id/
 * production_cycle_id filtreleriyle — bkz. field_ops.py IT-23 notu).
 *
 * Kullanım: <VisitHistory farmerId={...} /> VEYA parcelId VEYA productionCycleId
 * (hangisi verilirse o filtre kullanılır).
 */
export default function VisitHistory({ farmerId, parcelId, productionCycleId }) {
  const [visits, setVisits] = useState(null);

  useEffect(() => {
    const params = {};
    if (farmerId) params.farmer_id = farmerId;
    if (parcelId) params.parcel_id = parcelId;
    if (productionCycleId) params.production_cycle_id = productionCycleId;
    api.get("/visits", { params }).then((r) => setVisits(r.data)).catch(() => setVisits([]));
  }, [farmerId, parcelId, productionCycleId]);

  if (visits === null) return null;

  return (
    <div className="card p-5" data-testid="visit-history">
      <h3 className="font-display text-lg mb-4 flex items-center gap-2"><History size={16} className="text-[var(--primary)]"/>Ziyaret Geçmişi ({visits.length})</h3>
      <div className="space-y-2">
        {visits.map((v) => (
          <div key={v.id} className="p-3 bg-[var(--surface-2)] rounded-lg text-sm">
            <div className="flex items-center justify-between">
              <div className="font-medium">{v.visited_by}</div>
              <div className="text-xs text-[var(--text-dim)]">{(v.started_at || "").slice(0, 16).replace("T", " ")}</div>
            </div>
            {v.notes && <div className="text-xs text-[var(--text-dim)] mt-1">{v.notes}</div>}
            <div className="text-[10px] text-[var(--text-dim)] mt-1 flex gap-3">
              {v.gps_start && <span>GPS var</span>}
              {v.photos?.length > 0 && <span>{v.photos.length} fotoğraf</span>}
              {v.form_response && <span>Form dolduruldu</span>}
              {v.ended_at && <span>Bitiş: {v.ended_at.slice(0, 16).replace("T", " ")}</span>}
            </div>
          </div>
        ))}
        {visits.length === 0 && <div className="text-center text-[var(--text-dim)] py-6 text-sm">Henüz ziyaret kaydı yok</div>}
      </div>
    </div>
  );
}
