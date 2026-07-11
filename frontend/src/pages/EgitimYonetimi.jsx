/**
 * EĞİTİM YÖNETİMİ — Farmer LMS (IT-29 / FAZ 10 başlangıç)
 *
 * Kategori + Eğitim + İçerik + Atama tek ekranda yönetilir (SupportCatalog.jsx'in
 * basit katalog + CampaignManagement.jsx'in "seç+ekle" koşul listesi kalıplarının
 * birleşimi). İçerik dosyaları (video/pdf/word/ppt/resim/ses) YENİ bir yükleme
 * mekanizması İCAT ETMEZ — mevcut genel `/uploads` (module="lms_contents",
 * entity_id=content.id) endpoint'i kullanılır (bkz. backend/lms.py docstring'i).
 *
 * Atama hedefi seçici — bazı hedef tiplerde (production_cycle, il_ilce) BİLİNÇLİ
 * OLARAK basit bir metin/id girişi kullanılır (tam bir arama/seçim ekranı bu
 * iterasyonun kapsamı dışında — entitlement.py'nin "formül" override'ı gibi
 * benzer bir sadeleştirme).
 */
import { useEffect, useState } from "react";
import api from "@/api";
import Drawer from "@/components/Drawer";
import { QuickAddPanel } from "@/components/QuickAdd";
import {
  GraduationCap, BookOpen, Users2, Plus, X, ChevronUp, ChevronDown, Trash2, Upload, Target,
} from "lucide-react";

const DIFFICULTY_LABELS = { baslangic: "Başlangıç", orta: "Orta", ileri: "İleri" };
const EDUCATION_TYPE_LABELS = { online: "Online", yuz_yuze: "Yüz Yüze", karma: "Karma" };
const CONTENT_TYPE_LABELS = {
  video: "Video", pdf: "PDF", word: "Word", powerpoint: "PowerPoint",
  resim: "Resim", ses: "Ses Dosyası", harici_link: "Harici Link", youtube: "YouTube Videosu",
};
const URL_BASED = new Set(["harici_link", "youtube"]);
const TARGET_TYPE_LABELS = {
  user: "Tek Kullanıcı", user_group: "Kullanıcı Grubu", role: "Rol",
  segment: "Segment (Kayıtlı Sorgu)", production_cycle: "Üretim Sezonu (ID)",
  region: "Bölge", il_ilce: "İl / İlçe (Parsel lookup ID)",
};

export default function EgitimYonetimi() {
  const [categories, setCategories] = useState([]);
  const [courses, setCourses] = useState([]);
  const [roles, setRoles] = useState([]);
  const [users, setUsers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [segments, setSegments] = useState([]);
  const [regions, setRegions] = useState([]);
  const [seeding, setSeeding] = useState(false);
  const [selected, setSelected] = useState(null);       // açık olan kurs (drawer)
  const [contents, setContents] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [contentForm, setContentForm] = useState({ content_type: "video", title: "", external_url: "", duration_minutes: "" });
  const [assignForm, setAssignForm] = useState({ target_type: "role", target_value: "", note: "" });
  const [error, setError] = useState("");
  const [tab, setTab] = useState("kurslar");

  const loadCategories = () => api.get("/course-categories").then((r) => setCategories(r.data));
  const loadCourses = () => api.get("/courses").then((r) => setCourses(r.data));
  const loadGroups = () => api.get("/lms-user-groups").then((r) => setGroups(r.data));

  useEffect(() => {
    loadCategories();
    loadCourses();
    loadGroups();
    api.get("/users").then((r) => setUsers(r.data));
    api.get("/users/roles").then((r) => setRoles(r.data.built_in || []));
    api.get("/saved-queries").then((r) => setSegments(r.data.filter((s) => s.module === "farmers" || s.module === "users")));
    api.get("/regions").then((r) => setRegions(r.data));
  }, []);

  const categoriesById = new Map(categories.map((c) => [c.id, c]));

  async function seedCategories() {
    setSeeding(true);
    try { await api.post("/course-categories/seed-defaults"); await loadCategories(); } finally { setSeeding(false); }
  }

  async function toggleCourseActive(c) {
    await api.put(`/courses/${c.id}`, { is_active: !c.is_active });
    loadCourses();
  }

  async function openCourse(course) {
    setSelected(course);
    setError("");
    const [contentsRes, assignmentsRes, summaryRes] = await Promise.all([
      api.get(`/courses/${course.id}`),
      api.get(`/courses/${course.id}/assignments`),
      api.get(`/courses/${course.id}/status-summary`),
    ]);
    setContents(contentsRes.data.contents || []);
    setAssignments(assignmentsRes.data);
    setSummary(summaryRes.data);
  }

  async function refreshSelected() {
    if (!selected) return;
    const [contentsRes, assignmentsRes, summaryRes] = await Promise.all([
      api.get(`/courses/${selected.id}`),
      api.get(`/courses/${selected.id}/assignments`),
      api.get(`/courses/${selected.id}/status-summary`),
    ]);
    setContents(contentsRes.data.contents || []);
    setAssignments(assignmentsRes.data);
    setSummary(summaryRes.data);
  }

  async function addContent(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post(`/courses/${selected.id}/contents`, {
        ...contentForm,
        duration_minutes: contentForm.duration_minutes ? Number(contentForm.duration_minutes) : null,
      });
      setContentForm({ content_type: "video", title: "", external_url: "", duration_minutes: "" });
      refreshSelected();
    } catch (err) {
      setError(err.response?.data?.detail || "İçerik eklenemedi");
    }
  }

  async function moveContent(idx, dir) {
    const items = [...contents];
    const j = idx + dir;
    if (j < 0 || j >= items.length) return;
    [items[idx], items[j]] = [items[j], items[idx]];
    setContents(items);
    await api.post(`/courses/${selected.id}/contents/reorder`, {
      items: items.map((c, i) => ({ id: c.id, order: i })),
    });
  }

  async function deleteContent(contentId) {
    await api.delete(`/courses/${selected.id}/contents/${contentId}`);
    refreshSelected();
  }

  async function uploadContentFile(content, file) {
    const form = new FormData();
    form.append("file", file);
    form.append("module", "lms_contents");
    form.append("entity_id", content.id);
    await api.post("/uploads", form, { headers: { "Content-Type": "multipart/form-data" } });
    refreshSelected();
  }

  async function submitAssignment(e) {
    e.preventDefault();
    setError("");
    try {
      let target_value = assignForm.target_value;
      if (assignForm.target_type === "il_ilce") {
        target_value = { il_value_id: assignForm.il_value_id, ilce_value_id: assignForm.ilce_value_id || null };
      }
      const res = await api.post(`/courses/${selected.id}/assign`, {
        target_type: assignForm.target_type, target_value, note: assignForm.note || null,
      });
      setAssignForm({ target_type: "role", target_value: "", note: "" });
      refreshSelected();
      alert(`${res.data.resolved_user_count} kullanıcı bulundu, ${res.data.new_assignments} yeni atama yapıldı.`);
    } catch (err) {
      setError(err.response?.data?.detail || "Atama yapılamadı");
    }
  }

  return (
    <div className="p-8 max-w-[1400px]" data-testid="lms-management-page">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">FAZ 10 — FARMER LMS</div>
          <h1 className="font-display text-4xl flex items-center gap-2"><GraduationCap size={28}/> Eğitim Yönetimi</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">
            Eğitim kataloğu, içerik yönetimi, kullanıcı/rol/segment bazlı atama ve durum takibi.
          </p>
        </div>
        {categories.length === 0 && (
          <button onClick={seedCategories} disabled={seeding} className="btn btn-ghost text-sm">
            {seeding ? "Yükleniyor…" : "Varsayılan Kategorileri Yükle"}
          </button>
        )}
      </header>

      <div className="flex items-center gap-2 mb-4">
        <button onClick={() => setTab("kurslar")} className={`btn text-sm ${tab === "kurslar" ? "btn-primary" : "btn-ghost"}`}>
          <BookOpen size={14}/> Eğitimler
        </button>
        <button onClick={() => setTab("gruplar")} className={`btn text-sm ${tab === "gruplar" ? "btn-primary" : "btn-ghost"}`}>
          <Users2 size={14}/> Kullanıcı Grupları
        </button>
      </div>

      {tab === "kurslar" && (
        <>
          <QuickAddPanel
            title="Yeni Eğitim"
            testId="course-add"
            fields={[
              { name: "title", label: "Başlık", required: true },
              { name: "description", label: "Açıklama", type: "textarea", span2: true },
              { name: "category_id", label: "Kategori", type: "select", required: true,
                options: categories.map((c) => ({ value: c.id, label: c.name })) },
              { name: "education_type", label: "Eğitim Türü", type: "select", required: true, default: "online",
                options: Object.entries(EDUCATION_TYPE_LABELS).map(([value, label]) => ({ value, label })) },
              { name: "difficulty", label: "Zorluk Seviyesi", type: "select", default: "baslangic",
                options: Object.entries(DIFFICULTY_LABELS).map(([value, label]) => ({ value, label })) },
              { name: "duration_minutes", label: "Süre (dk)", type: "number" },
              { name: "validity_months", label: "Geçerlilik Süresi (ay, opsiyonel)", type: "number" },
              { name: "instructor", label: "Eğitmen (opsiyonel)" },
              { name: "is_mandatory", label: "Zorunlu mu?", type: "select", default: "false",
                options: [{ value: "false", label: "Opsiyonel" }, { value: "true", label: "Zorunlu" }] },
            ]}
            onSubmit={async (v) => {
              await api.post("/courses", {
                ...v,
                duration_minutes: v.duration_minutes ? Number(v.duration_minutes) : null,
                validity_months: v.validity_months ? Number(v.validity_months) : null,
                is_mandatory: v.is_mandatory === "true",
              });
              loadCourses();
            }}
          />

          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                <th className="p-4">Başlık</th><th className="p-4">Kategori</th><th className="p-4">Tür</th>
                <th className="p-4">Zorluk</th><th className="p-4">Zorunlu</th><th className="p-4">Durum</th><th className="p-4"></th>
              </tr></thead>
              <tbody>
                {courses.map((c) => (
                  <tr key={c.id} className="border-b border-[var(--border)] hover:bg-[var(--surface-2)] cursor-pointer" onClick={() => openCourse(c)}>
                    <td className="p-4">{c.title}</td>
                    <td className="p-4 text-xs text-[var(--text-dim)]">{categoriesById.get(c.category_id)?.name || "—"}</td>
                    <td className="p-4 text-xs text-[var(--text-dim)]">{EDUCATION_TYPE_LABELS[c.education_type] || c.education_type}</td>
                    <td className="p-4 text-xs text-[var(--text-dim)]">{DIFFICULTY_LABELS[c.difficulty] || c.difficulty}</td>
                    <td className="p-4">{c.is_mandatory && <span className="badge badge-d text-[10px]">Zorunlu</span>}</td>
                    <td className="p-4">
                      <button onClick={(e) => { e.stopPropagation(); toggleCourseActive(c); }} className={`badge ${c.is_active === false ? "badge-d" : "badge-a"}`}>
                        {c.is_active === false ? "Pasif" : "Aktif"}
                      </button>
                    </td>
                    <td className="p-4 text-right text-xs text-[var(--primary)]">Yönet →</td>
                  </tr>
                ))}
                {courses.length === 0 && (
                  <tr><td colSpan="7" className="p-6 text-center text-[var(--text-dim)]">Henüz eğitim yok</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tab === "gruplar" && (
        <>
          <QuickAddPanel
            title="Yeni Kullanıcı Grubu"
            testId="lms-group-add"
            fields={[{ name: "name", label: "Grup Adı", required: true }]}
            onSubmit={async (v) => { await api.post("/lms-user-groups", { name: v.name, member_user_ids: [] }); loadGroups(); }}
          />
          <div className="space-y-3">
            {groups.map((g) => (
              <div key={g.id} className="card p-4">
                <div className="font-medium mb-2">{g.name} <span className="text-xs text-[var(--text-dim)]">({g.member_user_ids.length} üye)</span></div>
                <div className="flex flex-wrap gap-2 mb-2">
                  {g.member_user_ids.map((uid) => {
                    const u = users.find((x) => x.id === uid);
                    return (
                      <span key={uid} className="badge badge-neutral text-[10px] flex items-center gap-1">
                        {u?.full_name || uid}
                        <button onClick={async () => {
                          await api.put(`/lms-user-groups/${g.id}`, { member_user_ids: g.member_user_ids.filter((x) => x !== uid) });
                          loadGroups();
                        }}><X size={10}/></button>
                      </span>
                    );
                  })}
                </div>
                <select className="input text-xs max-w-xs" value="" onChange={async (e) => {
                  if (!e.target.value) return;
                  await api.put(`/lms-user-groups/${g.id}`, { member_user_ids: [...g.member_user_ids, e.target.value] });
                  loadGroups();
                }}>
                  <option value="">+ Üye ekle...</option>
                  {users.filter((u) => !g.member_user_ids.includes(u.id)).map((u) => (
                    <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>
                  ))}
                </select>
              </div>
            ))}
            {groups.length === 0 && <div className="text-sm text-[var(--text-dim)]">Henüz kullanıcı grubu yok</div>}
          </div>
        </>
      )}

      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.title || ""} width="560px">
        {selected && (
          <div className="p-4 space-y-6">
            {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded">{error}</div>}

            {summary && (
              <div>
                <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Durum Özeti ({summary.total} kişi)</div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(summary.by_status).map(([k, v]) => (
                    <span key={k} className="badge badge-neutral text-[10px]">{k}: {v}</span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">İçerikler (sıralı)</div>
              <div className="space-y-2 mb-3">
                {contents.map((c, idx) => (
                  <div key={c.id} className="bg-[var(--surface-2)] rounded-lg p-2">
                    <div className="flex items-center gap-2">
                      <div className="flex flex-col">
                        <button onClick={() => moveContent(idx, -1)} disabled={idx === 0}><ChevronUp size={12}/></button>
                        <button onClick={() => moveContent(idx, 1)} disabled={idx === contents.length - 1}><ChevronDown size={12}/></button>
                      </div>
                      <div className="flex-1">
                        <div className="text-sm">{c.title}</div>
                        <div className="text-[10px] text-[var(--text-dim)]">{CONTENT_TYPE_LABELS[c.content_type]}{c.duration_minutes ? ` · ${c.duration_minutes} dk` : ""}</div>
                        {URL_BASED.has(c.content_type) && c.external_url && (
                          <a href={c.external_url} target="_blank" rel="noreferrer" className="text-[10px] text-[var(--primary)]">{c.external_url}</a>
                        )}
                        {!URL_BASED.has(c.content_type) && (
                          <label className="text-[10px] text-[var(--primary)] flex items-center gap-1 cursor-pointer mt-1">
                            <Upload size={10}/> Dosya yükle
                            <input type="file" className="hidden" onChange={(e) => e.target.files[0] && uploadContentFile(c, e.target.files[0])}/>
                          </label>
                        )}
                      </div>
                      <button onClick={() => deleteContent(c.id)} className="text-[var(--text-dim)] hover:text-red-400"><Trash2 size={14}/></button>
                    </div>
                  </div>
                ))}
                {contents.length === 0 && <div className="text-xs text-[var(--text-dim)]">Henüz içerik yok</div>}
              </div>
              <form onSubmit={addContent} className="space-y-2">
                <select className="input text-sm" value={contentForm.content_type}
                        onChange={(e) => setContentForm((f) => ({ ...f, content_type: e.target.value }))}>
                  {Object.entries(CONTENT_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <input className="input text-sm" placeholder="İçerik başlığı" required
                       value={contentForm.title} onChange={(e) => setContentForm((f) => ({ ...f, title: e.target.value }))}/>
                {URL_BASED.has(contentForm.content_type) && (
                  <input className="input text-sm" placeholder="URL" required
                         value={contentForm.external_url} onChange={(e) => setContentForm((f) => ({ ...f, external_url: e.target.value }))}/>
                )}
                <input className="input text-sm" type="number" placeholder="Süre (dk, opsiyonel)"
                       value={contentForm.duration_minutes} onChange={(e) => setContentForm((f) => ({ ...f, duration_minutes: e.target.value }))}/>
                <button type="submit" className="btn btn-ghost text-xs"><Plus size={12}/> İçerik Ekle</button>
              </form>
            </div>

            <div>
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2 flex items-center gap-1"><Target size={12}/> Atama</div>
              <form onSubmit={submitAssignment} className="space-y-2 mb-3">
                <select className="input text-sm" value={assignForm.target_type}
                        onChange={(e) => setAssignForm((f) => ({ ...f, target_type: e.target.value, target_value: "" }))}>
                  {Object.entries(TARGET_TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>

                {assignForm.target_type === "user" && (
                  <select className="input text-sm" required value={assignForm.target_value}
                          onChange={(e) => setAssignForm((f) => ({ ...f, target_value: e.target.value }))}>
                    <option value="">Kullanıcı seç...</option>
                    {users.map((u) => <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>)}
                  </select>
                )}
                {assignForm.target_type === "user_group" && (
                  <select className="input text-sm" required value={assignForm.target_value}
                          onChange={(e) => setAssignForm((f) => ({ ...f, target_value: e.target.value }))}>
                    <option value="">Grup seç...</option>
                    {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                )}
                {assignForm.target_type === "role" && (
                  <select className="input text-sm" required value={assignForm.target_value}
                          onChange={(e) => setAssignForm((f) => ({ ...f, target_value: e.target.value }))}>
                    <option value="">Rol seç...</option>
                    {roles.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
                  </select>
                )}
                {assignForm.target_type === "segment" && (
                  <select className="input text-sm" required value={assignForm.target_value}
                          onChange={(e) => setAssignForm((f) => ({ ...f, target_value: e.target.value }))}>
                    <option value="">Kayıtlı sorgu seç...</option>
                    {segments.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.module})</option>)}
                  </select>
                )}
                {assignForm.target_type === "production_cycle" && (
                  <input className="input text-sm" placeholder="Üretim Sezonu ID" required
                         value={assignForm.target_value} onChange={(e) => setAssignForm((f) => ({ ...f, target_value: e.target.value }))}/>
                )}
                {assignForm.target_type === "region" && (
                  <select className="input text-sm" required value={assignForm.target_value}
                          onChange={(e) => setAssignForm((f) => ({ ...f, target_value: e.target.value }))}>
                    <option value="">Bölge seç...</option>
                    {regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </select>
                )}
                {assignForm.target_type === "il_ilce" && (
                  <>
                    <input className="input text-sm" placeholder="İl lookup value ID" required
                           value={assignForm.il_value_id || ""} onChange={(e) => setAssignForm((f) => ({ ...f, il_value_id: e.target.value }))}/>
                    <input className="input text-sm" placeholder="İlçe lookup value ID (opsiyonel)"
                           value={assignForm.ilce_value_id || ""} onChange={(e) => setAssignForm((f) => ({ ...f, ilce_value_id: e.target.value }))}/>
                  </>
                )}
                <input className="input text-sm" placeholder="Not (opsiyonel)"
                       value={assignForm.note} onChange={(e) => setAssignForm((f) => ({ ...f, note: e.target.value }))}/>
                <button type="submit" className="btn btn-primary text-xs">Ata</button>
              </form>

              <div className="space-y-1.5">
                {assignments.map((a) => (
                  <div key={a.id} className="text-xs text-[var(--text-dim)] flex items-center justify-between bg-[var(--surface-2)] rounded p-2">
                    <span>{TARGET_TYPE_LABELS[a.target_type]} · {a.resolved_user_count} kullanıcı</span>
                    <span>{new Date(a.assigned_at).toLocaleDateString("tr-TR")}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
