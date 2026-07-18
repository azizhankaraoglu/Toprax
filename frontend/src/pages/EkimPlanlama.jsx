/**
 * EKİM PLANLAMA KARAR MOTORU (#10)
 *
 * backend/agronomy.py'nin ekranı. İki sekme:
 *   - "Analiz": aranabilir parsel combobox'ı (il/ilçe/mahalle/ada/parsel/ad) +
 *     lookup'tan çeşit seçimi -> POST /ekim-planlama/analyze
 *   - "Bilgi Kütüphanesi": kural CRUD'u + AI prompt düzenleme (AutomationRules.jsx
 *     ile AYNI aile — kendi basit satır formu, yeni genel bileşen icat edilmedi)
 *
 * Parsel combobox'ı BİLİNÇLİ olarak yeni bir bağımlılık (react-select vb.)
 * KULLANMAZ — debounce'lu bir input + sonuç listesi yeterli (Karar Protokolü).
 */
import { useCallback, useEffect, useState } from "react";
import api from "@/api";
import ParcelPicker from "@/components/ParcelPicker";
import { Sprout, Search, BookOpen, Plus, Trash2, Sparkles, AlertTriangle } from "lucide-react";

const DECISION_BADGE = {
  uygun: { cls: "badge-a", text: "UYGUN" },
  sartli: { cls: "badge-c", text: "ŞARTLI" },
  uygun_degil: { cls: "badge-d", text: "UYGUN DEĞİL" },
};

const emptyRule = {
  name: "", category: "toprak", signal: "", operator: "lt",
  value: "", value2: "", score_delta: -10, advice: "", is_blocking: false, order: 100,
};

export default function EkimPlanlama() {
  const [tab, setTab] = useState("analiz");

  // --- Parsel seçimi (ortak ParcelPicker bileşeniyle — SON HAL) ---
  const [parcel, setParcel] = useState(null);

  // --- Analiz ---
  const [season, setSeason] = useState(new Date().getFullYear());
  const [varieties, setVarieties] = useState([]);
  const [variety, setVariety] = useState("");
  const [useAi, setUseAi] = useState(true);
  const [busy, setBusy] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState("");

  // --- Bilgi kütüphanesi ---
  const [rules, setRules] = useState([]);
  const [signals, setSignals] = useState([]);
  const [operators, setOperators] = useState([]);
  const [ruleForm, setRuleForm] = useState(emptyRule);
  const [prompt, setPrompt] = useState({ system_prompt: "", user_template: "" });
  const [libMsg, setLibMsg] = useState("");

  const loadRules = useCallback(() => api.get("/agronomy/rules").then((r) => setRules(r.data)), []);

  useEffect(() => {
    api.get("/ekim-planlama/varieties").then((r) => setVarieties(r.data)).catch(() => {});
    api.get("/agronomy/signals").then((r) => {
      setSignals(r.data.signals || []);
      setOperators(r.data.operators || []);
    }).catch(() => {});
    api.get("/agronomy/prompt").then((r) => setPrompt(r.data)).catch(() => {});
    loadRules().catch(() => {});
  }, [loadRules]);

  async function runAnalysis() {
    if (!parcel) return;
    setBusy(true); setError(""); setAnalysis(null);
    try {
      const { data } = await api.post("/ekim-planlama/analyze", {
        parcel_id: parcel.id, season: Number(season),
        variety: variety || null, use_ai: useAi,
      });
      setAnalysis(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Analiz çalıştırılamadı");
    } finally {
      setBusy(false);
    }
  }

  async function seedDefaults() {
    setLibMsg("");
    try {
      const { data } = await api.post("/agronomy/seed-defaults");
      setLibMsg(`${data.rules_added} kural, ${data.varieties_added} çeşit eklendi (toplam ${data.total_rules} kural).`);
      loadRules();
      api.get("/ekim-planlama/varieties").then((r) => setVarieties(r.data));
    } catch (err) {
      setLibMsg(err.response?.data?.detail || "Varsayılanlar yüklenemedi");
    }
  }

  async function submitRule(e) {
    e.preventDefault();
    setLibMsg("");
    try {
      const body = { ...ruleForm, score_delta: Number(ruleForm.score_delta), order: Number(ruleForm.order) };
      if (body.value === "") body.value = null;
      if (body.value2 === "") body.value2 = null;
      await api.post("/agronomy/rules", body);
      setRuleForm(emptyRule);
      loadRules();
    } catch (err) {
      setLibMsg(err.response?.data?.detail || "Kural eklenemedi");
    }
  }

  async function deleteRule(id) {
    await api.delete(`/agronomy/rules/${id}`);
    loadRules();
  }

  async function savePrompt() {
    setLibMsg("");
    try {
      await api.put("/agronomy/prompt", {
        system_prompt: prompt.system_prompt, user_template: prompt.user_template,
      });
      setLibMsg("AI şablonu kaydedildi.");
    } catch (err) {
      setLibMsg(err.response?.data?.detail || "Şablon kaydedilemedi");
    }
  }

  const signalLabel = (key) => signals.find((s) => s.key === key)?.label || key;

  return (
    <div className="page">
      <div className="page-header">
        <h1><Sprout size={22} /> Ekim Planlama Karar Motoru</h1>
        <p className="muted">
          Parselin toprak, uydu, sulama, hastalık ve geçmiş polar verilerini birlikte
          değerlendirir — hedef şeker (polar) oranını yükseltmektir.
        </p>
      </div>

      <div className="tabs" style={{ marginBottom: 16 }}>
        <button className={`tab ${tab === "analiz" ? "active" : ""}`} onClick={() => setTab("analiz")}
                data-testid="tab-analiz">
          <Search size={15} /> Analiz
        </button>
        <button className={`tab ${tab === "kutuphane" ? "active" : ""}`} onClick={() => setTab("kutuphane")}
                data-testid="tab-kutuphane">
          <BookOpen size={15} /> Bilgi Kütüphanesi
        </button>
      </div>

      {tab === "analiz" && (
        <>
          <div className="card">
            <h3>Parsel Seç</h3>
            {/* SON HAL — ortak ParcelPicker bileşeni (bkz. components/ParcelPicker.jsx) */}
            <ParcelPicker
              value={parcel}
              onSelect={(p) => { setParcel(p); setAnalysis(null); }}
              testId="parcel-search"
            />

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 14, alignItems: "flex-end" }}>
              <div>
                <label className="muted" style={{ fontSize: 12 }}>Sezon</label>
                <input className="input" type="number" style={{ width: 110 }}
                       value={season} onChange={(e) => setSeason(e.target.value)} data-testid="season-input" />
              </div>
              <div>
                <label className="muted" style={{ fontSize: 12 }}>Çeşit</label>
                <select className="input" value={variety} onChange={(e) => setVariety(e.target.value)}
                        data-testid="variety-select" style={{ minWidth: 180 }}>
                  <option value="">— Seçilmedi —</option>
                  {varieties.map((v) => <option key={v.id} value={v.label}>{v.label}</option>)}
                </select>
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: 6, paddingBottom: 8 }}>
                <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />
                <span className="muted" style={{ fontSize: 13 }}>AI anlatımı ekle</span>
              </label>
              <button className="btn btn-primary" disabled={!parcel || busy} onClick={runAnalysis}
                      data-testid="analyze-btn">
                <Sparkles size={15} /> {busy ? "Analiz ediliyor…" : "Analiz Et"}
              </button>
            </div>
            {error && <p style={{ color: "var(--danger, #d33)", marginTop: 10 }}>{error}</p>}
            {varieties.length === 0 && (
              <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
                Çeşit listesi boş — "Bilgi Kütüphanesi" sekmesinden "Varsayılanları Yükle" çalıştırın.
              </p>
            )}
          </div>

          {analysis && (
            <>
              <div className="card" data-testid="analysis-result">
                <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
                  <div style={{ fontSize: 44, fontWeight: 800, lineHeight: 1 }}>{analysis.score}</div>
                  <div>
                    <div className="muted" style={{ fontSize: 12 }}>100 üzerinden uygunluk skoru</div>
                    <span className={`badge ${DECISION_BADGE[analysis.decision]?.cls || "badge-neutral"}`}>
                      {analysis.decision_label}
                    </span>
                  </div>
                  <div style={{ flex: 1 }} />
                  <div className="muted" style={{ fontSize: 12, textAlign: "right" }}>
                    {analysis.season} sezonu{analysis.variety ? ` · ${analysis.variety}` : ""}<br />
                    {analysis.ai_powered ? "AI destekli anlatım" : "Kural tabanlı anlatım"}
                  </div>
                </div>

                {analysis.data_gaps?.length > 0 && (
                  <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>
                    <AlertTriangle size={13} /> Eksik veri: {analysis.data_gaps.join(", ")} —
                    bu alanlar "sorun yok" anlamına gelmez, ölçüm yapılmamıştır.
                  </p>
                )}

                <pre style={{
                  whiteSpace: "pre-wrap", marginTop: 14, fontFamily: "inherit",
                  fontSize: 14, lineHeight: 1.6,
                }} data-testid="analysis-narrative">{analysis.narrative}</pre>

                {analysis.ai_error && (
                  <p className="muted" style={{ fontSize: 12 }}>AI çağrısı başarısız: {analysis.ai_error}</p>
                )}
              </div>

              <div className="card">
                <h3>Tespit Edilen Bulgular ({analysis.matched_rules.length})</h3>
                {analysis.matched_rules.length === 0 && (
                  <p className="muted">Kural kütüphanesinde olumsuz bir bulgu tetiklenmedi.</p>
                )}
                <table className="table">
                  <thead>
                    <tr><th>Etki</th><th>Kural</th><th>Öneri</th></tr>
                  </thead>
                  <tbody>
                    {analysis.matched_rules.map((m) => (
                      <tr key={m.id || m.name}>
                        <td style={{ whiteSpace: "nowrap" }}>
                          {m.is_blocking
                            ? <span className="badge badge-d">ENGEL</span>
                            : <span className="badge badge-neutral">{m.score_delta > 0 ? "+" : ""}{m.score_delta}</span>}
                        </td>
                        <td>{m.name}</td>
                        <td className="muted">{m.advice}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="card">
                <h3>Ölçümler</h3>
                <table className="table">
                  <thead><tr><th>Sinyal</th><th>Değer</th></tr></thead>
                  <tbody>
                    {signals.map((s) => (
                      <tr key={s.key}>
                        <td>{s.label}</td>
                        <td className={analysis.signals[s.key] == null ? "muted" : ""}>
                          {analysis.signals[s.key] == null ? "veri yok" : String(analysis.signals[s.key])}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {analysis.details?.gecmis_sezonlar?.length > 0 && (
                  <>
                    <h4 style={{ marginTop: 16 }}>Geçmiş Sezonlar</h4>
                    <table className="table">
                      <thead><tr><th>Sezon</th><th>Ton</th><th>Polar (%)</th></tr></thead>
                      <tbody>
                        {analysis.details.gecmis_sezonlar.map((g) => (
                          <tr key={g.season}><td>{g.season}</td><td>{g.ton ?? "—"}</td><td>{g.polar ?? "—"}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )}
              </div>
            </>
          )}
        </>
      )}

      {tab === "kutuphane" && (
        <>
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
              <div>
                <h3 style={{ margin: 0 }}>Agronomik Kurallar ({rules.length})</h3>
                <p className="muted" style={{ margin: "4px 0 0" }}>
                  Motor bu kuralları çalıştırır. Kural değiştirmek kod değişikliği gerektirmez.
                </p>
              </div>
              <button className="btn" onClick={seedDefaults} data-testid="seed-btn">
                Varsayılanları Yükle
              </button>
            </div>
            {libMsg && <p className="muted" style={{ marginTop: 10 }}>{libMsg}</p>}

            <table className="table" style={{ marginTop: 12 }}>
              <thead>
                <tr><th>Kural</th><th>Koşul</th><th>Etki</th><th></th></tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{r.name}</div>
                      <div className="muted" style={{ fontSize: 12 }}>{r.advice}</div>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <span className="muted">{signalLabel(r.signal)}</span> {r.operator} {String(r.value ?? "")}
                      {r.operator === "between" ? ` – ${r.value2}` : ""}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      {r.is_blocking
                        ? <span className="badge badge-d">ENGEL</span>
                        : <span className="badge badge-neutral">{r.score_delta > 0 ? "+" : ""}{r.score_delta}</span>}
                    </td>
                    <td>
                      <button className="btn" onClick={() => deleteRule(r.id)} title="Sil">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <h3><Plus size={16} /> Yeni Kural</h3>
            <form onSubmit={submitRule} style={{ display: "grid", gap: 10 }}>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input className="input" placeholder="Kural adı" required style={{ flex: 2, minWidth: 200 }}
                       value={ruleForm.name} onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })} />
                <select className="input" value={ruleForm.category} style={{ flex: 1, minWidth: 130 }}
                        onChange={(e) => setRuleForm({ ...ruleForm, category: e.target.value })}>
                  {["toprak", "uydu", "su", "hastalik", "gecmis"].map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <select className="input" required value={ruleForm.signal} style={{ flex: 2, minWidth: 200 }}
                        onChange={(e) => setRuleForm({ ...ruleForm, signal: e.target.value })}>
                  <option value="">— Sinyal seçin —</option>
                  {signals.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
                <select className="input" value={ruleForm.operator} style={{ minWidth: 120 }}
                        onChange={(e) => setRuleForm({ ...ruleForm, operator: e.target.value })}>
                  {operators.map((o) => <option key={o} value={o}>{o}</option>)}
                </select>
                <input className="input" placeholder="Değer" style={{ width: 120 }}
                       value={ruleForm.value} onChange={(e) => setRuleForm({ ...ruleForm, value: e.target.value })} />
                {ruleForm.operator === "between" && (
                  <input className="input" placeholder="Üst değer" style={{ width: 120 }}
                         value={ruleForm.value2} onChange={(e) => setRuleForm({ ...ruleForm, value2: e.target.value })} />
                )}
              </div>
              <textarea className="input" placeholder="Öneri metni (çiftçiye/mühendise gösterilir)" rows={2}
                        value={ruleForm.advice} onChange={(e) => setRuleForm({ ...ruleForm, advice: e.target.value })} />
              <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
                <label className="muted" style={{ fontSize: 13 }}>
                  Skor etkisi{" "}
                  <input className="input" type="number" style={{ width: 90 }} value={ruleForm.score_delta}
                         onChange={(e) => setRuleForm({ ...ruleForm, score_delta: e.target.value })} />
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <input type="checkbox" checked={ruleForm.is_blocking}
                         onChange={(e) => setRuleForm({ ...ruleForm, is_blocking: e.target.checked })} />
                  <span className="muted" style={{ fontSize: 13 }}>Engelleyici (tek başına "uygun değil" yapar)</span>
                </label>
                <button className="btn btn-primary" type="submit">Kural Ekle</button>
              </div>
            </form>
          </div>

          <div className="card">
            <h3><Sparkles size={16} /> AI Anlatım Şablonu</h3>
            <p className="muted" style={{ marginTop: 0 }}>
              AI kararı DEĞİŞTİRMEZ — skoru ve bulguları anlatır. Şablon değişkenleri:
              {" "}{"{parsel_adi} {il} {ilce} {mahalle} {alan} {sezon} {cesit} {skor} {karar} {sinyaller} {bulgular}"}
            </p>
            <label className="muted" style={{ fontSize: 12 }}>Sistem promptu</label>
            <textarea className="input" rows={4} value={prompt.system_prompt || ""}
                      onChange={(e) => setPrompt({ ...prompt, system_prompt: e.target.value })} />
            <label className="muted" style={{ fontSize: 12, marginTop: 10, display: "block" }}>Kullanıcı şablonu</label>
            <textarea className="input" rows={8} value={prompt.user_template || ""}
                      onChange={(e) => setPrompt({ ...prompt, user_template: e.target.value })} />
            <button className="btn btn-primary" style={{ marginTop: 10 }} onClick={savePrompt}>
              Şablonu Kaydet
            </button>
          </div>
        </>
      )}
    </div>
  );
}
