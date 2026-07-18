/**
 * İLETİŞİM POLİTİKALARI + KARA LİSTE (IT-27 / FAZ 9 TAMAMLANDI)
 *
 * Communication Policy: "olay → kanal(lar)" kuralları — AutomationRules.jsx'in
 * (IT-24) kural motoru admin ekranıyla AYNI aile (event_type + hedef, burada
 * hedef bir TaskType değil kanal+şablon listesi). Kara Liste (KVKK) AYRI bir
 * ekran İCAT EDİLMEDİ — aynı sayfada ikinci bir bölüm, backend'de de tek
 * modülde (communication_policy.py) birlikte yaşıyorlar.
 */
import { useState } from "react";
import api from "@/api";
import { useFetch } from "@/hooks/use-fetch";
import FarmerSelect from "@/components/FarmerSelect";
import { Zap, Plus, ShieldOff, Trash2, Users } from "lucide-react";

const emptyPolicyForm = {
  name: "", event_type: "", channels: [], template_ids: {},
  group_ids: [], notify_responsible: true,   // #5 — çok-gruplu fan-out + köy sorumlusu
};
const emptyBlacklistForm = { contact_type: "farmer", contact_id: "", reason: "" };
const emptyGroupForm = { name: "", description: "", member_user_ids: [], member_farmer_ids: [] };

// Refactoring notu (2026-07-11): 5 bagimsiz okuma-fetch'i useFetch hook'una
// tasindi (bkz. hooks/use-fetch.js) -- form state (policyForm/blacklistForm/
// error) DEGISMEDI, sadece "listeyi cek" kismi sadelesti. DAVRANIS AYNI.
export default function CommunicationPolicies() {
  const policiesQ = useFetch("/communication-policies", { initialData: [] });
  const eventTypesQ = useFetch("/communication-policies/event-types", { initialData: [] });
  const channelsQ = useFetch("/channels", { initialData: [] });
  const templatesQ = useFetch("/templates", { initialData: [] });
  const blacklistQ = useFetch("/communications/blacklist", { initialData: [] });
  const policies = policiesQ.data;
  const eventTypes = eventTypesQ.data;
  const channels = channelsQ.data;
  const templates = templatesQ.data;
  const blacklist = blacklistQ.data;
  const groupsQ = useFetch("/groups", { initialData: [] });
  const usersQ = useFetch("/users", { initialData: [] });
  const groups = groupsQ.data;
  const staffUsers = (usersQ.data || []).filter((u) => u.role !== "ciftci");
  const [policyForm, setPolicyForm] = useState(emptyPolicyForm);
  const [blacklistForm, setBlacklistForm] = useState(emptyBlacklistForm);
  const [groupForm, setGroupForm] = useState(emptyGroupForm);
  const [error, setError] = useState("");

  const loadPolicies = () => policiesQ.reload();
  const loadBlacklist = () => blacklistQ.reload();

  // ---- #5 Gruplar ----
  function toggleGroupMemberUser(uid) {
    setGroupForm((f) => ({
      ...f,
      member_user_ids: f.member_user_ids.includes(uid)
        ? f.member_user_ids.filter((x) => x !== uid) : [...f.member_user_ids, uid],
    }));
  }
  function addGroupFarmer(fid) {
    if (!fid) return;
    setGroupForm((f) => (f.member_farmer_ids.includes(fid) ? f : { ...f, member_farmer_ids: [...f.member_farmer_ids, fid] }));
  }
  async function submitGroup(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/groups", groupForm);
      setGroupForm(emptyGroupForm);
      groupsQ.reload();
    } catch (err) { setError(err.response?.data?.detail || "Grup oluşturulamadı"); }
  }
  async function deleteGroup(id) {
    if (!window.confirm("Bu grup silinsin mi? (Arşivlenir)")) return;
    await api.delete(`/groups/${id}`);
    groupsQ.reload();
  }
  function togglePolicyGroup(gid) {
    setPolicyForm((f) => ({
      ...f,
      group_ids: (f.group_ids || []).includes(gid)
        ? f.group_ids.filter((x) => x !== gid) : [...(f.group_ids || []), gid],
    }));
  }

  const eventLabels = Object.fromEntries(eventTypes.map((e) => [e.key, e.label]));
  const channelLabel = (key) => channels.find((c) => c.key === key)?.label || key;

  function toggleChannel(ch) {
    setPolicyForm((f) => {
      const channels = f.channels.includes(ch) ? f.channels.filter((c) => c !== ch) : [...f.channels, ch];
      return { ...f, channels };
    });
  }
  function setChannelTemplate(ch, templateId) {
    setPolicyForm((f) => ({ ...f, template_ids: { ...f.template_ids, [ch]: templateId } }));
  }

  async function submitPolicy(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/communication-policies", policyForm);
      setPolicyForm(emptyPolicyForm);
      loadPolicies();
    } catch (err) {
      setError(err.response?.data?.detail || "Politika oluşturulamadı");
    }
  }

  async function togglePolicyActive(policy) {
    await api.put(`/communication-policies/${policy.id}`, { is_active: !policy.is_active });
    loadPolicies();
  }

  async function submitBlacklist(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/communications/blacklist", blacklistForm);
      setBlacklistForm(emptyBlacklistForm);
      loadBlacklist();
    } catch (err) {
      setError(err.response?.data?.detail || "Kara listeye eklenemedi");
    }
  }

  async function removeFromBlacklist(id) {
    await api.delete(`/communications/blacklist/${id}`);
    loadBlacklist();
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="communication-policies-page">
      <header className="mb-6">
        <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">İLETİŞİM MERKEZİ</div>
        <h1 className="font-display text-4xl">İletişim Politikaları & Kara Liste</h1>
        <p className="text-[var(--text-dim)] text-sm mt-1">
          Bir iş olayı (ör. "Hakediş Oluştu") gerçekleştiğinde otomatik hangi kanal(lar)dan
          bildirim gideceğini tanımlayın. Kara listedeki kişilere hiçbir politika/kampanya mesaj gönderemez.
        </p>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      <form onSubmit={submitPolicy} className="card p-5 mb-6 space-y-3" data-testid="policy-form">
        <h3 className="font-display text-lg flex items-center gap-2"><Zap size={16} className="text-[var(--primary)]"/>Yeni İletişim Politikası</h3>
        <div className="grid grid-cols-2 gap-3">
          <input className="input" placeholder="Politika adı" required
                 value={policyForm.name} onChange={(e) => setPolicyForm((f) => ({ ...f, name: e.target.value }))}/>
          <select className="input" required value={policyForm.event_type}
                  onChange={(e) => setPolicyForm((f) => ({ ...f, event_type: e.target.value }))}>
            <option value="">Olay seç...</option>
            {eventTypes.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}
          </select>
        </div>
        <div>
          <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Kanal(lar) — hepsi bağımsız olarak gönderilir</div>
          <div className="flex flex-wrap gap-2 mb-2">
            {channels.map((c) => (
              <button key={c.key} type="button" onClick={() => toggleChannel(c.key)}
                      className={`btn text-xs ${policyForm.channels.includes(c.key) ? "btn-primary" : "btn-ghost"}`}>
                {c.label}
              </button>
            ))}
          </div>
          {policyForm.channels.map((ch) => (
            <div key={ch} className="flex items-center gap-2 mb-1.5">
              <span className="text-xs text-[var(--text-dim)] w-24">{channelLabel(ch)} şablonu:</span>
              <select className="input flex-1" value={policyForm.template_ids[ch] || ""} onChange={(e) => setChannelTemplate(ch, e.target.value)}>
                <option value="">Şablon seç...</option>
                {templates.filter((t) => t.channel === ch).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
          ))}
        </div>

        {/* #5 — çok-gruplu fan-out + köy sorumlusu */}
        <div>
          <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">
            Ek Alıcılar (olayın kendi kişisine EK olarak)
          </div>
          <div className="flex flex-wrap gap-2 mb-2">
            {groups.length === 0 && <span className="text-xs text-[var(--text-dim)]">Henüz grup yok — aşağıdan oluşturun.</span>}
            {groups.map((g) => (
              <button key={g.id} type="button" onClick={() => togglePolicyGroup(g.id)}
                      className={`btn text-xs ${(policyForm.group_ids || []).includes(g.id) ? "btn-primary" : "btn-ghost"}`}
                      data-testid="policy-group-chip">
                {g.name} ({(g.member_user_ids?.length || 0) + (g.member_farmer_ids?.length || 0)})
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs text-[var(--text-dim)]">
            <input type="checkbox" checked={policyForm.notify_responsible !== false}
                   onChange={(e) => setPolicyForm((f) => ({ ...f, notify_responsible: e.target.checked }))}
                   data-testid="policy-notify-responsible" />
            Parselin köy sorumlusuna da gönder (portföy sorumlusu — #6)
          </label>
        </div>

        <button type="submit" className="btn btn-primary" data-testid="policy-submit">Politikayı Oluştur</button>
      </form>

      {/* #5 — KİŞİ GRUPLARI (personel + çiftçi karma) */}
      <div className="card p-5 mb-8" data-testid="groups-card">
        <h3 className="font-display text-lg flex items-center gap-2 mb-1">
          <Users size={16} className="text-[var(--primary)]" /> Kişi Grupları
        </h3>
        <p className="text-[11px] text-[var(--text-dim)] mb-3">
          Personel ve/veya çiftçilerden oluşan adlandırılmış dağıtım listeleri. Yukarıdaki politikalarda
          "Ek Alıcılar" olarak seçilir (anomali vb. olaylarda tüm üyelere çok-kanallı bildirim gider).
        </p>

        <form onSubmit={submitGroup} className="space-y-3 mb-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input className="input" placeholder="Grup adı (ör. Kriz Ekibi)" required
                   value={groupForm.name} onChange={(e) => setGroupForm((f) => ({ ...f, name: e.target.value }))}
                   data-testid="group-name" />
            <input className="input" placeholder="Açıklama (opsiyonel)"
                   value={groupForm.description} onChange={(e) => setGroupForm((f) => ({ ...f, description: e.target.value }))} />
          </div>
          <div>
            <div className="text-xs text-[var(--text-dim)] mb-1">Personel üyeler</div>
            <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto scrollbar">
              {staffUsers.map((u) => (
                <button key={u.id} type="button" onClick={() => toggleGroupMemberUser(u.id)}
                        className={`btn text-[11px] ${groupForm.member_user_ids.includes(u.id) ? "btn-primary" : "btn-ghost"}`}>
                  {u.full_name || u.email}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs text-[var(--text-dim)] mb-1">Çiftçi üyeler (arayıp ekleyin)</div>
            <FarmerSelect value="" onChange={addGroupFarmer} />
            {groupForm.member_farmer_ids.length > 0 && (
              <div className="text-[11px] text-[var(--text-dim)] mt-1">
                {groupForm.member_farmer_ids.length} çiftçi eklendi
                <button type="button" className="ml-2 text-red-400"
                        onClick={() => setGroupForm((f) => ({ ...f, member_farmer_ids: [] }))}>temizle</button>
              </div>
            )}
          </div>
          <button type="submit" className="btn btn-primary text-xs" data-testid="group-submit">
            <Plus size={12} /> Grup Oluştur
          </button>
        </form>

        <div className="space-y-1">
          {groups.map((g) => (
            <div key={g.id} className="flex items-center justify-between text-sm p-2 bg-[var(--surface-2)] rounded">
              <div>
                <span className="font-medium">{g.name}</span>
                <span className="text-[11px] text-[var(--text-dim)] ml-2">
                  {(g.member_user_ids?.length || 0)} personel · {(g.member_farmer_ids?.length || 0)} çiftçi
                  {g.description ? ` · ${g.description}` : ""}
                </span>
              </div>
              <button onClick={() => deleteGroup(g.id)} className="text-red-400 p-1" title="Sil"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
      </div>

      <div className="card overflow-hidden mb-8">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Ad</th><th className="p-4">Olay</th><th className="p-4">Kanal(lar)</th><th className="p-4">Durum</th>
          </tr></thead>
          <tbody>
            {policies.map((p) => (
              <tr key={p.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4">{p.name}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{eventLabels[p.event_type] || p.event_type}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{p.channels.map(channelLabel).join(", ")}</td>
                <td className="p-4">
                  <button onClick={() => togglePolicyActive(p)} className={`badge ${p.is_active === false ? "badge-d" : "badge-a"}`}>
                    {p.is_active === false ? "Pasif" : "Aktif"}
                  </button>
                </td>
              </tr>
            ))}
            {policies.length === 0 && (
              <tr><td colSpan="4" className="p-6 text-center text-[var(--text-dim)]">Henüz iletişim politikası yok</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <form onSubmit={submitBlacklist} className="card p-5 mb-6 space-y-3" data-testid="blacklist-form">
        <h3 className="font-display text-lg flex items-center gap-2"><ShieldOff size={16} className="text-red-400"/>Kara Listeye Ekle (KVKK)</h3>
        <div className="grid grid-cols-3 gap-3">
          <select className="input" value={blacklistForm.contact_type}
                  onChange={(e) => setBlacklistForm((f) => ({ ...f, contact_type: e.target.value }))}>
            <option value="farmer">Çiftçi</option>
            <option value="personnel">Personel</option>
          </select>
          <input className="input" placeholder="Kişi ID (farmer_id / user_id)" required
                 value={blacklistForm.contact_id} onChange={(e) => setBlacklistForm((f) => ({ ...f, contact_id: e.target.value }))}/>
          <input className="input" placeholder="Sebep (opsiyonel)"
                 value={blacklistForm.reason} onChange={(e) => setBlacklistForm((f) => ({ ...f, reason: e.target.value }))}/>
        </div>
        <button type="submit" className="btn btn-primary text-sm" data-testid="blacklist-submit">
          <Plus size={12}/> Kara Listeye Ekle
        </button>
      </form>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
            <th className="p-4">Tip</th><th className="p-4">Kişi ID</th><th className="p-4">Sebep</th><th className="p-4">Eklenme</th><th className="p-4"></th>
          </tr></thead>
          <tbody>
            {blacklist.map((b) => (
              <tr key={b.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="p-4">{b.contact_type === "farmer" ? "Çiftçi" : "Personel"}</td>
                <td className="p-4 font-mono text-xs">{b.contact_id}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{b.reason || "—"}</td>
                <td className="p-4 text-xs text-[var(--text-dim)]">{(b.created_at || "").slice(0, 10)}</td>
                <td className="p-4">
                  <button onClick={() => removeFromBlacklist(b.id)} className="btn btn-ghost text-xs text-red-400" data-testid={`blacklist-remove-${b.id}`}>
                    <Trash2 size={12}/> Çıkar
                  </button>
                </td>
              </tr>
            ))}
            {blacklist.length === 0 && (
              <tr><td colSpan="5" className="p-6 text-center text-[var(--text-dim)]">Kara liste boş</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
