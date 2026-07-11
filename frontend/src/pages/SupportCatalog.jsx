/**
 * DESTEK KATALOĞU YÖNETİMİ (IT-18 / FAZ 7 — UFYD)
 *
 * Ayarlar altında admin tanımlı destek tipi kataloğu (Mazot/Gübre/Tohum/
 * İlaç/Makine Hizmeti/Sulama/Nakliye/Avans/Diğer). Kod gerektirmez —
 * yeni bir tip burada eklenir, ProductionCycleDetail'deki "Destek
 * Talepleri" formunda otomatik seçenek olarak belirir.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import { QuickAddPanel } from "@/components/QuickAdd";
import { Wallet } from "lucide-react";

export function DestekKatalogu() {
  const [types, setTypes] = useState([]);
  const [seeding, setSeeding] = useState(false);

  const load = () => api.get("/support-types", { params: { include_inactive: true } }).then((r) => setTypes(r.data));
  useEffect(() => { load(); }, []);

  async function seedDefaults() {
    setSeeding(true);
    try {
      await api.post("/support-types/seed-defaults");
      load();
    } finally {
      setSeeding(false);
    }
  }

  async function toggleActive(t) {
    await api.put(`/support-types/${t.id}`, { is_active: !t.is_active });
    load();
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="support-catalog-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">UFYD — AYARLAR</div>
          <h1 className="font-display text-4xl">Destek Kataloğu</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Çiftçilere sağlanan destek tiplerini (Mazot, Gübre, Tohum...) yönetin. Burada tanımlanan
            tipler, Üretim Sezonu ekranındaki "Destek Talepleri" formunda seçenek olarak görünür.
          </p>
        </div>
        {types.length === 0 && (
          <button onClick={seedDefaults} disabled={seeding} className="btn btn-ghost text-sm">
            {seeding ? "Yükleniyor…" : "Varsayılanları Yükle"}
          </button>
        )}
      </header>

      <QuickAddPanel
        title="Yeni Destek Tipi"
        testId="support-type-add"
        fields={[
          { name: "name", label: "Ad", required: true },
          { name: "unit", label: "Birim", required: true, default: "adet" },
          { name: "default_price", label: "Varsayılan Fiyat", type: "number", step: "0.01" },
          { name: "accounting_code", label: "Muhasebe Kodu" },
          { name: "vat_rate", label: "KDV (%)", type: "number", step: "0.01" },
          { name: "deduct_from_stock", label: "Stoktan Düş", type: "select", default: "false",
            options: [{ value: "false", label: "Hayır" }, { value: "true", label: "Evet" }] },
        ]}
        onSubmit={async (v) => {
          await api.post("/support-types", {
            ...v,
            default_price: v.default_price ? Number(v.default_price) : 0,
            vat_rate: v.vat_rate ? Number(v.vat_rate) : 0,
            deduct_from_stock: v.deduct_from_stock === "true",
          });
          load();
        }}
      />

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Ad</th><th className="p-4">Birim</th><th className="p-4">Varsayılan Fiyat</th>
            <th className="p-4">Muhasebe Kodu</th><th className="p-4">Stoktan Düş</th><th className="p-4">KDV</th><th className="p-4">Durum</th>
          </tr></thead>
          <tbody>
            {types.map((t) => (
              <tr key={t.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4 flex items-center gap-2"><Wallet size={14} className="text-[var(--primary)]"/>{t.name}</td>
                <td className="p-4 text-[var(--text-dim)]">{t.unit}</td>
                <td className="p-4">{t.default_price}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{t.accounting_code || "—"}</td>
                <td className="p-4">{t.deduct_from_stock ? "Evet" : "Hayır"}</td>
                <td className="p-4">%{t.vat_rate}</td>
                <td className="p-4">
                  <button onClick={() => toggleActive(t)} className={`badge ${t.is_active === false ? "badge-d" : "badge-a"}`}>
                    {t.is_active === false ? "Pasif" : "Aktif"}
                  </button>
                </td>
              </tr>
            ))}
            {types.length === 0 && (
              <tr><td colSpan="7" className="p-6 text-center text-[var(--text-dim)]">Henüz destek tipi yok</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
