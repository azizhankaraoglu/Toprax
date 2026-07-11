/**
 * SAHA OPERASYONLARI — Kanban + Takvim (IT-23 / FAZ 8 devam)
 *
 * IT-22'nin field_tasks/work_orders/visits modelini TÜKETEN ilk UI —
 * IT-22 bilinçli olarak backend-only bırakılmıştı. Kanban sütunları
 * ROADMAP'in verdiği 8 görünür grupla BİREBİR (11 backend durumu bazı
 * sütunlarda birleşir — "Sahada" = yerine_ulasildi + calisiliyor);
 * reddedildi/iptal_edildi ayrı, dar bir 9. sütunda gösterilir (tüm
 * görevler görünür kalsın diye, roadmap'in 8 sütunluk listesine sadık
 * kalmak adına ayrı tutuldu).
 *
 * Sürükle-bırak SADECE bir hedef durumu ÖNERİR (client-side ALLOWED_NEXT
 * tahmini) — gerçek doğrulama HER ZAMAN backend'de (`PUT /tasks/{id}/
 * transition`) yapılır; checklist tamamlanmadan kapandı'ya bırakma
 * backend'den 400 döner ve UI bunu olduğu gibi gösterir (kabul kriteri:
 * "Kanban sürükle-bırak durum geçiş kurallarına, checklist dahil, uyuyor").
 */
import { useEffect, useMemo, useState } from "react";
import api from "@/api";
import Drawer from "@/components/Drawer";
import SmartDataGrid from "@/components/SmartDataGrid";
import {
  ListChecks, Calendar as CalendarIcon, Kanban as KanbanIcon, MapPin, User, Check, X, Plus,
  LayoutDashboard, Table2, ClipboardList, AlertTriangle, CalendarCheck, Users2, Gauge, Timer,
} from "lucide-react";

// (IT-24) Saha Raporları — CORE_FILTERABLE_FIELDS["field_tasks"] (query_engine.py)
// ile BİREBİR eşleşen kolon listesi. SmartDataGrid join YAPMAZ (bkz. IT-11
// docstring'i), bu yüzden farmer_id/parcel_id/assigned_to gibi alanlar HAM
// (UUID) görünür — diğer modüllerdeki (ör. contracts) SmartDataGrid
// kullanımlarıyla TUTARLI bir bilinçli sınırlama.
const FIELD_TASKS_GRID_COLUMNS = [
  { key: "task_type_id", label: "Görev Tipi", type: "text" },
  { key: "assigned_to", label: "Atanan Personel", type: "text" },
  { key: "status", label: "Durum", type: "text" },
  { key: "priority", label: "Öncelik", type: "text" },
  { key: "farmer_id", label: "Çiftçi", type: "text" },
  { key: "parcel_id", label: "Parsel", type: "text" },
  { key: "planned_date", label: "Planlanan Tarih", type: "date" },
  { key: "sla_due_date", label: "SLA Bitiş", type: "date" },
];

function DashboardKPI({ icon: Icon, label, value, suffix, accent }) {
  return (
    <div className="card card-hover p-5 fade-in">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center mb-3 ${accent || "bg-[var(--primary)]/10 text-[var(--primary)]"}`}>
        <Icon size={20} />
      </div>
      <div className="text-xs text-[var(--text-dim)] tracking-wider uppercase">{label}</div>
      <div className="font-display text-3xl mt-1">{value}{suffix && <span className="text-base text-[var(--text-dim)] ml-1">{suffix}</span>}</div>
    </div>
  );
}

const TASK_STATUS_LABELS = {
  planlandi: "Planlandı", atandi: "Atandı", kabul_edildi: "Kabul Edildi",
  reddedildi: "Reddedildi", yola_cikildi: "Yola Çıkıldı", yerine_ulasildi: "Görev Yerine Ulaşıldı",
  calisiliyor: "Çalışılıyor", tamamlandi: "Tamamlandı", onay_bekliyor: "Yönetici Onayı Bekliyor",
  kapandi: "Kapandı", iptal_edildi: "İptal Edildi",
};

// backend/field_ops.py'deki TASK_ALLOWED_TRANSITIONS'ın client-side TAHMİNİ —
// sürükle-bırak hedefini önermek için, gerçek doğrulama backend'de.
const ALLOWED_NEXT = {
  planlandi: ["atandi", "iptal_edildi"],
  atandi: ["kabul_edildi", "reddedildi", "iptal_edildi"],
  kabul_edildi: ["yola_cikildi", "iptal_edildi"],
  yola_cikildi: ["yerine_ulasildi", "iptal_edildi"],
  yerine_ulasildi: ["calisiliyor", "iptal_edildi"],
  calisiliyor: ["tamamlandi", "iptal_edildi"],
  tamamlandi: ["onay_bekliyor", "iptal_edildi"],
  onay_bekliyor: ["kapandi", "iptal_edildi"],
  reddedildi: ["planlandi", "iptal_edildi"],
  kapandi: [], iptal_edildi: [],
};

// Kanban sütunu -> o sütuna karşılık gelen backend durum(lar)ı.
const KANBAN_COLUMNS = [
  { key: "planlandi", label: "Planlandı", statuses: ["planlandi"] },
  { key: "atandi", label: "Atandı", statuses: ["atandi"] },
  { key: "kabul_edildi", label: "Kabul Edildi", statuses: ["kabul_edildi"] },
  { key: "yolda", label: "Yolda", statuses: ["yola_cikildi"] },
  { key: "sahada", label: "Sahada", statuses: ["yerine_ulasildi", "calisiliyor"] },
  { key: "tamamlandi", label: "Tamamlandı", statuses: ["tamamlandi"] },
  { key: "onay_bekliyor", label: "Onay Bekliyor", statuses: ["onay_bekliyor"] },
  { key: "kapandi", label: "Kapandı", statuses: ["kapandi"] },
  { key: "iptal", label: "Reddedildi / İptal", statuses: ["reddedildi", "iptal_edildi"] },
];

function pickDropTargetStatus(columnStatuses, currentStatus) {
  const allowed = ALLOWED_NEXT[currentStatus] || [];
  return columnStatuses.find((s) => allowed.includes(s)) || columnStatuses[0];
}

export default function SahaOperasyonlari() {
  // IT-41 — Raporlar menüsünden "?view=raporlar" ile doğrudan Raporlar
  // sekmesine açılabilir (?task= ile AYNI window.location.search kalıbı,
  // bkz. aşağıdaki selectedTaskId) — parametre yoksa eskisi gibi "kanban".
  const [view, setView] = useState(() => new URLSearchParams(window.location.search).get("view") || "kanban"); // "kanban" | "takvim" | "dashboard" | "raporlar"
  const [dashboard, setDashboard] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [taskTypes, setTaskTypes] = useState([]);
  const [staff, setStaff] = useState([]);
  const [farmers, setFarmers] = useState([]);
  const [parcels, setParcels] = useState([]);
  // Haritadan "görev detayına git" — ?task=<id> ile açılır (bkz. HaritaPaneli.jsx popup'ı).
  const [selectedTaskId, setSelectedTaskId] = useState(() => new URLSearchParams(window.location.search).get("task"));
  const [dragTaskId, setDragTaskId] = useState(null);
  const [error, setError] = useState("");
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const [newTaskForm, setNewTaskForm] = useState({ task_type_id: "", assigned_to: "", parcel_id: "", planned_date: "" });

  const load = () => api.get("/tasks").then((r) => setTasks(r.data));

  useEffect(() => {
    load();
    api.get("/task-types").then((r) => setTaskTypes(r.data));
    api.get("/field-ops/assignable-users").then((r) => setStaff(r.data));
    api.get("/farmers", { params: { limit: 500 } }).then((r) => setFarmers(r.data));
    api.get("/parcels", { params: { limit: 1200 } }).then((r) => setParcels(r.data));
    api.get("/field-ops/dashboard").then((r) => setDashboard(r.data));
  }, []);

  const farmersById = useMemo(() => new Map(farmers.map((f) => [f.id, f])), [farmers]);
  const parcelsById = useMemo(() => new Map(parcels.map((p) => [p.id, p])), [parcels]);
  const staffById = useMemo(() => new Map(staff.map((s) => [s.id, s])), [staff]);
  const taskTypesById = useMemo(() => new Map(taskTypes.map((t) => [t.id, t])), [taskTypes]);

  const selectedTask = tasks.find((t) => t.id === selectedTaskId) || null;

  async function transitionTask(taskId, status) {
    setError("");
    try {
      await api.put(`/tasks/${taskId}/transition`, { status });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Durum değiştirilemedi");
    }
  }

  async function toggleChecklist(taskId, item, done) {
    await api.put(`/tasks/${taskId}/checklist`, { item, done });
    load();
  }

  function onDrop(column) {
    if (!dragTaskId) return;
    const task = tasks.find((t) => t.id === dragTaskId);
    setDragTaskId(null);
    if (!task) return;
    if (column.statuses.includes(task.status)) return; // aynı sütuna bırakıldı
    const target = pickDropTargetStatus(column.statuses, task.status);
    transitionTask(task.id, target);
  }

  async function submitNewTask(e) {
    e.preventDefault();
    try {
      const parcel = parcelsById.get(newTaskForm.parcel_id);
      await api.post("/tasks", {
        ...newTaskForm,
        farmer_id: parcel?.farmer_id || null,
      });
      setNewTaskOpen(false);
      setNewTaskForm({ task_type_id: "", assigned_to: "", parcel_id: "", planned_date: "" });
      load();
    } catch (err) {
      setError(err.response?.data?.detail || "Görev oluşturulamadı");
    }
  }

  // Takvim — planned_date'e göre günlere gruplanır (basit hafta/liste görünümü,
  // yeni bir takvim kütüphanesi eklenmedi — bilinçli sadelik).
  const tasksByDay = useMemo(() => {
    const map = new Map();
    for (const t of tasks) {
      const day = (t.planned_date || "").slice(0, 10);
      if (!map.has(day)) map.set(day, []);
      map.get(day).push(t);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [tasks]);

  return (
    <div className="p-8 max-w-[1800px]" data-testid="saha-operasyonlari-page">
      <header className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">SAHA OPERASYONLARI</div>
          <h1 className="font-display text-4xl">Görev Yönetimi</h1>
          <p className="text-[var(--text-dim)] text-sm mt-1">İş Emri / Görev / Ziyaret — Kanban ve Takvim görünümü</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setView("kanban")} className={`btn text-sm ${view === "kanban" ? "btn-primary" : "btn-ghost"}`}>
            <KanbanIcon size={14}/> Kanban
          </button>
          <button onClick={() => setView("takvim")} className={`btn text-sm ${view === "takvim" ? "btn-primary" : "btn-ghost"}`}>
            <CalendarIcon size={14}/> Takvim
          </button>
          <button onClick={() => setView("dashboard")} className={`btn text-sm ${view === "dashboard" ? "btn-primary" : "btn-ghost"}`} data-testid="view-dashboard-btn">
            <LayoutDashboard size={14}/> Dashboard
          </button>
          <button onClick={() => setView("raporlar")} className={`btn text-sm ${view === "raporlar" ? "btn-primary" : "btn-ghost"}`} data-testid="view-raporlar-btn">
            <Table2 size={14}/> Raporlar
          </button>
          <button onClick={() => setNewTaskOpen(true)} className="btn btn-primary text-sm" data-testid="new-field-task-btn">
            <Plus size={14}/> Yeni Görev
          </button>
        </div>
      </header>

      {error && <div className="text-xs text-red-400 p-2 bg-red-500/10 rounded mb-4">{error}</div>}

      {view === "dashboard" ? (
        <div data-testid="field-ops-dashboard">
          {!dashboard ? (
            <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <DashboardKPI icon={ClipboardList} label="Aktif İş Emirleri" value={dashboard.active_work_orders} accent="bg-blue-500/10 text-blue-400"/>
                <DashboardKPI icon={KanbanIcon} label="Aktif Görevler" value={dashboard.active_tasks} accent="bg-emerald-500/10 text-emerald-400"/>
                <DashboardKPI icon={AlertTriangle} label="Geciken Görevler" value={dashboard.overdue_tasks} accent="bg-red-500/10 text-red-400"/>
                <DashboardKPI icon={CalendarCheck} label="Bugünkü Ziyaretler" value={dashboard.today_visits} accent="bg-amber-500/10 text-amber-400"/>
                <DashboardKPI icon={Timer} label="Ort. Tamamlanma Süresi" value={dashboard.avg_completion_hours ?? "—"} suffix={dashboard.avg_completion_hours != null ? "saat" : ""} accent="bg-violet-500/10 text-violet-400"/>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="card p-5">
                  <h3 className="font-display text-lg mb-4 flex items-center gap-2"><Users2 size={16} className="text-[var(--primary)]"/>Personel Doluluk Oranı</h3>
                  <div className="space-y-2">
                    {dashboard.staff_utilization.map((s) => (
                      <div key={s.user_id} className="flex justify-between items-center text-sm border-b border-[var(--border)] pb-2">
                        <div>{s.full_name}</div>
                        <div className="font-mono text-[var(--primary)]">{s.active_tasks} aktif görev</div>
                      </div>
                    ))}
                    {dashboard.staff_utilization.length === 0 && (
                      <div className="text-sm text-[var(--text-dim)] py-4 text-center">Aktif görev yok</div>
                    )}
                  </div>
                </div>
                <div className="card p-5">
                  <h3 className="font-display text-lg mb-4 flex items-center gap-2"><Gauge size={16} className="text-[var(--primary)]"/>Bölgesel Operasyon Yoğunluğu</h3>
                  <div className="space-y-2">
                    {Object.entries(dashboard.regional_density).map(([region, count]) => (
                      <div key={region} className="flex justify-between items-center text-sm border-b border-[var(--border)] pb-2">
                        <div className="font-mono text-xs text-[var(--text-dim)]">{region}</div>
                        <div className="font-mono text-[var(--primary)]">{count}</div>
                      </div>
                    ))}
                    {Object.keys(dashboard.regional_density).length === 0 && (
                      <div className="text-sm text-[var(--text-dim)] py-4 text-center">Aktif görev yok</div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      ) : view === "raporlar" ? (
        <div data-testid="field-ops-reports">
          <SmartDataGrid module="field_tasks" columns={FIELD_TASKS_GRID_COLUMNS} defaultSort={[{ field: "planned_date", dir: "desc" }]} onRowClick={(row) => setSelectedTaskId(row.id)} />
        </div>
      ) : view === "kanban" ? (
        <div className="flex gap-3 overflow-x-auto pb-4" data-testid="kanban-board">
          {KANBAN_COLUMNS.map((col) => {
            const colTasks = tasks.filter((t) => col.statuses.includes(t.status));
            return (
              <div
                key={col.key}
                className="card p-3 min-w-[220px] w-[220px] shrink-0"
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(col)}
                data-testid={`kanban-col-${col.key}`}
              >
                <div className="text-xs font-medium text-[var(--text-dim)] uppercase tracking-wider mb-2 flex items-center justify-between">
                  {col.label} <span className="badge badge-neutral text-[10px]">{colTasks.length}</span>
                </div>
                <div className="space-y-2 min-h-[60px]">
                  {colTasks.map((t) => {
                    const parcel = parcelsById.get(t.parcel_id);
                    const person = staffById.get(t.assigned_to);
                    return (
                      <div
                        key={t.id}
                        draggable
                        onDragStart={() => setDragTaskId(t.id)}
                        onClick={() => setSelectedTaskId(t.id)}
                        className="p-2 rounded-lg bg-[var(--surface-2)] border border-[var(--border)] cursor-pointer hover:border-[var(--primary)] text-xs"
                        data-testid={`kanban-card-${t.id}`}
                      >
                        <div className="font-medium">{taskTypesById.get(t.task_type_id)?.name || t.task_type_id}</div>
                        {parcel && <div className="text-[var(--text-dim)] flex items-center gap-1 mt-1"><MapPin size={10}/>{parcel.parcel_code}</div>}
                        {person && <div className="text-[var(--text-dim)] flex items-center gap-1 mt-0.5"><User size={10}/>{person.full_name}</div>}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-4" data-testid="takvim-view">
          {tasksByDay.map(([day, dayTasks]) => (
            <div key={day} className="card p-4">
              <div className="font-display text-lg mb-2">{day || "Tarihsiz"}</div>
              <div className="space-y-2">
                {dayTasks.map((t) => {
                  const parcel = parcelsById.get(t.parcel_id);
                  const person = staffById.get(t.assigned_to);
                  return (
                    <div key={t.id} onClick={() => setSelectedTaskId(t.id)}
                         className="flex items-center justify-between text-sm p-2 rounded-lg bg-[var(--surface-2)] cursor-pointer hover:border-[var(--primary)] border border-transparent">
                      <div className="flex items-center gap-3">
                        <span className="badge badge-b text-[10px]">{TASK_STATUS_LABELS[t.status] || t.status}</span>
                        <span>{taskTypesById.get(t.task_type_id)?.name || t.task_type_id}</span>
                        {parcel && <span className="text-[var(--text-dim)] text-xs flex items-center gap-1"><MapPin size={10}/>{parcel.parcel_code}</span>}
                      </div>
                      {person && <span className="text-[var(--text-dim)] text-xs flex items-center gap-1"><User size={11}/>{person.full_name}</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          {tasksByDay.length === 0 && <div className="text-center text-[var(--text-dim)] py-10">Görev yok</div>}
        </div>
      )}

      {/* GÖREV DETAY DRAWER */}
      <Drawer open={!!selectedTask} onClose={() => setSelectedTaskId(null)} title={selectedTask ? (taskTypesById.get(selectedTask.task_type_id)?.name || "Görev") : ""}>
        {selectedTask && (
          <div className="p-4 space-y-4">
            <div>
              <span className={`badge badge-b`}>{TASK_STATUS_LABELS[selectedTask.status] || selectedTask.status}</span>
              {selectedTask.close_reason && <div className="text-xs text-red-400 mt-1">{selectedTask.close_reason}</div>}
            </div>
            <div className="text-sm space-y-1">
              <div><span className="text-[var(--text-dim)]">Parsel:</span> {parcelsById.get(selectedTask.parcel_id)?.parcel_code || "—"}</div>
              <div><span className="text-[var(--text-dim)]">Çiftçi:</span> {farmersById.get(selectedTask.farmer_id)?.full_name || "—"}</div>
              <div><span className="text-[var(--text-dim)]">Atanan:</span> {staffById.get(selectedTask.assigned_to)?.full_name || "—"}</div>
              <div><span className="text-[var(--text-dim)]">Planlanan tarih:</span> {selectedTask.planned_date}</div>
            </div>

            <div>
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2 flex items-center gap-1"><ListChecks size={12}/> Checklist</div>
              <div className="space-y-1">
                {(selectedTask.checklist || []).map((c) => (
                  <label key={c.item} className="flex items-center gap-2 text-sm p-1.5 rounded bg-[var(--surface-2)] cursor-pointer">
                    <input type="checkbox" checked={c.done} onChange={(e) => toggleChecklist(selectedTask.id, c.item, e.target.checked)} data-testid={`checklist-${c.item}`}/>
                    {c.item}
                  </label>
                ))}
                {(selectedTask.checklist || []).length === 0 && <div className="text-xs text-[var(--text-dim)]">Checklist yok</div>}
              </div>
            </div>

            <div>
              <div className="text-xs text-[var(--text-dim)] uppercase tracking-wider mb-2">Durum Değiştir</div>
              <div className="flex flex-wrap gap-2">
                {(ALLOWED_NEXT[selectedTask.status] || []).map((s) => (
                  <button key={s} onClick={() => transitionTask(selectedTask.id, s)}
                          className={`btn text-xs ${s === "iptal_edildi" || s === "reddedildi" ? "btn-ghost text-red-400" : "btn-primary"}`}
                          data-testid={`task-transition-${s}`}>
                    <Check size={12}/> {TASK_STATUS_LABELS[s]}
                  </button>
                ))}
                {(ALLOWED_NEXT[selectedTask.status] || []).length === 0 && <div className="text-xs text-[var(--text-dim)]">Bu durum terminaldir</div>}
              </div>
            </div>
          </div>
        )}
      </Drawer>

      {/* YENİ GÖREV MODAL */}
      {newTaskOpen && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => setNewTaskOpen(false)}>
          <form onSubmit={submitNewTask} className="card max-w-md w-full p-6 space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="font-display text-xl">Yeni Görev</h3>
              <button type="button" onClick={() => setNewTaskOpen(false)}><X size={18}/></button>
            </div>
            <select className="input" required value={newTaskForm.task_type_id} onChange={(e) => setNewTaskForm((f) => ({ ...f, task_type_id: e.target.value }))}>
              <option value="">Görev tipi seç...</option>
              {taskTypes.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <select className="input" required value={newTaskForm.assigned_to} onChange={(e) => setNewTaskForm((f) => ({ ...f, assigned_to: e.target.value }))}>
              <option value="">Personel seç...</option>
              {staff.map((s) => <option key={s.id} value={s.id}>{s.full_name} ({s.role})</option>)}
            </select>
            <select className="input" value={newTaskForm.parcel_id} onChange={(e) => setNewTaskForm((f) => ({ ...f, parcel_id: e.target.value }))}>
              <option value="">Parsel seç (opsiyonel)...</option>
              {parcels.slice(0, 300).map((p) => <option key={p.id} value={p.id}>{p.parcel_code} — {p.name}</option>)}
            </select>
            <input type="date" className="input" required value={newTaskForm.planned_date} onChange={(e) => setNewTaskForm((f) => ({ ...f, planned_date: e.target.value }))}/>
            <button type="submit" className="btn btn-primary w-full justify-center">Oluştur</button>
          </form>
        </div>
      )}
    </div>
  );
}
