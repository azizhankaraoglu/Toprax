/**
 * SÖZLEŞME DETAYI (SON HAL) — route /sozlesmeler/:id
 *
 * Sözleşmenin ilk kendi detay sayfası (önceden moduleRoutes contracts'ı
 * parsele yönlendiriyordu). Veri kaynağı: GET /contracts/{id} (data_entry.py)
 * — sözleşme + gömülü farmer/parcel özetleri + bağlı ekim + kantar kayıtları.
 * Çapraz navigasyon: çiftçi kartı → /ciftciler/:id, parsel kartı →
 * /parseller/:id, ekim satırları → /ekim?parcel=<id>.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "@/api";
import Breadcrumb from "@/components/Breadcrumb";
import FavoriteButton from "@/components/FavoriteButton";
import { pushRecentlyViewed } from "@/lib/recentlyViewed";
import { FileText, Users, Map as MapIcon, Sprout, Scale, AlertTriangle } from "lucide-react";

const STATUS_BADGE = {
  "imzalı": "badge-a", "onay_bekliyor": "badge-d", "iptal": "badge-neutral", "taslak": "badge-c",
};

function InfoRow({ label, value }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex justify-between py-1.5 border-b border-[var(--border)] last:border-0 text-sm">
      <span className="text-[var(--text-dim)]">{label}</span>
      <span className="text-right">{String(value)}</span>
    </div>
  );
}

export default function ContractDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [c, setC] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setC(null); setError("");
    api.get(`/contracts/${id}`)
      .then((r) => {
        setC(r.data);
        pushRecentlyViewed({ module: "contracts", id: r.data.id,
          label: r.data.contract_no || "Sözleşme" });
      })
      .catch((e) => setError(e.response?.data?.detail || "Sözleşme yüklenemedi"));
  }, [id]);

  if (error) return <div className="p-10 text-[var(--danger)]">{error}</div>;
  if (!c) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const parcelKonum = [c.parcel?.il, c.parcel?.ilce, c.parcel?.mahalle || c.parcel?.village]
    .filter(Boolean).join(" / ");

  return (
    <div className="p-8 max-w-[1200px]" data-testid="contract-detail-page">
      <Breadcrumb items={[{ label: "Sözleşmeler", to: "/sozlesmeler" }, { label: c.contract_no || "Sözleşme" }]} />

      <header className="mb-6 flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SÖZLEŞME DETAYI</div>
          <h1 className="font-display text-3xl flex items-center gap-3">
            <FileText size={26} className="text-[var(--primary)]" />
            {c.contract_no || "Sözleşme"}
            <FavoriteButton module="contracts" entityId={c.id} label={c.contract_no || "Sözleşme"} />
          </h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            {c.season} sezonu · {c.crop || "Şeker Pancarı"} · {c.variety}
          </p>
        </div>
        <span className={`badge ${STATUS_BADGE[c.status] || "badge-neutral"} text-sm`}
              data-testid="contract-status-badge">
          {c.status === "onay_bekliyor" ? "onay bekliyor" : c.status}
        </span>
      </header>

      {c.deviation && (
        <div className="card p-4 mb-4 border-l-4 border-[var(--warning,#F59E0B)]" data-testid="contract-deviation-card">
          <div className="flex items-center gap-2 text-sm font-medium mb-1">
            <AlertTriangle size={15} className="text-[var(--warning,#F59E0B)]" /> Kota→Alan Sapması
          </div>
          <p className="text-sm text-[var(--text-dim)]">{c.deviation.aciklama}</p>
          {c.deviation_decided_by && (
            <p className="text-xs text-[var(--text-dim)] mt-2">
              Karar: {c.deviation_decided_by} · {c.deviation_decided_at?.slice(0, 10)}
              {c.deviation_decision_note ? ` · "${c.deviation_decision_note}"` : ""}
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* Çiftçi kartı → çapraz navigasyon */}
        <div
          className="card card-hover p-5 cursor-pointer"
          role="button" tabIndex={0}
          data-testid="contract-farmer-card"
          onClick={() => c.farmer && nav(`/ciftciler/${c.farmer.id}`)}
          onKeyDown={(e) => { if (e.key === "Enter" && c.farmer) nav(`/ciftciler/${c.farmer.id}`); }}
          title="Çiftçi detayına git"
        >
          <div className="flex items-center gap-2 text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">
            <Users size={14} /> Çiftçi
          </div>
          {c.farmer ? (
            <>
              <div className="font-medium">{c.farmer.full_name}</div>
              <div className="text-xs text-[var(--text-dim)] mt-1">
                {c.farmer.member_no} · {c.farmer.village || "—"}
              </div>
              {c.farmer.karne_score && (
                <span className="badge badge-neutral mt-2 inline-block">
                  Karne {c.farmer.karne_score} · {c.farmer.karne_points}
                </span>
              )}
            </>
          ) : <div className="text-[var(--text-dim)] text-sm">Çiftçi kaydı yok</div>}
        </div>

        {/* Parsel kartı → çapraz navigasyon */}
        <div
          className="card card-hover p-5 cursor-pointer"
          role="button" tabIndex={0}
          data-testid="contract-parcel-card"
          onClick={() => c.parcel && nav(`/parseller/${c.parcel.id}`)}
          onKeyDown={(e) => { if (e.key === "Enter" && c.parcel) nav(`/parseller/${c.parcel.id}`); }}
          title="Parsel detayına git"
        >
          <div className="flex items-center gap-2 text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">
            <MapIcon size={14} /> Parsel
          </div>
          {c.parcel ? (
            <>
              <div className="font-medium">{c.parcel.name}</div>
              <div className="text-xs text-[var(--text-dim)] mt-1">
                {parcelKonum || c.parcel.parcel_code}
                {c.parcel.ada_no ? ` · Ada ${c.parcel.ada_no} Parsel ${c.parcel.parsel_no_tapu || "?"}` : ""}
              </div>
              <div className="text-xs text-[var(--text-dim)] mt-1">
                {c.parcel.area_dekar} dekar
                {c.parcel.ekim_durumu ? ` · ${c.parcel.ekim_durumu}` : ""}
              </div>
            </>
          ) : <div className="text-[var(--text-dim)] text-sm">Parsel kaydı yok</div>}
        </div>

        {/* Kota kartı */}
        <div className="card p-5">
          <div className="flex items-center gap-2 text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">
            <Scale size={14} /> Kota
          </div>
          <div className="font-display text-2xl">{c.kota_ton} <span className="text-sm text-[var(--text-dim)]">ton</span></div>
          <div className="text-xs text-[var(--text-dim)] mt-1">{c.kota_dekar} dekar taahhüt</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="card p-5">
          <h3 className="font-display text-lg mb-3">Sözleşme Bilgileri</h3>
          <InfoRow label="Sözleşme Türü" value={c.sozlesme_turu} />
          <InfoRow label="Fabrika Temsilcisi" value={c.fabrika_temsilcisi} />
          <InfoRow label="Noter Onaylı" value={c.noter_onayli_mi === true ? "Evet" : c.noter_onayli_mi === false ? "Hayır" : null} />
          <InfoRow label="İmza Tarihi" value={c.imza_tarihi} />
          <InfoRow label="Tohum Avansı" value={c.advance_seed_kg ? `${c.advance_seed_kg} kg` : null} />
          <InfoRow label="Gübre Avansı" value={c.advance_fertilizer_kg ? `${c.advance_fertilizer_kg} kg` : null} />
          <InfoRow label="Oluşturulma" value={c.created_at?.slice(0, 10)} />
        </div>
        <div className="card p-5">
          <h3 className="font-display text-lg mb-3">Prim / Kesinti & Teslim</h3>
          <InfoRow label="Prim Oranı" value={c.prim_orani_yuzde != null ? `%${c.prim_orani_yuzde}` : null} />
          <InfoRow label="Prim Tutarı" value={c.prim_tutari} />
          <InfoRow label="Kesinti Oranı" value={c.kesinti_orani_yuzde != null ? `%${c.kesinti_orani_yuzde}` : null} />
          <InfoRow label="Kesinti Açıklama" value={c.kesinti_aciklama} />
          <InfoRow label="Teslim Fabrikası" value={c.teslim_fabrika} />
          <InfoRow label="Planlanan Teslim" value={c.teslim_tarihi_planlanan} />
          <InfoRow label="Nakliye Sorumlusu" value={c.nakliye_sorumlusu} />
        </div>
      </div>

      <div className="card p-5 mb-6" data-testid="contract-plantings-card">
        <h3 className="font-display text-lg mb-3 flex items-center gap-2">
          <Sprout size={17} /> Bağlı Ekim Kayıtları ({(c.plantings || []).length})
        </h3>
        {(c.plantings || []).length === 0 ? (
          <p className="text-[var(--text-dim)] text-sm">Bu sözleşmeye bağlı ekim kaydı yok.</p>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-3">Çeşit</th><th className="p-3">Ekim Tarihi</th><th className="p-3">Beklenen Hasat</th><th className="p-3">Aşama</th>
            </tr></thead>
            <tbody>
              {c.plantings.map((p) => (
                <tr key={p.id}
                    className="border-b border-[var(--border)] hover:bg-[var(--surface-2)] cursor-pointer"
                    onClick={() => nav(`/ekim?parcel=${p.parcel_id}`)}
                    title="Ekim Kaydı sayfasında aç">
                  <td className="p-3">{p.variety}</td>
                  <td className="p-3 text-[var(--text-dim)]">{p.planting_date}</td>
                  <td className="p-3 text-[var(--text-dim)]">{p.expected_harvest_date}</td>
                  <td className="p-3"><span className="badge badge-neutral">{p.stage}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {(c.kantar_records || []).length > 0 && (
        <div className="card p-5" data-testid="contract-kantar-card">
          <h3 className="font-display text-lg mb-3 flex items-center gap-2">
            <Scale size={17} /> Kantar Kayıtları ({c.kantar_records.length})
          </h3>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
              <th className="p-3">Fiş No</th><th className="p-3">Tartım</th><th className="p-3">Net (ton)</th><th className="p-3">Polar</th><th className="p-3">Kalite</th>
            </tr></thead>
            <tbody>
              {c.kantar_records.map((k) => (
                <tr key={k.id} className="border-b border-[var(--border)]">
                  <td className="p-3 font-mono text-xs">{k.fis_no}</td>
                  <td className="p-3 text-[var(--text-dim)]">{k.weighing_at?.slice(0, 10)}</td>
                  <td className="p-3">{k.net_ton}</td>
                  <td className="p-3">%{k.polar_oran}</td>
                  <td className="p-3"><span className="badge badge-neutral">{k.kalite}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
