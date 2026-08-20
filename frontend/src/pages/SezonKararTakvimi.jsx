/**
 * SEZON KARAR TAKVİMİ — ekim öncesinden hasada karar desteği.
 *
 * Backend: backend/season_planner.py. Bu ekran KENDİ tavsiye mantığını
 * İÇERMEZ — kararları sunucudan alır, gösterir ve kabul edilenleri geri
 * yollar (kabul edilen karar mevcut Saha Görevi / sulama kaydına yazılır).
 *
 * Tasarım: mevcut ekranların kartlarıyla aynı görsel dil (card/btn/badge),
 * yeni bir tasarım dili İCAT EDİLMEZ (CLAUDE.md konvansiyon #9).
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/api";
import ParcelPicker from "@/components/ParcelPicker";
import ParcelDecisionPanel from "@/components/ParcelDecisionPanel";
import {
  CalendarClock, AlertTriangle, Clock, ListChecks, Info, CheckCircle2,
  Droplets, Sun, Leaf, Satellite, ShieldCheck, RefreshCw,
} from "lucide-react";

const ACILIYET = {
  acil: { label: "Acil", cls: "badge-d", icon: AlertTriangle },
  yakin: { label: "Yakında", cls: "badge-c", icon: Clock },
  planla: { label: "Planla", cls: "badge-b", icon: ListChecks },
  bilgi: { label: "Bilgi", cls: "badge-neutral", icon: Info },
};

const KONU_ICON = {
  sulama: Droplets, gunes: Sun, toprak: Leaf, gubreleme: Leaf,
  uydu: Satellite, bitki_sagligi: Satellite, su_stresi: Droplets,
  hastalik: ShieldCheck, hasat: CalendarClock, ekim: Leaf, arazi: Sun,
};

const GUVEN_CLS = { yuksek: "badge-a", orta: "badge-c", dusuk: "badge-d" };

export default function SezonKararTakvimi() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [parcelId, setParcelId] = useState(searchParams.get("parcel") || "");
  const [parcelObj, setParcelObj] = useState(null);
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [staff, setStaff] = useState([]);
  const [assignee, setAssignee] = useState("");
  // Fenolojik şeritte İNCELENEN aşama. null = güncel aşama gösterilir.
  // Şerit daha önce salt-okunur bir durum göstergesiydi; kullanıcı bunu
  // "diğer butonlar pasif" olarak okuduğu için tıklanabilir hale getirildi.
  const [stageKey, setStageKey] = useState(null);

  useEffect(() => {
    api.get("/field-ops/assignable-users").then((r) => setStaff(r.data || [])).catch(() => {});
  }, []);

  const load = (pid) => {
    if (!pid) return;
    setBusy(true);
    setMsg("");
    setStageKey(null);
    api.get(`/season-planner/parcels/${pid}`)
      .then((r) => setPlan(r.data))
      .catch((e) => setMsg(e.response?.data?.detail || "Takvim yüklenemedi."))
      .finally(() => setBusy(false));
  };

  useEffect(() => { if (parcelId) load(parcelId); /* eslint-disable-next-line */ }, [parcelId]);

  async function accept(karar) {
    setMsg("");
    try {
      const { data } = await api.post("/season-planner/accept", {
        parcel_id: parcelId, karar, assigned_to: assignee || undefined,
        planned_date: karar.onerilen_tarih,
      });
      setMsg(`"${karar.baslik}" kabul edildi — ${data.tip === "saha_gorevi" ? "saha görevi" :
        data.tip === "sulama_kaydi" ? "sulama kaydı" : "uydu analizi"} oluşturuldu.`);
      load(parcelId);
    } catch (e) {
      setMsg(e.response?.data?.detail || "Karar uygulanamadı.");
    }
  }

  const guven = plan?.veri_guveni;

  return (
    <div className="p-8 max-w-[1400px]" data-testid="sezon-karar-takvimi">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">KARAR DESTEK</div>
        <h1 className="font-display text-4xl">Sezon Karar Takvimi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Toprak, uydu, güneş, hava ve biyoloji ölçümlerini fenolojik aşamaya göre
          birleştirir; ne yapılacağını gerekçesiyle söyler.
        </p>
      </header>

      <div className="card p-4 mb-4 flex items-end gap-3 flex-wrap">
        <div style={{ minWidth: 320, flex: 1 }}>
          <label className="text-xs text-[var(--text-dim)]">Parsel</label>
          {/* ParcelPicker sözleşmesi: `value` seçili parsel OBJESİ,
              seçim geri çağrısı `onSelect` (null = temizle). */}
          <ParcelPicker
            value={parcelObj}
            onSelect={(p) => {
              setParcelObj(p);
              setParcelId(p?.id || "");
              setSearchParams(p?.id ? { parcel: p.id } : {});
            }}
            testId="season-parcel-picker"
          />
        </div>
        <div>
          <label className="text-xs text-[var(--text-dim)]">Görev atanacak personel</label>
          <select className="input" value={assignee} onChange={(e) => setAssignee(e.target.value)}
                  data-testid="season-assignee" style={{ minWidth: 200 }}>
            <option value="">Seçilmedi</option>
            {staff.map((u) => <option key={u.id} value={u.id}>{u.full_name || u.email}</option>)}
          </select>
        </div>
        <button className="btn btn-ghost text-xs" onClick={() => load(parcelId)} disabled={!parcelId || busy}>
          <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> Yenile
        </button>
      </div>

      {msg && <div className="card p-3 mb-4 text-sm text-[var(--primary)]">{msg}</div>}
      {busy && <div className="card p-6 text-center text-sm text-[var(--text-dim)]">Ölçümler toplanıyor…</div>}

      {/* 2026-08-19 — Karar Paneli (hava + ekim penceresi + polar/söküm).
          ParcelDetail ile AYNI bileşen; bu ekran zaten "sezon kararı" ekranı
          olduğu için tahminlerin ikinci doğal yeri burası. */}
      {parcelId && !busy && (
        <div className="mb-4">
          <ParcelDecisionPanel parcelId={parcelId} planting={plan?.ekim || null} />
        </div>
      )}

      {plan && !busy && (
        <>
          {/* Fenolojik aşama şeridi */}
          <div className="card p-4 mb-4">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
              <div>
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Güncel Aşama</div>
                <div className="font-display text-2xl">{plan.asama?.label}</div>
                <div className="text-xs text-[var(--text-dim)]">{plan.asama?.aciklama}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-[var(--text-dim)]">Büyüme derece-gün birikimi</div>
                <div className="font-display text-2xl">{plan.gdd_birikimi ?? "—"}</div>
              </div>
              {guven && (
                <div className="text-right">
                  <div className="text-xs text-[var(--text-dim)]">Veri güveni</div>
                  <span className={`badge ${GUVEN_CLS[guven.seviye] || "badge-neutral"}`}>
                    %{guven.skor} · {guven.seviye}
                  </span>
                </div>
              )}
            </div>
            <div className="flex gap-1 flex-wrap">
              {(plan.asamalar || []).map((s, i) => {
                const curIdx = (plan.asamalar || []).findIndex((x) => x.key === plan.asama?.key);
                const isCurrent = s.key === plan.asama?.key;
                const isPast = curIdx >= 0 && i < curIdx;
                const isSelected = stageKey === s.key;
                return (
                  <button
                    key={s.key}
                    type="button"
                    onClick={() => setStageKey(isSelected ? null : s.key)}
                    title={s.aciklama}
                    data-testid={`asama-${s.key}`}
                    className={`px-3 py-1.5 rounded-lg text-[11px] transition-colors ${
                      isCurrent
                        ? "bg-[var(--primary)] text-black font-medium"
                        : isPast
                        ? "bg-[var(--surface-2)] text-[var(--text)]"
                        : "bg-[var(--surface-2)] text-[var(--text-dim)]"
                    } ${isSelected ? "ring-2 ring-[var(--primary)]" : "hover:opacity-80"}`}
                  >
                    {isPast && "✓ "}{s.label}
                  </button>
                );
              })}
            </div>

            {/* Şeritten seçilen aşamanın detayı — güncel aşamadan bağımsız
                olarak sezonun herhangi bir dönemini inceleyebilmek için. */}
            {stageKey && (() => {
              const st = (plan.asamalar || []).find((x) => x.key === stageKey);
              if (!st) return null;
              const curIdx = (plan.asamalar || []).findIndex((x) => x.key === plan.asama?.key);
              const stIdx = (plan.asamalar || []).findIndex((x) => x.key === stageKey);
              const durum = stIdx < curIdx ? "Tamamlandı" : stIdx === curIdx ? "Güncel aşama" : "Henüz gelmedi";
              const aralik =
                st.gdd_min == null ? `< ${st.gdd_max} GDD`
                : st.gdd_max == null ? `> ${st.gdd_min} GDD`
                : `${st.gdd_min} – ${st.gdd_max} GDD`;
              return (
                <div className="mt-3 pt-3 border-t border-[var(--border)] flex flex-wrap gap-x-6 gap-y-2 items-start">
                  <div>
                    <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Aşama</div>
                    <div className="font-medium">{st.label}</div>
                  </div>
                  <div>
                    <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">Durum</div>
                    <span className={`badge ${stIdx === curIdx ? "badge-a" : stIdx < curIdx ? "badge-neutral" : "badge-c"}`}>{durum}</span>
                  </div>
                  <div>
                    <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider">GDD aralığı</div>
                    <div className="text-sm">{aralik}</div>
                  </div>
                  <div className="basis-full text-sm text-[var(--text-dim)]">{st.aciklama}</div>
                </div>
              );
            })()}
          </div>

          {/* Veri güven rozeti detayı */}
          {guven && guven.eksik_girdiler?.length > 0 && (
            <div className="card p-4 mb-4 border border-amber-500/30 bg-amber-500/5">
              <div className="text-sm font-medium mb-1 flex items-center gap-2">
                <ShieldCheck size={15} /> Bu tavsiyeler neye dayanıyor?
              </div>
              <div className="text-xs text-[var(--text-dim)] mb-2">{guven.aciklama} {guven.oneri}</div>
              <div className="flex flex-wrap gap-2">
                {guven.girdiler.map((g) => (
                  <span key={g.girdi}
                        className={`badge ${g.durum === "olculdu" ? "badge-a" :
                          g.durum === "tahmin" ? "badge-c" : "badge-neutral"}`}>
                    {g.label}: {g.durum_label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Karar kartları */}
          <div className="flex items-center gap-3 mb-3 text-sm">
            <span className="badge badge-d">{plan.ozet?.acil} acil</span>
            <span className="badge badge-c">{plan.ozet?.yakin} yakında</span>
            <span className="badge badge-b">{plan.ozet?.planla} planla</span>
            <span className="text-[var(--text-dim)]">toplam {plan.ozet?.toplam} karar</span>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            {(plan.kararlar || []).map((k) => {
              const a = ACILIYET[k.aciliyet] || ACILIYET.bilgi;
              const Icon = KONU_ICON[k.konu] || Info;
              return (
                <div key={k.id} className="card p-4" data-testid={`karar-${k.konu}`}>
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2">
                      <Icon size={16} className="text-[var(--primary)]" />
                      <h3 className="font-medium">{k.baslik}</h3>
                    </div>
                    <span className={`badge ${a.cls} shrink-0`}>{a.label}</span>
                  </div>
                  <p className="text-sm text-[var(--text-dim)] mb-2">{k.aciklama}</p>
                  <div className="text-xs text-[var(--text-dim)] mb-2">
                    <div className="font-medium mb-1">Gerekçe (ölçümler):</div>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {(k.gerekce || []).map((g, i) => <li key={i}>{g}</li>)}
                    </ul>
                  </div>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="text-[11px] text-[var(--text-dim)]">
                      Önerilen tarih: {k.onerilen_tarih} · güven %{Math.round((k.guven || 0) * 100)}
                    </div>
                    {k.eylem?.tip && k.eylem.tip !== "yok" && (
                      <button className="btn btn-primary text-xs" onClick={() => accept(k)}
                              data-testid={`karar-kabul-${k.konu}`}>
                        <CheckCircle2 size={13} /> Kabul et ve uygula
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
            {(plan.kararlar || []).length === 0 && (
              <div className="card p-6 text-center text-sm text-[var(--text-dim)]">
                Bu parsel için şu an bir eylem önerisi yok.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
