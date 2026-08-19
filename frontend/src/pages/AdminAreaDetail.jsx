/**
 * İDARİ ALAN DETAYI — route /idari-alanlar/:id
 *
 * Kullanıcı isteği (2026-08-19): haritadan il/ilçe/mahalle'ye tıklanınca
 * "demografik veri sayfası (harita görüntüsü + eklediğimiz demografik
 * veriler)" açılsın.
 *
 * Veri kaynağı: `GET /admin-areas/{id}` (tam hassasiyetli geometri) ve
 * `GET /admin-areas/{id}/summary` (sınır içindeki gerçek çiftçi/parsel
 * sayısı — $geoIntersects ile hesaplanır, isim eşleşmesiyle DEĞİL).
 * Alan etiketleri backend'deki DEMOGRAPHIC_LABELS ile aynı sırada tutulur.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, Polygon } from "react-leaflet";
import api from "@/api";
import { getBasemapUrl } from "@/lib/theme";
import { ArrowLeft, Users, MapPin, Landmark, Sprout, Tractor, Beef } from "lucide-react";

const GROUPS = [
  {
    title: "Kimlik", icon: Landmark,
    fields: [["il_adi", "İl"], ["ilce_adi", "İlçe"], ["mahalle_adi", "Mahalle"],
             ["display_name", "Tam Ad"], ["bolge_adi", "Bölge"],
             ["il_plaka", "İl Plaka"], ["ilce_kodu", "İlçe Kodu"], ["mahalle_kodu", "Mahalle Kodu"]],
  },
  {
    title: "Demografi", icon: Users,
    fields: [["nufus_toplam", "Toplam Nüfus"], ["hane_sayisi", "Hane Sayısı"],
             ["hane_kisi_sayisi", "Hane Başına Kişi"], ["kirsalsal_yerlesim", "Yerleşim Sınıfı"],
             ["kirsal_nufus_orani_yuzde", "Kırsal Nüfus Oranı (%)"],
             ["yas_0_17_yuzde", "Yaş 0-17 (%)"], ["yas_18_49_yuzde", "Yaş 18-49 (%)"],
             ["yas_50_64_yuzde", "Yaş 50-64 (%)"], ["yas_65_ustu_yuzde", "Yaş 65+ (%)"],
             ["egitim_ilkokul_yuzde", "Eğitim: İlkokul (%)"],
             ["egitim_orta_lise_yuzde", "Eğitim: Orta/Lise (%)"],
             ["egitim_yuksekogretim_yuzde", "Eğitim: Yükseköğretim (%)"],
             ["hane_aylik_gelir_tl", "Hane Aylık Gelir (TL)"], ["gelir_seviyesi_grubu", "Gelir Seviyesi"]],
  },
  {
    title: "Tarımsal Profil", icon: Sprout,
    fields: [["kayitli_cks_ciftci_sayisi", "Kayıtlı ÇKS Çiftçi"],
             ["ciftci_yas_ortalamasi", "Çiftçi Yaş Ortalaması"],
             ["kadin_ciftci_orani_yuzde", "Kadın Çiftçi Oranı (%)"],
             ["tarimsal_istihdam_orani_yuzde", "Tarımsal İstihdam (%)"],
             ["islenen_tarim_arazisi_dekar", "İşlenen Tarım Arazisi (dekar)"],
             ["traktor_sayisi", "Traktör Sayısı"], ["baskin_urun_grubu", "Baskın Ürün Grubu"],
             ["birinci_ana_urun", "1. Ana Ürün"], ["birinci_urun_rekolte_ton", "1. Ürün Rekolte (ton)"],
             ["ikinci_ana_urun", "2. Ana Ürün"], ["ikinci_urun_rekolte_ton", "2. Ürün Rekolte (ton)"],
             ["ucuncu_ana_urun", "3. Ana Ürün"], ["ucuncu_urun_rekolte_ton", "3. Ürün Rekolte (ton)"]],
  },
  {
    title: "Hayvancılık", icon: Beef,
    fields: [["buyukbas_hayvan_sayisi", "Büyükbaş Hayvan"], ["kucukbas_hayvan_sayisi", "Küçükbaş Hayvan"]],
  },
];

const fmt = (v) => (v == null || v === ""
  ? "—"
  : typeof v === "number" ? new Intl.NumberFormat("tr-TR").format(v) : v);

function centerOf(geometry) {
  const pts = [];
  (function walk(c) {
    if (typeof c[0] === "number") pts.push(c);
    else c.forEach(walk);
  })(geometry?.coordinates || []);
  if (!pts.length) return [39.5, 33.5];
  return [pts.reduce((s, p) => s + p[1], 0) / pts.length,
          pts.reduce((s, p) => s + p[0], 0) / pts.length];
}

export default function AdminAreaDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [area, setArea] = useState(null);
  const [summary, setSummary] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get(`/admin-areas/${id}`).then((r) => setArea(r.data))
      .catch((e) => setErr(e.response?.data?.detail || "İdari alan bulunamadı"));
    api.get(`/admin-areas/${id}/summary`).then((r) => setSummary(r.data)).catch(() => {});
  }, [id]);

  if (err) return <div className="p-8"><div className="card p-6 text-sm text-red-400">{err}</div></div>;
  if (!area) return <div className="p-8"><div className="card p-6 text-sm text-[var(--text-dim)]">Yükleniyor…</div></div>;

  const rings = area.geometry
    ? (area.geometry.type === "MultiPolygon" ? area.geometry.coordinates.flat() : area.geometry.coordinates)
    : [];
  const typeLabel = { il: "İl", ilce: "İlçe", mahalle: "Mahalle/Köy" }[area.area_type] || area.area_type;

  return (
    <div className="p-8 max-w-[1500px]" data-testid="admin-area-detail">
      <button onClick={() => nav(-1)} className="btn btn-ghost text-xs mb-4">
        <ArrowLeft size={13} /> Geri
      </button>

      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">
          {typeLabel.toUpperCase()}
        </div>
        <h1 className="font-display text-4xl">{area.display_name || area.name}</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          {[area.il_adi, area.ilce_adi, area.mahalle_adi].filter(Boolean).join(" › ")}
        </p>
      </header>

      {/* Sınır içindeki GERÇEK operasyon verisi ($geoIntersects) */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          {[[Users, "Sistemdeki Çiftçi", summary.farmer_count],
            [MapPin, "Sistemdeki Parsel", summary.parcel_count],
            [Sprout, "Kayıtlı ÇKS Çiftçi", area.kayitli_cks_ciftci_sayisi],
            [Tractor, "Traktör", area.traktor_sayisi]].map(([Icon, label, value]) => (
            <div key={label} className="card p-4">
              <Icon size={16} className="text-[var(--primary)] mb-2" />
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">{label}</div>
              <div className="font-display text-2xl mt-1">{fmt(value)}</div>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* HARİTA */}
        <div className="card overflow-hidden" style={{ minHeight: 380 }}>
          {rings.length > 0 ? (
            <MapContainer center={centerOf(area.geometry)} zoom={area.area_type === "il" ? 8 : area.area_type === "ilce" ? 10 : 13}
                          style={{ height: 420, width: "100%" }} scrollWheelZoom>
              <TileLayer url={getBasemapUrl()} />
              {rings.map((ring, i) => (
                <Polygon key={i} positions={ring.map(([lng, lat]) => [lat, lng])}
                         pathOptions={{ color: "#4ade80", weight: 2, fillOpacity: 0.12 }} />
              ))}
            </MapContainer>
          ) : (
            <div className="p-6 text-sm text-[var(--text-dim)]">Bu alan için sınır geometrisi yok.</div>
          )}
        </div>

        {/* DEMOGRAFİK VERİLER */}
        <div className="space-y-4">
          {GROUPS.map(({ title, icon: Icon, fields }) => {
            const rows = fields.filter(([k]) => area[k] != null && area[k] !== "");
            if (!rows.length) return null;
            return (
              <div key={title} className="card p-4">
                <h3 className="font-display text-lg mb-2 flex items-center gap-2">
                  <Icon size={16} className="text-[var(--primary)]" /> {title}
                </h3>
                <div className="grid gap-1 sm:grid-cols-2">
                  {rows.map(([k, label]) => (
                    <div key={k} className="flex items-center justify-between text-sm py-1 border-b border-[var(--border)]">
                      <span className="text-[var(--text-dim)]">{label}</span>
                      <b>{fmt(area[k])}</b>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
