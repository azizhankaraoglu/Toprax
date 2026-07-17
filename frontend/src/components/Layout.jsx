import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import api from "@/api";
import ErrorBoundary from "@/components/ErrorBoundary";
import {
  Wheat, LayoutDashboard, Users, Map, FileText, Sprout, Droplets,
  Settings2, BarChart3, Truck, Bell, LogOut, Award, ChevronRight, FlaskConical,
  Satellite, Brain, Smartphone, Receipt, FileSpreadsheet, Scale, Activity, Settings, Sparkles,
  UserCog, ShieldCheck, ListTree, LayoutList, Search, Landmark, Compass, Wallet, LineChart, Kanban, Zap, MessagesSquare, Megaphone, ShieldOff, GraduationCap, Cable, SlidersHorizontal, ClipboardCheck,
  Workflow, CheckSquare, Inbox, Code2, Radio
} from "lucide-react";
import WorkspaceDrawer from "@/components/WorkspaceDrawer";
import AnnouncementPopup from "@/components/AnnouncementPopup";

// Sadece bu roller Ayarlar/Audit Log'u görebilir (backend'deki
// ADMIN_TIER_ROLES ile tutarlı — config.py).
const ADMIN_TIER_ROLES = new Set(["super_admin", "kurum_yoneticisi", "il_yoneticisi", "fabrika_muduru"]);

// Sidebar menüsü gruplandırılmış halde
const navGroups = [
  {
    title: "ANA",
    items: [
      { to: "/", icon: LayoutDashboard, label: "Dashboard", end: true },
      { to: "/arama", icon: Search, label: "Global Arama" },
      { to: "/ciftciler", icon: Users, label: "Çiftçiler" },
      { to: "/parseller", icon: Map, label: "Parseller" },
      { to: "/harita-paneli", icon: Compass, label: "Harita Paneli" },
      { to: "/idari-alanlar", icon: Landmark, label: "İdari Alanlar" },
    ]
  },
  {
    title: "ÜRETİM",
    items: [
      { to: "/sozlesmeler", icon: FileText, label: "Sözleşme & Kota" },
      { to: "/ekim", icon: Sprout, label: "Ekim Planlama" },
      { to: "/sulama", icon: Droplets, label: "Sulama & Kaynak" },
      { to: "/operasyon", icon: Settings2, label: "Operasyon" },
    ]
  },
  {
    title: "ANALİZ & AI",
    items: [
      { to: "/uydu", icon: Satellite, label: "Uydu / NDVI" },
      { to: "/uzaktan-algilama", icon: Satellite, label: "Uzaktan Algılama" },
      { to: "/copilot", icon: Sparkles, label: "AI Copilot", featureFlag: "ai" },
      { to: "/hastalik", icon: Brain, label: "AI Hastalık", featureFlag: "ai" },
    ]
  },
  {
    title: "SAHA & LOJİSTİK",
    items: [
      { to: "/saha-operasyonlari", icon: Kanban, label: "Görev Yönetimi" },
      { to: "/otomasyon-kurallari", icon: Zap, label: "Otomasyon Kuralları" },
      { to: "/saha", icon: Smartphone, label: "Saha Mobil" },
      { to: "/formlar", icon: FileSpreadsheet, label: "Formlar & Anket" },
      { to: "/lojistik", icon: Truck, label: "Lojistik & Randevu" },
      { to: "/kantar", icon: Scale, label: "Kantar" },
    ]
  },
  {
    // IT-41 — tüm rapor/analiz ekranları tek menüde toplandı (önceden
    // ÜRETİM/ANALİZ & AI/BELGE & FİNANS'a dağılmıştı). Route'lar DEĞİŞMEDİ,
    // sadece nav kaydı taşındı — her rapor kendi filtresini/SmartDataGrid'ini
    // korur (bkz. ROADMAP-DETAY-TAM.md FAZ 14 / IT-41).
    title: "RAPORLAR",
    items: [
      { to: "/toprak", icon: FlaskConical, label: "Toprak Analizleri" },
      { to: "/saha-operasyonlari?view=raporlar", icon: ClipboardCheck, label: "Saha Raporları" },
      { to: "/verimlilik", icon: BarChart3, label: "Verimlilik" },
      { to: "/karne", icon: Award, label: "Çiftçi Karne" },
      { to: "/ufyd-dashboard", icon: LineChart, label: "UFYD Dashboard" },
    ]
  },
  {
    title: "BELGE & FİNANS",
    items: [
      { to: "/e-fatura", icon: Receipt, label: "E-Faturalar" },
      { to: "/irsaliye", icon: FileSpreadsheet, label: "İrsaliyeler" },
    ]
  },
  {
    title: "EĞİTİM",
    items: [
      { to: "/egitim-yonetimi", icon: GraduationCap, label: "Eğitim Yönetimi", featureFlag: "lms" },
    ]
  },
  {
    title: "SİSTEM",
    items: [
      { to: "/bildirimler", icon: Bell, label: "Bildirimler" },
      { to: "/audit", icon: Activity, label: "Audit Log", adminTierOnly: true },
      { to: "/kullanicilar", icon: UserCog, label: "Kullanıcılar", adminTierOnly: true },
      { to: "/ozel-roller", icon: ShieldCheck, label: "Özel Roller", adminTierOnly: true },
      { to: "/alan-tanimlari", icon: LayoutList, label: "Form Yönetimi", adminTierOnly: true },
      { to: "/lookup-yonetimi", icon: ListTree, label: "Lookup Yönetimi", adminTierOnly: true },
      { to: "/destek-katalogu", icon: Wallet, label: "Destek Kataloğu", adminTierOnly: true },
      { to: "/sablon-yonetimi", icon: MessagesSquare, label: "Şablon Yönetimi", adminTierOnly: true },
      { to: "/duyuru-yonetimi", icon: Radio, label: "Duyuru Yönetimi", adminTierOnly: true },
      { to: "/kampanyalar", icon: Megaphone, label: "Kampanyalar" },
      { to: "/iletisim-politikalari", icon: ShieldOff, label: "İletişim Politikaları", adminTierOnly: true },
      { to: "/organizasyon-hiyerarsisi", icon: Workflow, label: "Organizasyon Hiyerarşisi", adminTierOnly: true },
      { to: "/onay-bekleyenlerim", icon: CheckSquare, label: "Onay Bekleyenlerim" },
      { to: "/bize-ulasin", icon: Inbox, label: "Bize Ulaşın" },
      { to: "/integration-hub", icon: Cable, label: "Integration Hub" },
      { to: "/gelistirici-portali", icon: Code2, label: "Geliştirici Portalı", adminTierOnly: true },
      { to: "/platform-core", icon: SlidersHorizontal, label: "Platform Core" },
      { to: "/ai-bilgi-kutuphanesi", icon: Brain, label: "AI Bilgi Kütüphanesi", featureFlag: "ai" },
      { to: "/experience-profiles", icon: Smartphone, label: "Experience Profile" },
      { to: "/ayarlar", icon: Settings, label: "Ayarlar", adminTierOnly: true },
    ]
  }
];

export default function Layout() {
  const nav = useNavigate();
  const location = useLocation();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [mobileOpen, setMobileOpen] = useState(false);
  // IT-33 — Feature Flags: kapatılan bir özelliğin menüsü GERÇEKTEN gizlenir
  // (backend zaten 403 döner, bu sadece kullanıcı deneyimini tutarlı kılar).
  // Henüz yüklenmemiş/bilinmeyen bir flag varsayılan AÇIK sayılır (flash-of-
  // hidden-item önlenir, platform_core.py'nin is_feature_enabled ile AYNI
  // "yoksa açık" varsayımı).
  const [flagsByKey, setFlagsByKey] = useState({});
  useEffect(() => {
    api.get("/feature-flags").then((r) => {
      setFlagsByKey(Object.fromEntries(r.data.map((f) => [f.key, f.enabled])));
    }).catch(() => {});
  }, []);

  function logout() { localStorage.clear(); nav("/login"); }

  return (
    <div className="flex min-h-screen bg-[var(--bg)]">
      {/* Mobile hamburger */}
      <button
        onClick={() => setMobileOpen(!mobileOpen)}
        className="md:hidden fixed top-4 left-4 z-50 w-10 h-10 rounded-lg bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center"
      >
        <span className="text-xl">☰</span>
      </button>

      <aside className={`w-64 bg-[var(--bg)] border-r border-[var(--border)] flex flex-col fixed h-screen z-40 transition-transform ${mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}`}>
        <div className="p-5 border-b border-[var(--border)]">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-[var(--primary)] flex items-center justify-center">
              <Wheat size={18} className="text-white"/>
            </div>
            <div>
              <div className="font-display text-lg leading-none">Toprax</div>
              <div className="text-[10px] text-[var(--text-dim)] tracking-widest mt-0.5">KOOPERATİF EDİSYONU</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto scrollbar p-3">
          {navGroups.map((g) => {
            const visibleItems = g.items.filter((item) =>
              (!item.adminTierOnly || ADMIN_TIER_ROLES.has(user.role)) &&
              (!item.featureFlag || flagsByKey[item.featureFlag] !== false)
            );
            if (visibleItems.length === 0) return null;
            return (
              <div key={g.title} className="mb-3">
                <div className="text-[10px] text-[var(--text-dim)] tracking-widest px-3 mb-1 mt-2">{g.title}</div>
                {visibleItems.map((item) => {
                  // IT-41 — bazı rapor kayıtları ("/saha-operasyonlari?view=raporlar"
                  // gibi) bir sorgu parametresi taşır. NavLink'in isActive'i
                  // sadece pathname'e bakar (search'ü yok sayar), bu yüzden
                  // sorgu parametreli bir kayıtla aynı pathname'i paylaşan
                  // başka bir menü öğesi (ör. "Görev Yönetimi") yanlışlıkla
                  // birlikte aktif görünmesin diye search da elle karşılaştırılır.
                  const [toPath, toQuery] = item.to.split("?");
                  return (
                    <NavLink key={item.to} to={item.to} end={item.end}
                             onClick={() => setMobileOpen(false)}
                             data-testid={`nav-${toPath.replace("/", "") || "home"}`}
                             className={({ isActive }) => {
                               const active = isActive && (!toQuery || window.location.search.includes(toQuery));
                               return `group flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                                 active ? "bg-[var(--primary)]/10 text-[var(--primary)]" : "text-[var(--text-dim)] hover:bg-[var(--surface)] hover:text-white"
                               }`;
                             }}>
                      <item.icon size={15}/>
                      <span>{item.label}</span>
                    </NavLink>
                  );
                })}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-[var(--border)] p-3">
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--primary)] to-[var(--primary-dark)] flex items-center justify-center text-white font-bold text-sm">
              {(user.full_name || "?").charAt(0)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm truncate">{user.full_name || "Kullanıcı"}</div>
              <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider">{user.role || ""}</div>
            </div>
            <WorkspaceDrawer />
            <button data-testid="logout-button" onClick={logout} className="text-[var(--text-dim)] hover:text-[var(--danger)]"><LogOut size={16}/></button>
          </div>
        </div>
      </aside>

      <main className="flex-1 md:ml-64 min-h-screen pt-14 md:pt-0">
        <ErrorBoundary resetKey={location.pathname}><Outlet /></ErrorBoundary>
      </main>
      <AnnouncementPopup />
    </div>
  );
}
