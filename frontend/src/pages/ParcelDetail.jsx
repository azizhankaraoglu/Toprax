/**
 * PARSEL DETAY SAYFASI
 *
 * Bir parselin tüm bilgilerini gösterir:
 * - Harita üzerinde konumu
 * - Sahip çiftçi bilgisi
 * - Toprak analizleri
 * - Sulama olayları
 * - Verim geçmişi
 * - Ekim geçmişi
 * - Görev listesi
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/api";
import { MapContainer, TileLayer, Polygon } from "react-leaflet";
import { ArrowLeft, MapPin, Droplets, FlaskConical, Sprout, Award, Satellite, Radio, Plane } from "lucide-react";

const RISK_COLORS = { yesil: "#4ade80", sari: "#fbbf24", turuncu: "#fb923c", kirmizi: "#ef4444" };

export default function ParcelDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);

  useEffect(() => { api.get(`/parcels/${id}`).then((r) => setData(r.data)); }, [id]);
  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const { parcel, farmer, plantings, soil_samples, irrigation_events, yields, tasks, iot_sensors = [], drone_missions = [] } = data;
  const centerLat = parcel.geometry?.coordinates[0][0][1] || 39.5;
  const centerLng = parcel.geometry?.coordinates[0][0][0] || 33.5;
  const riskColor = RISK_COLORS[parcel.risk_level] || "#4ade80";

  return (
    <div className="p-8 max-w-[1600px]" data-testid="parcel-detail-page">
      <button onClick={() => nav("/parseller")} className="btn btn-ghost mb-4 text-sm">
        <ArrowLeft size={14}/> Parsel listesi
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        {/* SOL: HARİTA */}
        <div className="card overflow-hidden lg:col-span-2" style={{ height: 380 }}>
          {parcel.geometry && (
            <MapContainer center={[centerLat, centerLng]} zoom={14} style={{ height: "100%", width: "100%" }}>
              <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap"/>
              <Polygon
                positions={parcel.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])}
                pathOptions={{ color: riskColor, fillColor: riskColor, fillOpacity: 0.5, weight: 3 }}
              />
            </MapContainer>
          )}
        </div>

        {/* SAĞ: ÖZET BİLGİ */}
        <div className="card p-5 space-y-4">
          <div>
            <div className="font-mono text-xs text-[var(--primary)]">{parcel.parcel_code}</div>
            <div className="font-display text-2xl mt-1">{parcel.name}</div>
          </div>
          <div className="text-sm text-[var(--text-dim)] flex items-center gap-2">
            <MapPin size={14}/> {parcel.village} · {parcel.active_season} sezonu
          </div>
          {parcel.risk_level && (
            <div className="flex items-center gap-2 text-sm p-2.5 rounded-lg" style={{ background: `${riskColor}15`, color: riskColor }}>
              <Satellite size={14}/>
              <span className="font-medium">{parcel.risk_label}</span>
              <span className="text-xs opacity-80 ml-auto">NDVI {parcel.ndvi_latest}</span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 pt-3 border-t border-[var(--border)]">
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Alan</div><div className="font-display text-xl">{parcel.area_dekar} <span className="text-xs">da</span></div></div>
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Ürün</div><div className="font-medium">{parcel.current_crop}</div></div>
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Toprak</div><div className="font-medium">{parcel.soil_type}</div></div>
            <div><div className="text-[10px] text-[var(--text-dim)] uppercase">Sulama</div><div className="font-medium">{parcel.irrigation}</div></div>
          </div>

          {farmer && (
            <div className="pt-3 border-t border-[var(--border)]">
              <div className="text-[10px] text-[var(--text-dim)] uppercase mb-1">SAHİBİ</div>
              <button onClick={() => nav(`/ciftciler/${farmer.id}`)} className="text-left w-full hover:bg-[var(--surface-2)] p-2 rounded transition-colors">
                <div className="text-sm">{farmer.full_name}</div>
                <div className="text-xs text-[var(--text-dim)]">{farmer.member_no} · {farmer.phone}</div>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* SEKMELER — Veri tablolarına grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* TOPRAK ANALİZLERİ */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <FlaskConical size={16} className="text-[var(--primary)]"/>
            <h3 className="font-display text-lg">Toprak Analizleri ({soil_samples.length})</h3>
          </div>
          <div className="max-h-[300px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5">Tarih</th><th className="p-2.5">pH</th>
                  <th className="p-2.5">N/P/K</th><th className="p-2.5">Öneri</th>
                </tr>
              </thead>
              <tbody>
                {soil_samples.map((s) => (
                  <tr key={s.id} className="border-b border-[var(--border)]">
                    <td className="p-2.5 text-xs">{s.date}</td>
                    <td className="p-2.5">{s.ph}</td>
                    <td className="p-2.5 text-xs">{s.n_ppm}/{s.p_ppm}/{s.k_ppm}</td>
                    <td className="p-2.5 text-xs text-[var(--primary)]">{s.recommendation}</td>
                  </tr>
                ))}
                {soil_samples.length === 0 && <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Toprak analizi yok</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {/* SULAMA OLAYLARI */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Droplets size={16} className="text-blue-400"/>
            <h3 className="font-display text-lg">Sulama Olayları ({irrigation_events.length})</h3>
          </div>
          <div className="max-h-[300px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5">Tarih</th><th className="p-2.5">Yöntem</th>
                  <th className="p-2.5">Su (m³)</th><th className="p-2.5">Nem</th>
                </tr>
              </thead>
              <tbody>
                {irrigation_events.map((e) => (
                  <tr key={e.id} className="border-b border-[var(--border)]">
                    <td className="p-2.5 text-xs">{e.date}</td>
                    <td className="p-2.5 capitalize">{e.method}</td>
                    <td className="p-2.5 text-[var(--primary)]">{e.water_m3}</td>
                    <td className="p-2.5 text-xs">{e.moisture_before}%→{e.moisture_after}%</td>
                  </tr>
                ))}
                {irrigation_events.length === 0 && <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Sulama kaydı yok</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {/* EKİM GEÇMİŞİ */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Sprout size={16} className="text-emerald-400"/>
            <h3 className="font-display text-lg">Ekim Geçmişi ({plantings.length})</h3>
          </div>
          <div className="max-h-[280px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5">Sezon</th><th className="p-2.5">Çeşit</th>
                  <th className="p-2.5">Ekim</th><th className="p-2.5">Aşama</th>
                </tr>
              </thead>
              <tbody>
                {plantings.map((p) => (
                  <tr key={p.id} className="border-b border-[var(--border)]">
                    <td className="p-2.5 font-medium">{p.season}</td>
                    <td className="p-2.5">{p.variety}</td>
                    <td className="p-2.5 text-xs">{p.planting_date}</td>
                    <td className="p-2.5"><span className="badge badge-b">{p.stage}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* VERİM */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Award size={16} className="text-amber-400"/>
            <h3 className="font-display text-lg">Verim Geçmişi ({yields.length})</h3>
          </div>
          <div className="max-h-[280px] overflow-y-auto scrollbar">
            <table className="w-full text-sm">
              <thead className="bg-[var(--surface-2)] sticky top-0">
                <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                  <th className="p-2.5">Sezon</th><th className="p-2.5">Beklenen</th>
                  <th className="p-2.5">Gerçek</th><th className="p-2.5">Polar</th>
                </tr>
              </thead>
              <tbody>
                {yields.map((y) => (
                  <tr key={y.id} className="border-b border-[var(--border)]">
                    <td className="p-2.5 font-medium">{y.season}</td>
                    <td className="p-2.5 text-[var(--text-dim)]">{y.expected_ton.toFixed(1)} t</td>
                    <td className="p-2.5 text-[var(--primary)]">{y.actual_ton.toFixed(1)} t</td>
                    <td className="p-2.5">%{y.polar_oran}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        {/* IoT SENSÖRLER */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Radio size={16} className="text-violet-400"/>
            <h3 className="font-display text-lg">IoT Sensörler ({iot_sensors.length})</h3>
          </div>
          <div className="max-h-[280px] overflow-y-auto scrollbar p-4 space-y-2">
            {iot_sensors.map((s) => (
              <div key={s.id} className="flex items-center justify-between text-sm p-2 rounded bg-[var(--surface-2)]">
                <div>
                  <div className="font-mono text-xs">{s.sensor_code}</div>
                  <div className="text-xs text-[var(--text-dim)]">Nem %{s.nem_pct} · {s.sicaklik_c}°C</div>
                </div>
                <span className={`badge ${s.status === "aktif" ? "badge-a" : "badge-d"}`}>{s.status}</span>
              </div>
            ))}
            {iot_sensors.length === 0 && <div className="text-center text-[var(--text-dim)] py-6">Bu parselde sensör yok</div>}
          </div>
        </div>

        {/* DRONE GÖREVLERİ */}
        <div className="card overflow-hidden">
          <div className="p-4 border-b border-[var(--border)] flex items-center gap-2">
            <Plane size={16} className="text-indigo-400"/>
            <h3 className="font-display text-lg">Drone Görevleri ({drone_missions.length})</h3>
          </div>
          <div className="max-h-[280px] overflow-y-auto scrollbar p-4 space-y-2">
            {drone_missions.map((m) => (
              <div key={m.id} className="text-sm p-2 rounded bg-[var(--surface-2)]">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs">{m.mission_code}</span>
                  <span className="text-xs text-[var(--text-dim)]">{m.flight_date?.slice(0, 10)}</span>
                </div>
                <div className="text-xs text-[var(--text-dim)] mt-1">{m.notes}</div>
              </div>
            ))}
            {drone_missions.length === 0 && <div className="text-center text-[var(--text-dim)] py-6">Bu parselde drone görevi yok</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
