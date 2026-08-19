/**
 * TOPRAK BİYOLOJİSİ — parseldeki canlı organizma envanteri + sağlık skoru.
 *
 * Backend: backend/soil_biology.py. Organizma listesi ve ölçüm alanları
 * `/soil-biology/catalog`'tan gelir — bu ekran HİÇBİR organizma adını veya
 * eşiğini hardcode ETMEZ (tek kaynak ilkesi, indices.py ile aynı disiplin).
 */
import { useEffect, useState } from "react";
import api from "@/api";
import ParcelPicker from "@/components/ParcelPicker";
import { Leaf, Save, FlaskConical, Bug, Trash2 } from "lucide-react";

const ETKI_CLS = { faydali: "badge-a", zararli: "badge-d", notr: "badge-neutral" };
const YOGUNLUK = [["dusuk", "Düşük"], ["orta", "Orta"], ["yuksek", "Yüksek"]];

export default function ToprakBiyolojisi() {
  const [catalog, setCatalog] = useState(null);
  const [parcelId, setParcelId] = useState("");
  const [parcelObj, setParcelObj] = useState(null);
  const [records, setRecords] = useState([]);
  const [form, setForm] = useState({ sample_date: new Date().toISOString().slice(0, 10) });
  const [organisms, setOrganisms] = useState({});     // key -> {tespit_edildi, yogunluk}
  const [preview, setPreview] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/soil-biology/catalog").then((r) => setCatalog(r.data)).catch(() => {});
  }, []);

  const loadRecords = (pid) => {
    if (!pid) { setRecords([]); return; }
    api.get("/soil-biology", { params: { parcel_id: pid } })
      .then((r) => setRecords(r.data || [])).catch(() => setRecords([]));
  };
  useEffect(() => { loadRecords(parcelId); }, [parcelId]);

  const organismList = () => Object.entries(organisms)
    .filter(([, v]) => v?.tespit_edildi)
    .map(([key, v]) => ({ organism_key: key, tespit_edildi: true, yogunluk: v.yogunluk || "orta" }));

  async function runPreview() {
    const { data } = await api.post("/soil-biology/score-preview",
      { ...numericForm(), organizmalar: organismList() });
    setPreview(data);
  }

  function numericForm() {
    const out = {};
    Object.entries(form).forEach(([k, v]) => {
      if (v === "" || v == null) return;
      out[k] = ["sample_date", "laboratuvar", "notlar"].includes(k) ? v : Number(v);
    });
    return out;
  }

  async function submit(e) {
    e.preventDefault();
    if (!parcelId) { setMsg("Önce parsel seçin."); return; }
    setBusy(true);
    setMsg("");
    try {
      const { data } = await api.post("/soil-biology", {
        parcel_id: parcelId, ...numericForm(), organizmalar: organismList(),
      });
      setMsg(`Kayıt eklendi — toprak sağlığı skoru: ${data.saglik_skoru?.skor ?? "—"}/100`);
      setOrganisms({});
      setPreview(null);
      loadRecords(parcelId);
    } catch (err) {
      setMsg(err.response?.data?.detail || "Kayıt eklenemedi.");
    } finally { setBusy(false); }
  }

  async function remove(id) {
    if (!window.confirm("Bu kayıt silinsin mi?")) return;
    await api.delete(`/soil-biology/${id}`);
    loadRecords(parcelId);
  }

  return (
    <div className="p-8 max-w-[1500px]" data-testid="toprak-biyolojisi">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">TOPRAK SAĞLIĞI</div>
        <h1 className="font-display text-4xl">Toprak Biyolojisi</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Parseldeki canlı organizmalar, mikrobiyal ölçümler ve türetilmiş toprak sağlığı skoru.
        </p>
      </header>

      <div className="card p-4 mb-4" style={{ maxWidth: 520 }}>
        <label className="text-xs text-[var(--text-dim)]">Parsel</label>
        {/* ParcelPicker: `value` seçili OBJE, geri çağrı `onSelect`. */}
        <ParcelPicker value={parcelObj}
                      onSelect={(p) => { setParcelObj(p); setParcelId(p?.id || ""); }}
                      testId="bio-parcel-picker" />
      </div>

      {msg && <div className="card p-3 mb-4 text-sm text-[var(--primary)]">{msg}</div>}

      {catalog && parcelId && (
        <form onSubmit={submit} className="grid gap-4 lg:grid-cols-2">
          {/* ÖLÇÜMLER */}
          <div className="card p-4">
            <h3 className="font-display text-lg mb-3 flex items-center gap-2">
              <FlaskConical size={16} className="text-[var(--primary)]" /> Laboratuvar Ölçümleri
            </h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="text-xs text-[var(--text-dim)]">Örnek tarihi</label>
                <input className="input" type="date" required value={form.sample_date || ""}
                       onChange={(e) => setForm({ ...form, sample_date: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-[var(--text-dim)]">Laboratuvar</label>
                <input className="input" value={form.laboratuvar || ""}
                       onChange={(e) => setForm({ ...form, laboratuvar: e.target.value })} />
              </div>
              {catalog.olcumler.map((m) => (
                <div key={m.key}>
                  <label className="text-xs text-[var(--text-dim)]" title={m.aciklama}>
                    {m.label} ({m.birim})
                  </label>
                  <input className="input" type="number" step="0.01"
                         placeholder={`hedef ≥ ${m.hedef}`}
                         value={form[m.key] ?? ""}
                         onChange={(e) => setForm({ ...form, [m.key]: e.target.value })}
                         data-testid={`olcum-${m.key}`} />
                </div>
              ))}
            </div>
          </div>

          {/* ORGANİZMALAR */}
          <div className="card p-4">
            <h3 className="font-display text-lg mb-3 flex items-center gap-2">
              <Bug size={16} className="text-[var(--primary)]" /> Tespit Edilen Organizmalar
            </h3>
            <div className="space-y-2 max-h-[420px] overflow-y-auto scrollbar pr-1">
              {catalog.organizmalar.map((o) => {
                const cur = organisms[o.key] || {};
                return (
                  <div key={o.key} className="flex items-center gap-2 text-sm border-b border-[var(--border)] pb-2">
                    <input type="checkbox" checked={!!cur.tespit_edildi}
                           onChange={(e) => setOrganisms({
                             ...organisms, [o.key]: { ...cur, tespit_edildi: e.target.checked },
                           })}
                           data-testid={`org-${o.key}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate">{o.label}</span>
                        <span className={`badge ${ETKI_CLS[o.etki]} text-[10px]`}>{o.etki}</span>
                      </div>
                      <div className="text-[10px] text-[var(--text-dim)] truncate" title={o.aciklama}>
                        {o.aciklama}
                      </div>
                    </div>
                    {cur.tespit_edildi && (
                      <select className="input text-xs" style={{ width: 90 }}
                              value={cur.yogunluk || "orta"}
                              onChange={(e) => setOrganisms({
                                ...organisms, [o.key]: { ...cur, yogunluk: e.target.value },
                              })}>
                        {YOGUNLUK.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                      </select>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="flex gap-2 mt-3">
              <button type="button" className="btn btn-ghost text-xs" onClick={runPreview}>
                Skoru önizle
              </button>
              <button type="submit" className="btn btn-primary text-xs" disabled={busy}>
                <Save size={13} /> {busy ? "Kaydediliyor…" : "Kaydet"}
              </button>
            </div>
            {preview && (
              <div className="mt-3 p-3 rounded-lg bg-[var(--surface-2)] text-sm">
                <b>Önizleme:</b> {preview.skor ?? "—"}/100 ({preview.sinif || "—"}) ·
                ölçüm kapsamı %{preview.kapsam_yuzde}
                {preview.engelleyici_organizmalar?.length > 0 && (
                  <div className="text-red-300 text-xs mt-1">
                    Engelleyici: {preview.engelleyici_organizmalar.join(", ")}
                  </div>
                )}
              </div>
            )}
          </div>
        </form>
      )}

      {/* GEÇMİŞ KAYITLAR */}
      {records.length > 0 && (
        <div className="card overflow-hidden mt-4">
          <div className="p-3 border-b border-[var(--border)] font-display text-lg flex items-center gap-2">
            <Leaf size={16} className="text-[var(--primary)]" /> Geçmiş Analizler ({records.length})
          </div>
          <table className="w-full text-sm">
            <thead className="bg-[var(--surface-2)]">
              <tr className="text-left text-[10px] text-[var(--text-dim)] uppercase tracking-wider">
                <th className="p-3">Tarih</th><th className="p-3">Skor</th><th className="p-3">Sınıf</th>
                <th className="p-3">Kapsam</th><th className="p-3">Organizma</th><th className="p-3"></th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-[var(--border)]">
                  <td className="p-3">{r.sample_date}</td>
                  <td className="p-3"><b>{r.saglik_skoru?.skor ?? "—"}</b>/100</td>
                  <td className="p-3">{r.saglik_skoru?.sinif || "—"}</td>
                  <td className="p-3 text-[var(--text-dim)]">%{r.saglik_skoru?.kapsam_yuzde}</td>
                  <td className="p-3 text-[var(--text-dim)]">
                    {(r.organizmalar || []).filter((o) => o.tespit_edildi).length} tür
                  </td>
                  <td className="p-3 text-right">
                    <button className="btn btn-ghost text-xs text-red-400" onClick={() => remove(r.id)}>
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
