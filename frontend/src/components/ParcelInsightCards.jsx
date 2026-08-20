/**
 * ParcelInsightCards — parsel detayında karar destek ölçümleri.
 *
 * Dört kart TEK bileşende toplandı çünkü hepsi aynı deseni izliyor:
 * "uç noktayı çağır → yoksa dürüst boş durum → varsa özet + detay".
 * Ayrı dosyalara bölmek dört kez aynı iskeleti yazmak olurdu.
 *
 * Kartlar TAVSİYE ÜRETMEZ — sunucudan geleni gösterir (tavsiye üretimi
 * season_planner.py'nin işi). Burada sadece ölçüm ve özet var.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import {
  Sun, Droplets, Leaf, Wind, RefreshCw, AlertTriangle, TrendingUp, Sprout, Flame,
} from "lucide-react";

function Card({ icon: Icon, title, subtitle, children, action }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3 gap-2">
        <div className="flex items-center gap-2">
          <Icon size={16} className="text-[var(--primary)]" />
          <div>
            <h3 className="font-display text-base">{title}</h3>
            {subtitle && <div className="text-[11px] text-[var(--text-dim)]">{subtitle}</div>}
          </div>
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function Row({ label, value, hint }) {
  return (
    <div className="flex items-center justify-between text-sm py-1 border-b border-[var(--border)] last:border-0">
      <span className="text-[var(--text-dim)]" title={hint}>{label}</span>
      <b>{value ?? "—"}</b>
    </div>
  );
}

function Empty({ text }) {
  return <div className="text-xs text-[var(--text-dim)] py-3">{text}</div>;
}

export default function ParcelInsightCards({ parcelId }) {
  const nav = useNavigate();
  const [solar, setSolar] = useState(null);
  const [water, setWater] = useState(null);
  const [carbon, setCarbon] = useState(null);
  const [bio, setBio] = useState(null);
  const [stand, setStand] = useState(null);
  const [fire, setFire] = useState(null);
  const [solarBusy, setSolarBusy] = useState(false);

  useEffect(() => {
    if (!parcelId) return;
    api.get(`/solar/parcels/${parcelId}`).then((r) => setSolar(r.data)).catch(() => setSolar(null));
    api.get(`/water-budget/parcels/${parcelId}`).then((r) => setWater(r.data)).catch(() => setWater(null));
    api.get(`/sustainability/parcels/${parcelId}`).then((r) => setCarbon(r.data)).catch(() => setCarbon(null));
    api.get("/soil-biology", { params: { parcel_id: parcelId, limit: 1 } })
      .then((r) => setBio((r.data || [])[0] || null)).catch(() => setBio(null));
    api.get(`/crop-stand/parcels/${parcelId}`).then((r) => setStand(r.data)).catch(() => setStand(null));
    // 20 km yangın bariyeri (2026-08-19) — NASA FIRMS
    api.get(`/satellite/fire-alerts/${parcelId}`, { params: { days: 3, radius_km: 20 } })
      .then((r) => setFire(r.data)).catch(() => setFire(null));
  }, [parcelId]);

  const refreshSolar = () => {
    setSolarBusy(true);
    api.get(`/solar/parcels/${parcelId}`, { params: { yenile: true } })
      .then((r) => setSolar(r.data)).finally(() => setSolarBusy(false));
  };

  return (
    <div className="grid gap-4 md:grid-cols-2 mb-4" data-testid="parcel-insight-cards">
      {/* GÜNEŞ & GÖLGE */}
      <Card icon={Sun} title="Güneş & Gölge" subtitle="Copernicus DEM GLO-30 · saatlik gölge profili"
            action={
              <button className="btn btn-ghost text-xs" onClick={refreshSolar} disabled={solarBusy}>
                <RefreshCw size={12} className={solarBusy ? "animate-spin" : ""} /> Yenile
              </button>
            }>
        {!solar?.available ? (
          <Empty text={solar?.reason || "Güneş analizi henüz yapılmadı."} />
        ) : (
          <>
            <Row label="Günlük etkin güneşlenme" value={`${solar.gunes_saati_gunluk} saat`} />
            <Row label="İhtiyacın karşılanması"
                 value={`%${solar.yeterlilik?.karsilanma_yuzde} (${solar.yeterlilik?.durum})`}
                 hint={`Bu ürün için gerekli: ${solar.yeterlilik?.gerekli_saat} saat/gün`} />
            <Row label="Bakı / eğim"
                 value={`${solar.arazi?.baki || "—"} · %${solar.arazi?.egim_yuzde ?? "—"}`} />
            <Row label="Rakım" value={solar.arazi?.yukseklik_m ? `${solar.arazi.yukseklik_m} m` : "—"} />
            <Row label="Ortalama gölge oranı" value={`%${solar.ortalama_golge_orani_yuzde}`} />
            {/* Saatlik gölge şeridi — koyu = gölge */}
            <div className="flex gap-0.5 mt-3">
              {(solar.saatlik || []).map((h) => (
                <div key={h.saat} className="flex-1 text-center" title={`${h.saat}:00 — gölge %${h.golge_orani_yuzde ?? 100}`}>
                  <div style={{
                    height: 26,
                    background: h.gunes_var
                      ? `rgba(250, 204, 21, ${Math.max(0.12, 1 - (h.golge_orani_yuzde || 0) / 100)})`
                      : "var(--surface-2)",
                    borderRadius: 3,
                  }} />
                  <div className="text-[9px] text-[var(--text-dim)] mt-0.5">{h.saat}</div>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>

      {/* SU BÜTÇESİ */}
      <Card icon={Droplets} title="Su Bütçesi" subtitle="FAO-56 · ET0 × Kc − etkili yağış">
        {!water?.available ? (
          <Empty text={water?.reason || "Su bütçesi hesaplanamadı."} />
        ) : (
          <>
            <Row label="Fenolojik aşama / Kc" value={`${water.fenolojik_asama} · ${water.kc}`} />
            <Row label="Toprak su kapasitesi (TAW)" value={`${water.kapasite?.taw_mm} mm`}
                 hint={`Toprak dokusu: ${water.toprak?.doku}${water.toprak?.laboratuvardan ? " (laboratuvardan)" : " (varsayım)"}`} />
            <Row label="Kritik eşik (RAW)" value={`${water.kapasite?.raw_mm} mm`} />
            <Row label="Güncel su açığı" value={`${water.kapasite?.guncel_acik_mm} mm`} />
            <div className={`mt-3 p-3 rounded-lg text-sm ${
              water.oneri?.aciliyet === "acil" ? "bg-red-500/10 text-red-300"
                : water.oneri?.aciliyet === "yaklasiyor" ? "bg-amber-500/10 text-amber-300"
                : "bg-emerald-500/10 text-emerald-300"}`}>
              <div className="font-medium">{water.oneri?.mesaj}</div>
              {water.oneri?.sulama_gerekli && (
                <div className="text-xs mt-1">
                  Net {water.oneri.net_ihtiyac_mm} mm · brüt {water.oneri.brut_ihtiyac_mm} mm
                  {water.oneri.brut_ihtiyac_m3 != null && ` (${water.oneri.brut_ihtiyac_m3} m³)`}
                </div>
              )}
            </div>
            {water.varsayimlar?.length > 0 && (
              <div className="text-[11px] text-[var(--text-dim)] mt-2">
                <AlertTriangle size={11} className="inline mr-1" />
                {water.varsayimlar.join(" · ")}
              </div>
            )}
          </>
        )}
      </Card>

      {/* KÖK SAYISI */}
      <Card icon={Sprout} title="Bitki Sıklığı / Kök Sayısı" subtitle="Ekim geometrisinden hesaplanır">
        {!stand?.available ? (
          <Empty text={stand?.reason || "Bu parselde ekim kaydı yok."} />
        ) : (
          <>
            <Row label="Ürün / çeşit" value={`${stand.crop || "—"} · ${stand.variety || "—"}`} />
            <Row label="Sıra arası × sıra üzeri"
                 value={`${stand.sira_arasi_cm} × ${stand.sira_uzeri_cm} cm`} />
            <Row label="Çimlenme oranı" value={stand.cimlenme_yuzde ? `%${stand.cimlenme_yuzde}` : "—"} />
            <Row label="Hesaplanan bitki/dekar" value={stand.hesaplanan_bitki_dekar?.toLocaleString("tr-TR")} />
            <Row label="Toplam kök sayısı" value={stand.kayitli_toplam_kok?.toLocaleString("tr-TR")}
                 hint={`Kaynak: ${stand.kaynak}`} />
            <Row label="Çıkış düzgünlüğü" value={stand.cikis_duzgunlugu_yuzde ? `%${stand.cikis_duzgunlugu_yuzde}` : "—"}
                 hint={`Hedef: ${stand.hedef_bitki_dekar?.toLocaleString("tr-TR")} bitki/dekar`} />
            <Row label="Tohum ihtiyacı" value={stand.tohum_ihtiyaci_kg ? `${stand.tohum_ihtiyaci_kg} kg` : "—"} />
          </>
        )}
      </Card>

      {/* KARBON — 2026-08-20: "Detaylı Rapor" ile parsele özel tam sayfaya
          gider (bkz. pages/ParcelCarbonDetail.jsx — bu kart ilk 3 kalemi/
          önerileri özetliyor, tam sayfa TÜM kalemleri + sezon karşılaştırmasını gösterir). */}
      <Card icon={Wind} title="Karbon Ayak İzi" subtitle="IPCC 2019 + tarımsal LCA — tahmindir"
            action={
              <button className="btn btn-ghost text-[10px] px-2 py-1"
                      onClick={() => nav(`/parseller/${parcelId}/karbon`)} data-testid="carbon-detail-link">
                Detaylı Rapor →
              </button>
            }>
        {!carbon?.ayak_izi ? (
          <Empty text="Karbon hesabı yapılamadı." />
        ) : (
          <>
            <Row label="Toplam" value={`${carbon.ayak_izi.toplam_kg_co2e?.toLocaleString("tr-TR")} kg CO₂e`} />
            <Row label="Dekar başına" value={`${carbon.ayak_izi.dekar_basina_kg_co2e} kg CO₂e`} />
            {carbon.ayak_izi.ton_urun_basina_kg_co2e != null && (
              <Row label="Ton ürün başına" value={`${carbon.ayak_izi.ton_urun_basina_kg_co2e} kg CO₂e`} />
            )}
            <div className="mt-2 space-y-1">
              {carbon.ayak_izi.kalemler?.slice(0, 3).map((k) => (
                <div key={k.kalem} className="flex items-center gap-2 text-xs">
                  <div className="flex-1 truncate text-[var(--text-dim)]">{k.kalem}</div>
                  <div className="w-24 h-1.5 bg-[var(--surface-2)] rounded">
                    <div style={{
                      width: `${Math.min(100, k.kg_co2e / carbon.ayak_izi.toplam_kg_co2e * 100)}%`,
                      height: "100%", background: "var(--primary)", borderRadius: 3,
                    }} />
                  </div>
                  <b className="w-20 text-right">{k.kg_co2e} kg</b>
                </div>
              ))}
            </div>
            {carbon.oneriler?.length > 0 && (
              <div className="mt-3 pt-2 border-t border-[var(--border)]">
                <div className="text-xs font-medium mb-1 flex items-center gap-1">
                  <TrendingUp size={12} /> İyileştirme önerileri
                </div>
                {carbon.oneriler.map((o, i) => (
                  <div key={i} className="text-[11px] text-[var(--text-dim)] mb-1">
                    <b className="text-[var(--text)]">{o.baslik}</b> — {o.kazanc_kg_co2e} kg CO₂e kazanç
                    {o.kazanc_tl_tahmini ? ` · ~${o.kazanc_tl_tahmini.toLocaleString("tr-TR")} TL` : ""}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </Card>

      {/* YANGIN BARİYERİ — 20 km (NASA FIRMS) */}
      <Card icon={Flame} title="Yangın Bariyeri (20 km)"
            subtitle="NASA FIRMS · son 3 gün · parsel merkezine uzaklık">
        {!fire ? (
          <Empty text="Yangın verisi alınamadı." />
        ) : fire.alerts?.length === 0 ? (
          <div className="text-sm text-emerald-300 py-3">
            20 km çevrede aktif yangın yok.
            {fire.provider === "demo" && (
              <div className="text-[11px] text-[var(--text-dim)] mt-1">
                NASA FIRMS anahtarı girilmemiş — demo modda çalışıyor
                (Ayarlar › Entegrasyonlar › NASA FIRMS).
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="p-3 rounded-lg bg-red-500/10 text-red-300 text-sm mb-2">
              <b>{fire.alerts.length} yangın</b> 20 km bariyeri içinde ·
              en yakını <b>{fire.en_yakin_km} km</b>
            </div>
            <div className="space-y-1 max-h-[180px] overflow-y-auto scrollbar">
              {fire.alerts.slice(0, 12).map((a, i) => (
                <div key={i} className="flex items-center justify-between text-xs py-1 border-b border-[var(--border)]">
                  <span className="text-[var(--text-dim)]">
                    {a.acq_date || a.tarih || "—"} · {a.yon}
                  </span>
                  <b>{a.mesafe_km} km</b>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>

      {/* TOPRAK BİYOLOJİSİ */}
      <Card icon={Leaf} title="Toprak Biyolojisi" subtitle="Mikroorganizma envanteri ve sağlık skoru">
        {!bio ? (
          <Empty text="Bu parselde toprak biyolojisi analizi yok — 'Toprak Biyolojisi' ekranından ekleyebilirsiniz." />
        ) : (
          <>
            <Row label="Örnek tarihi" value={bio.sample_date} />
            <Row label="Toprak sağlığı skoru"
                 value={`${bio.saglik_skoru?.skor ?? "—"} / 100 (${bio.saglik_skoru?.sinif || "—"})`} />
            <Row label="Ölçüm kapsamı" value={`%${bio.saglik_skoru?.kapsam_yuzde}`} />
            <Row label="Mikrobiyal biyokütle" value={bio.mikrobiyal_biyokutle_c ? `${bio.mikrobiyal_biyokutle_c} mg/kg` : "—"} />
            <Row label="Solucan" value={bio.solucan_sayisi_m2 ? `${bio.solucan_sayisi_m2} adet/m²` : "—"} />
            {bio.saglik_skoru?.engelleyici_organizmalar?.length > 0 && (
              <div className="mt-2 p-2 rounded bg-red-500/10 text-red-300 text-xs">
                <AlertTriangle size={12} className="inline mr-1" />
                Engelleyici: {bio.saglik_skoru.engelleyici_organizmalar.join(", ")}
              </div>
            )}
            {bio.organizmalar?.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {bio.organizmalar.filter((o) => o.tespit_edildi).map((o, i) => (
                  <span key={i} className="badge badge-neutral text-[10px]">{o.organism_key}</span>
                ))}
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
