/**
 * KARNE DETAYI — "Neden bu skoru aldı?" (SON HAL) — route /karne/:farmerId
 *
 * backend/karne_engine.py'nin breakdown ucunu tüketir: skor bileşen bileşen
 * (ham veri + ağırlık + katkı + açıklama) gösterilir. Yetkili kullanıcı
 * (karne:manage) ağırlıkları düzenleyip tüm skorları yeniden hesaplatabilir.
 * Çiftçi listesi/detayındaki tüm karne rozetleri buraya tıklanır.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "@/api";
import Breadcrumb from "@/components/Breadcrumb";
import { Award, RefreshCw, SlidersHorizontal, AlertTriangle } from "lucide-react";

const LETTER_BADGE = { A: "badge-a", B: "badge-b", C: "badge-c", D: "badge-d" };

export default function KarneDetail() {
  const { farmerId } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [params, setParams] = useState(null);
  const [editWeights, setEditWeights] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => {
    api.get(`/karne/${farmerId}/breakdown`)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.response?.data?.detail || "Karne yüklenemedi"));
    api.get("/karne/parameters").then((r) => setParams(r.data)).catch(() => {});
  };
  useEffect(load, [farmerId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function recompute() {
    if (!window.confirm("TÜM çiftçilerin karne skorları gerçek verilerden yeniden hesaplanacak.\nMevcut skorlar değişebilir. Devam edilsin mi?")) return;
    setBusy(true); setMsg("");
    try {
      const { data: r } = await api.post("/karne/recompute");
      setMsg(`${r.updated} çiftçi güncellendi (A:${r.letters.A} B:${r.letters.B} C:${r.letters.C} D:${r.letters.D}).`);
      load();
    } catch (e) {
      setMsg(e.response?.data?.detail || "Yeniden hesaplama başarısız (yetkiniz olmayabilir).");
    } finally {
      setBusy(false);
    }
  }

  async function saveWeights() {
    setBusy(true); setMsg("");
    try {
      const weights = Object.fromEntries(
        Object.entries(editWeights).map(([k, v]) => [k, Number(v)]));
      await api.put("/karne/parameters", { weights });
      setEditWeights(null);
      setMsg("Ağırlıklar kaydedildi — skorların güncellenmesi için 'Yeniden Hesapla' çalıştırın.");
      load();
    } catch (e) {
      setMsg(e.response?.data?.detail || "Kaydedilemedi (yetkiniz olmayabilir).");
    } finally {
      setBusy(false);
    }
  }

  if (error) return <div className="p-10 text-[var(--danger)]">{error}</div>;
  if (!data) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const weights = params?.weights || {};

  return (
    <div className="p-8 max-w-[1100px]" data-testid="karne-detail-page">
      <Breadcrumb items={[
        { label: "Çiftçiler", to: "/ciftciler" },
        { label: data.farmer.full_name, to: `/ciftciler/${data.farmer.id}` },
        { label: "Karne" },
      ]} />

      <header className="mb-6 flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">KARNE ANALİZİ</div>
          <h1 className="font-display text-3xl flex items-center gap-3">
            <Award size={26} className="text-[var(--primary)]" /> {data.farmer.full_name}
          </h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            {data.farmer.member_no} · {data.farmer.village || "—"}
          </p>
        </div>
        <div className="card p-4 flex items-center gap-4">
          <div className="text-center">
            <div className="font-display text-4xl">{data.points}</div>
            <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider">Canlı Hesap</div>
          </div>
          <span className={`badge ${LETTER_BADGE[data.letter] || "badge-neutral"} text-lg px-3 py-1`}
                data-testid="karne-live-letter">{data.letter}</span>
        </div>
      </header>

      {data.stored_is_stale && (
        <div className="card p-3 mb-4 text-sm flex items-center gap-2 border-l-4 border-[var(--warning,#F59E0B)]"
             data-testid="karne-stale-warning">
          <AlertTriangle size={15} className="text-[var(--warning,#F59E0B)] shrink-0" />
          <span>
            Kayıtlı skor (<b>{data.stored_letter} · {data.stored_points}</b>) canlı hesaptan farklı —
            kayıtlı skor henüz eski (seed) değeri taşıyor olabilir. Tüm skorları gerçek veriye
            çekmek için "Yeniden Hesapla" çalıştırın.
          </span>
        </div>
      )}

      <div className="card overflow-hidden mb-6" data-testid="karne-components">
        <div className="p-4 border-b border-[var(--border)]">
          <h3 className="font-display text-lg">Skor Bileşenleri — bu skor neden {data.points}?</h3>
          <p className="text-xs text-[var(--text-dim)] mt-1">
            Verisi olmayan bileşen cezalandırılmaz — hesaptan çıkarılır ve kalan ağırlıklar
            yeniden dağıtılır ("etkin ağırlık" kolonu).
          </p>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Bileşen</th><th className="p-4">Ham Veri</th>
            <th className="p-4">Bileşen Puanı</th><th className="p-4">Etkin Ağırlık</th>
            <th className="p-4">Katkı</th>
          </tr></thead>
          <tbody>
            {data.components.map((c) => (
              <tr key={c.key} className={`border-b border-[var(--border)] ${!c.has_data ? "opacity-50" : ""}`}>
                <td className="p-4">
                  <div className="font-medium">{c.label}</div>
                  <div className="text-xs text-[var(--text-dim)] mt-0.5">{c.explanation}</div>
                </td>
                <td className="p-4 text-[var(--text-dim)]">{c.raw ?? "veri yok"}</td>
                <td className="p-4">
                  {c.has_data ? (
                    <div className="flex items-center gap-2">
                      <div className="w-20 h-1.5 rounded bg-[var(--surface-2)] overflow-hidden">
                        <div className="h-full bg-[var(--primary)]" style={{ width: `${c.score}%` }} />
                      </div>
                      <span>{c.score}</span>
                    </div>
                  ) : "—"}
                </td>
                <td className="p-4">{c.has_data ? `%${c.effective_weight}` : "—"}</td>
                <td className="p-4 font-medium">{c.contribution != null ? `+${c.contribution}` : "—"}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-[var(--surface-2)]">
              <td className="p-4 font-medium" colSpan={4}>TOPLAM</td>
              <td className="p-4 font-display text-lg">{data.points}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="flex items-center gap-3 flex-wrap mb-4">
        <button className="btn btn-primary" onClick={recompute} disabled={busy}
                data-testid="karne-recompute">
          <RefreshCw size={15} /> {busy ? "Hesaplanıyor…" : "Tüm Skorları Yeniden Hesapla"}
        </button>
        {!editWeights && (
          <button className="btn btn-ghost" onClick={() => setEditWeights({ ...weights })}
                  data-testid="karne-edit-weights">
            <SlidersHorizontal size={15} /> Ağırlıkları Düzenle
          </button>
        )}
        {msg && <span className="text-sm text-[var(--primary)]" data-testid="karne-msg">{msg}</span>}
      </div>

      {editWeights && (
        <div className="card p-4" data-testid="karne-weights-panel">
          <h3 className="font-display text-lg mb-3">Bileşen Ağırlıkları (parametrik)</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Object.entries(editWeights).map(([k, v]) => (
              <div key={k}>
                <label className="text-xs text-[var(--text-dim)] block mb-1">
                  {params?.labels?.[k] || data.components.find((c) => c.key === k)?.label || k}
                </label>
                <input className="input" type="number" step="1" min="0" value={v}
                       onChange={(e) => setEditWeights({ ...editWeights, [k]: e.target.value })} />
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-3">
            <button className="btn btn-primary" onClick={saveWeights} disabled={busy}>Kaydet</button>
            <button className="btn btn-ghost" onClick={() => setEditWeights(null)}>Vazgeç</button>
          </div>
        </div>
      )}
    </div>
  );
}
