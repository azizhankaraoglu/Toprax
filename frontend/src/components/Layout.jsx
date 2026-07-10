import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Wheat, LayoutDashboard, Users, Map, FileText, Sprout, Droplets,
  Settings2, BarChart3, Truck, Bell, LogOut, Award, ChevronRight, FlaskConical,
  Satellite, Brain, Smartphone, Receipt, FileSpreadsheet, Scale, Activity, Settings, Sparkles,
  UserCog, ShieldCheck
} from "lucide-react";

// Sadece bu roller Ayarlar/Audit Log'u görebilir (backend'deki
// ADMIN_TIER_ROLES ile tutarlı — config.py).
const ADMIN_TIER_ROLES = new Set(["super_admin", "kurum_yoneticisi", "il_yoneticisi", "fabrika_muduru"]);

// Sidebar menüsü gruplandırılmış halde
const navGroups = [
  {
    title: "ANA",
    items: [
      { to: "/", icon: LayoutDashboard, label: "Dashboard", end: true },
      { to: "/ciftciler", icon: Users, label: "Çiftçiler" },
      { to: "/parseller", icon: Map, label: "Parseller" },
    ]
  },
  {
    title: "ÜRETİM",
    items: [
      { to: "/sozlesmeler", icon: FileText, label: "Sözleşme & Kota" },
      { to: "/ekim", icon: Sprout, label: "Ekim Planlama" },
      { to: "/toprak", icon: FlaskConical, label: "Toprak Bilgisi" },
      { to: "/sulama", icon: Droplets, label: "Sulama & Kaynak" },
      { to: "/operasyon", icon: Settings2, label: "Operasyon" },
    ]
  },
  {
    title: "ANALİZ & AI",
    items: [
      { to: "/verimlilik", icon: BarChart3, label: "Verimlilik" },
      { to: "/uydu", icon: Satellite, label: "Uydu / NDVI" },
      { to: "/copilot", icon: Sparkles, label: "AI Copilot" },
      { to: "/hastalik", icon: Brain, label: "AI Hastalık" },
    ]
  },
  {
    title: "SAHA & LOJİSTİK",
    items: [
      { to: "/saha", icon: Smartphone, label: "Saha Mobil" },
      { to: "/formlar", icon: FileSpreadsheet, label: "Formlar & Anket" },
      { to: "/lojistik", icon: Truck, label: "Lojistik & Randevu" },
      { to: "/kantar", icon: Scale, label: "Kantar" },
    ]
  },
  {
    title: "BELGE & FİNANS",
    items: [
      { to: "/e-fatura", icon: Receipt, label: "E-Faturalar" },
      { to: "/irsaliye", icon: FileSpreadsheet, label: "İrsaliyeler" },
      { to: "/karne", icon: Award, label: "Çiftçi Karne" },
    ]
  },
  {
    title: "SİSTEM",
    items: [
      { to: "/bildirimler", icon: Bell, label: "Bildirimler" },
      { to: "/audit", icon: Activity, label: "Audit Log", adminTierOnly: true },
      { to: "/kullanicilar", icon: UserCog, label: "Kullanıcılar", adminTierOnly: true },
      { to: "/ozel-roller", icon: ShieldCheck, label: "Özel Roller", adminTierOnly: true },
      { to: "/ayarlar", icon: Settings, label: "Ayarlar", adminTierOnly: true },
    ]
  }
];

export default function Layout() {
  const nav = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [mobileOpen, setMobileOpen] = useState(false);

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

      <aside className={`w-64 bg-[#070b09] border-r border-[var(--border)] flex flex-col fixed h-screen z-40 transition-transform ${mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}`}>
        <div className="p-5 border-b border-[var(--border)]">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-[var(--primary)] flex items-center justify-center">
              <Wheat size={18} className="text-[#052e16]"/>
            </div>
            <div>
              <div className="font-display text-lg leading-none">TabSIS</div>
              <div className="text-[10px] text-[var(--text-dim)] tracking-widest mt-0.5">KOOPERATİF EDİSYONU</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto scrollbar p-3">
          {navGroups.map((g) => {
            const visibleItems = g.items.filter((item) => !item.adminTierOnly || ADMIN_TIER_ROLES.has(user.role));
            if (visibleItems.length === 0) return null;
            return (
              <div key={g.title} className="mb-3">
                <div className="text-[10px] text-[var(--text-dim)] tracking-widest px-3 mb-1 mt-2">{g.title}</div>
                {visibleItems.map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.end}
                           onClick={() => setMobileOpen(false)}
                           data-testid={`nav-${item.to.replace("/", "") || "home"}`}
                           className={({ isActive }) => `group flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                             isActive ? "bg-[var(--primary)]/10 text-[var(--primary)]" : "text-[var(--text-dim)] hover:bg-[var(--surface)] hover:text-white"
                           }`}>
                    <item.icon size={15}/>
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-[var(--border)] p-3">
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--primary)] to-[var(--primary-dark)] flex items-center justify-center text-[#052e16] font-bold text-sm">
              {(user.full_name || "?").charAt(0)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm truncate">{user.full_name || "Kullanıcı"}</div>
              <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider">{user.role || ""}</div>
            </div>
            <button data-testid="logout-button" onClick={logout} className="text-[var(--text-dim)] hover:text-[var(--danger)]"><LogOut size={16}/></button>
          </div>
        </div>
      </aside>

      <main className="flex-1 md:ml-64 min-h-screen pt-14 md:pt-0"><Outlet /></main>
    </div>
  );
}
