/**
 * ÇİFTÇİ 360° DETAY SAYFASI
 *
 * Admin (fabrika müdürü, ziraat mühendisi) bu sayfaya girer ve
 * bir çiftçinin TÜM bilgilerini tek ekranda görür:
 *
 * - Üst kart: Kimlik bilgileri + karne skoru + finansal balance
 * - Tab 1: Parseller (harita üzerinde + liste)
 * - Tab 2: Sözleşmeler (yıllara göre)
 * - Tab 3: Verim geçmişi (grafik + tablo)
 * - Tab 4: Sulama olayları
 * - Tab 5: Toprak analizleri
 * - Tab 6: Finansal hareketler (avans/hakediş)
 * - Tab 7: Kantar randevuları
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/api";
import { MapContainer, TileLayer, Polygon } from "react-leaflet";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { ArrowLeft, Phone, Mail, MapPin, Award, Wallet, Droplets, FileText, Map as MapIcon, Calendar } from "lucide-react";

// Sayı formatla (Türkçe ayraçlarla)
const fmt = (n) => new Intl.NumberFormat("tr-TR").format(n);

export default function FarmerDetail() {
  // URL'den :id parametresini al
  const { id } = useParams();
  const nav = useNavigate();

  // Sayfa state'leri
  const [data, setData] = useState(null);                  // Backend'den gelen tüm data
  const [tab, setTab] = useState("parsel");                // Aktif tab

  // Sayfa yüklendiğinde 360° datayı çek
  useEffect(() => {
    api.get(`/farmers/${id}`).then((r) => setData(r.data));
  }, [id]);

  // Loading durumu
  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const { farmer, summary, parcels, contracts, yields, yield_trend, irrigation, soil_samples, finance, appointments } = data;

  // Tab konfigürasyonu — kolayca yeni tab eklenebilir
  const tabs = [
    { id: "parsel", label: "Parseller", icon: MapIcon, count: parcels.length },
    { id: "sozlesme", label: "Sözleşmeler", icon: FileText, count: contracts.length },
    { id: "verim", label: "Verim", icon: Award, count: yields.length },
    { id: "sulama", label: "Sulama", icon: Droplets, count: irrigation.length },
    { id: "toprak", label: "Toprak", icon: MapPin, count: soil_samples.length },
    { id: "finans", label: "Finans", icon: Wallet, count: finance.length },
    { id: "randevu", label: "Randevular", icon: Calendar, count: appointments.length },
  ];

  return (
    <div className="p-8 max-w-[1600px]" data-testid="farmer-detail-page">
      {/* Geri butonu */}
      <button onClick={() => nav("/ciftciler")} className="btn btn-ghost mb-4 text-sm">
        <ArrowLeft size={14}/> Çiftçi listesi
      </button>

      {/* ÜST KART — Kimlik + Özet */}
      <div className="card p-6 mb-6 grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sol: Avatar + İsim + Üye No */}
        <div className="flex items-center gap-4">
          <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-[var(--primary)] to-[var(--primary-dark)] flex items-center justify-center text-[#052e16] font-display text-3xl">
            {farmer.full_name.charAt(0)}
          </div>
          <div>
            <div className="font-mono text-xs text-[var(--primary)]">{farmer.member_no}</div>
            <div className="font-display text-2xl mt-1">{farmer.full_name}</div>
            <div className="text-xs text-[var(--text-dim)] flex items-center gap-2 mt-1.5">
              <MapPin size={12}/> {farmer.village}
            </div>
          </div>
        </div>

        {/* İletişim bilgileri */}
        <div className="space-y-2 text-sm">
          <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase">İLETİŞİM</div>
          <div className="flex items-center gap-2"><Phone size={14} className="text-[var(--text-dim)]"/>{farmer.phone}</div>
          <div className="flex items-center gap-2"><Mail size={14} className="text-[var(--text-dim)]"/>{farmer.email || "—"}</div>
          <div className="text-xs text-[var(--text-dim)] font-mono">TC: {farmer.tc_no}</div>
        </div>

        {/* Karne kartı */}
        <div className="text-center bg-[var(--surface-2)] rounded-xl p-4">
          <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase mb-2">KARNE SKORU</div>
          <div className={`badge badge-${farmer.karne_score.toLowerCase()} text-base px-4 py-1`}>{farmer.karne_score}</div>
          <div className="font-display text-3xl mt-2">{farmer.karne_points}</div>
          <div className="text-[10px] text-[var(--text-dim)]">/ 100 puan</div>
        </div>

        {/* Finansal bakiye */}
        <div className="text-center bg-[var(--surface-2)] rounded-xl p-4">
          <div className="text-[10px] text-[var(--text-dim)] tracking-widest uppercase mb-2">BAKİYE</div>
          <div className={`font-display text-3xl ${summary.balance >= 0 ? "text-[var(--primary)]" : "text-red-400"}`}>
            {fmt(summary.balance)} ₺
          </div>
          <div className="text-[10px] text-[var(--text-dim)] mt-1">Üyelik {farmer.membership_year}</div>
        </div>
      </div>

      {/* ÖZET KPI'LAR — küçük kartlar şeridi */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <div className="card p-4 text-center">
          <div className="text-xs text-[var(--text-dim)] uppercase">Parsel</div>
          <div className="font-display text-2xl text-[var(--primary)]">{summary.parcel_count}</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-xs text-[var(--text-dim)] uppercase">Toplam Alan</div>
          <div className="font-display text-2xl">{fmt(summary.total_area_dekar)} <span className="text-xs text-[var(--text-dim)]">da</span></div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-xs text-[var(--text-dim)] uppercase">Aktif Sözleşme</div>
          <div className="font-display text-2xl">{summary.active_contracts}</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-xs text-[var(--text-dim)] uppercase">Su Kullanımı</div>
          <div className="font-display text-2xl">{fmt(summary.total_water_m3)} <span className="text-xs text-[var(--text-dim)]">m³</span></div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-xs text-[var(--text-dim)] uppercase">Toprak Analizi</div>
          <div className="font-display text-2xl">{summary.soil_samples_count}</div>
        </div>
      </div>

      {/* VERİM TREND GRAFİĞİ */}
      {yield_trend.length > 0 && (
        <div className="card p-5 mb-6">
          <h3 className="font-display text-lg mb-4">Yıllık Verim Karşılaştırması</h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={yield_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a2326"/>
              <XAxis dataKey="year" stroke="#97a8a0"/>
              <YAxis stroke="#97a8a0"/>
              <Tooltip contentStyle={{ background: "#11181a", border: "1px solid #243038", borderRadius: 8 }}/>
              <Legend wrapperStyle={{ fontSize: 12 }}/>
              <Bar dataKey="expected" fill="#fbbf24" name="Beklenen (ton)" radius={[6,6,0,0]}/>
              <Bar dataKey="actual" fill="#4ade80" name="Gerçekleşen (ton)" radius={[6,6,0,0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* TAB NAVIGATION */}
      <div className="flex gap-2 mb-4 border-b border-[var(--border)] overflow-x-auto scrollbar">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            data-testid={`tab-${t.id}`}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm transition-colors border-b-2 ${
              tab === t.id
                ? "border-[var(--primary)] text-[var(--primary)]"
                : "border-transparent text-[var(--text-dim)] hover:text-white"
            }`}
          >
            <t.icon size={14}/>
            {t.label}
            <span className="text-[10px] bg-[var(--surface-2)] px-1.5 py-0.5 rounded">{t.count}</span>
          </button>
        ))}
      </div>

      {/* TAB İÇERİKLERİ */}
      <div className="fade-in">
        {/* Parseller — harita + liste */}
        {tab === "parsel" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="card overflow-hidden lg:col-span-2" style={{ height: 480 }}>
              {parcels.length > 0 && parcels[0].geometry ? (
                <MapContainer center={[parcels[0].geometry.coordinates[0][0][1], parcels[0].geometry.coordinates[0][0][0]]} zoom={9} style={{ height: "100%", width: "100%" }}>
                  <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap"/>
                  {parcels.map((p) => p.geometry && (
                    <Polygon
                      key={p.id}
                      positions={p.geometry.coordinates[0].map(([lng, lat]) => [lat, lng])}
                      pathOptions={{ color: "#4ade80", fillColor: "#4ade80", fillOpacity: 0.4, weight: 2 }}
                    />
                  ))}
                </MapContainer>
              ) : <div className="p-10 text-center text-[var(--text-dim)]">Bu çiftçinin haritada gösterilebilir parseli yok</div>}
            </div>
            <div className="card overflow-y-auto scrollbar" style={{ maxHeight: 480 }}>
              {parcels.map((p) => (
                <div key={p.id} onClick={() => nav(`/parseller/${p.id}`)} className="p-3 border-b border-[var(--border)] cursor-pointer hover:bg-[var(--surface-2)]">
                  <div className="flex justify-between">
                    <span className="font-mono text-xs text-[var(--text-dim)]">{p.parcel_code}</span>
                    <span className="text-xs text-[var(--primary)]">{p.area_dekar.toFixed(1)} da</span>
                  </div>
                  <div className="text-sm mt-1">{p.name}</div>
                  <div className="text-xs text-[var(--text-dim)] mt-0.5">{p.soil_type} · {p.irrigation}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Sözleşmeler */}
        {tab === "sozlesme" && (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-3">No</th><th className="p-3">Sezon</th><th className="p-3">Çeşit</th>
                <th className="p-3">Kota (da)</th><th className="p-3">Kota (ton)</th><th className="p-3">Durum</th>
              </tr></thead>
              <tbody>
                {contracts.map((c) => (
                  <tr key={c.id} className="border-b border-[var(--border)]">
                    <td className="p-3 font-mono text-xs">{c.contract_no}</td>
                    <td className="p-3">{c.season}</td>
                    <td className="p-3">{c.variety}</td>
                    <td className="p-3">{c.kota_dekar}</td>
                    <td className="p-3">{c.kota_ton}</td>
                    <td className="p-3"><span className={`badge ${c.status === "imzalı" ? "badge-a" : "badge-c"}`}>{c.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Verim */}
        {tab === "verim" && (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-3">Sezon</th><th className="p-3">Alan</th>
                <th className="p-3">Beklenen</th><th className="p-3">Gerçekleşen</th><th className="p-3">Verim</th><th className="p-3">Polar</th>
              </tr></thead>
              <tbody>
                {yields.map((y) => (
                  <tr key={y.id} className="border-b border-[var(--border)]">
                    <td className="p-3 font-medium">{y.season}</td>
                    <td className="p-3">{y.area_dekar} da</td>
                    <td className="p-3 text-[var(--text-dim)]">{y.expected_ton.toFixed(1)} t</td>
                    <td className="p-3 text-[var(--primary)]">{y.actual_ton.toFixed(1)} t</td>
                    <td className="p-3">{(y.actual_ton / y.area_dekar).toFixed(2)} t/da</td>
                    <td className="p-3">%{y.polar_oran}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Sulama */}
        {tab === "sulama" && (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-3">Tarih</th><th className="p-3">Yöntem</th>
                <th className="p-3">Su (m³)</th><th className="p-3">Önce Nem</th><th className="p-3">Sonra Nem</th>
              </tr></thead>
              <tbody>
                {irrigation.slice(0, 30).map((e) => (
                  <tr key={e.id} className="border-b border-[var(--border)]">
                    <td className="p-3">{e.date}</td>
                    <td className="p-3 capitalize">{e.method}</td>
                    <td className="p-3 text-[var(--primary)]">{e.water_m3} m³</td>
                    <td className="p-3 text-[var(--text-dim)]">%{e.moisture_before}</td>
                    <td className="p-3 text-[var(--primary)]">%{e.moisture_after}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {irrigation.length === 0 && <div className="p-6 text-center text-[var(--text-dim)]">Henüz sulama kaydı yok</div>}
          </div>
        )}

        {/* Toprak */}
        {tab === "toprak" && (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-3">Tarih</th><th className="p-3">Lab</th><th className="p-3">pH</th>
                <th className="p-3">EC</th><th className="p-3">OM%</th><th className="p-3">N/P/K</th><th className="p-3">Öneri</th>
              </tr></thead>
              <tbody>
                {soil_samples.map((s) => (
                  <tr key={s.id} className="border-b border-[var(--border)]">
                    <td className="p-3">{s.date}</td>
                    <td className="p-3 text-xs text-[var(--text-dim)]">{s.lab_name}</td>
                    <td className="p-3">{s.ph}</td>
                    <td className="p-3">{s.ec}</td>
                    <td className="p-3">{s.organic_matter_pct}</td>
                    <td className="p-3 text-xs">{s.n_ppm}/{s.p_ppm}/{s.k_ppm}</td>
                    <td className="p-3 text-xs text-[var(--primary)]">{s.recommendation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {soil_samples.length === 0 && <div className="p-6 text-center text-[var(--text-dim)]">Toprak analizi yok</div>}
          </div>
        )}

        {/* Finans */}
        {tab === "finans" && (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-3">Tarih</th><th className="p-3">Tip</th><th className="p-3">Açıklama</th><th className="p-3 text-right">Tutar</th>
              </tr></thead>
              <tbody>
                {finance.map((f) => (
                  <tr key={f.id} className="border-b border-[var(--border)]">
                    <td className="p-3">{f.date}</td>
                    <td className="p-3"><span className={`badge ${f.amount > 0 ? "badge-a" : "badge-d"}`}>{f.type}</span></td>
                    <td className="p-3 text-[var(--text-dim)]">{f.description}</td>
                    <td className={`p-3 text-right font-mono ${f.amount > 0 ? "text-[var(--primary)]" : "text-red-400"}`}>
                      {fmt(f.amount)} ₺
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Randevular */}
        {tab === "randevu" && (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-3">Tarih</th><th className="p-3">Plaka</th>
                <th className="p-3">Tahmini Ton</th><th className="p-3">Gerçek Ton</th><th className="p-3">Polar</th><th className="p-3">Durum</th>
              </tr></thead>
              <tbody>
                {appointments.map((a) => (
                  <tr key={a.id} className="border-b border-[var(--border)]">
                    <td className="p-3">{new Date(a.scheduled_at).toLocaleString("tr-TR")}</td>
                    <td className="p-3 font-mono">{a.truck_plate}</td>
                    <td className="p-3">{a.estimated_ton} t</td>
                    <td className="p-3">{a.actual_ton ? `${a.actual_ton} t` : "—"}</td>
                    <td className="p-3">{a.polar_oran ? `%${a.polar_oran}` : "—"}</td>
                    <td className="p-3"><span className="badge badge-b">{a.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
