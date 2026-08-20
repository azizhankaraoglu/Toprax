import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import api from "@/api";
import ErrorBoundary from "@/components/ErrorBoundary";
import {
  Wheat, LayoutDashboard, Users, Map, FileText, Sprout, Droplets,
  Settings2, BarChart3, Truck, Bell, LogOut, Award, ChevronRight, FlaskConical,
  Satellite, Brain, Smartphone, Receipt, FileSpreadsheet, Scale, Activity, Sparkles,
  UserCog, ShieldCheck, LayoutList, Landmark, Compass, LineChart, Kanban, Zap, MessagesSquare, Megaphone, ShieldOff, GraduationCap, Cable, ClipboardCheck,
  Workflow, CheckSquare, Inbox, Radio, FileBarChart2, Layers,
  CalendarClock, Bug, Factory, BrainCircuit, Leaf
} from "lucide-react";
import WorkspaceDrawer from "@/components/WorkspaceDrawer";
import AnnouncementPopup from "@/components/AnnouncementPopup";
import { getTheme, setTheme } from "@/lib/theme";
import { Sun, Moon } from "lucide-react";

// Sadece bu roller Ayarlar/Audit Log'u görebilir (backend'deki
// ADMIN_TIER_ROLES ile tutarlı — config.py).
const ADMIN_TIER_ROLES = new Set(["super_admin", "kurum_yoneticisi", "il_yoneticisi", "fabrika_muduru"]);

// Sidebar menüsü — SON HAL yeniden sınıflandırması (kullanıcı talebi):
// "Ana Alan" sadece 4 çekirdek varlığı taşır; Harita Paneli SAHA &
// LOJİSTİK'e, İdari Alanlar SİSTEM'e taşındı; iletişim ekranları yeni
// İLETİŞİM grubunda toplandı. Route'lar DEĞİŞMEDİ — sadece nav kayıtları
// taşındı (IT-41 emsali). Global Arama nav kaydı kaldırıldı: arama artık
// Dashboard'un üstünde gömülü (bkz. Dashboard.jsx), /arama → / yönlenir.
const navGroups = [
  {
    title: "ANA ALAN",
    items: [
      { to: "/", icon: LayoutDashboard, label: "Dashboard", end: true },
      { to: "/ciftciler", icon: Users, label: "Çiftçiler", featureFlag: "farmer" },
      { to: "/parseller", icon: Map, label: "Parseller", featureFlag: "parcel" },
      { to: "/sozlesmeler", icon: FileText, label: "Sözleşmeler", featureFlag: "contracts" },
    ]
  },
  // 2026-08-19 — KARAR DESTEK grubu. Kullanıcı isteği: "katma değeri yüksek
  // alanları ön planda tut (ne zaman ekmeliyim / ne zaman sökmeliyim, polar
  // iyileştirme, karbon ayak izi gibi)". Bu ekranlar önceden ÜRETİM grubunun
  // içinde, veri girişi ağırlıklı CRUD ekranlarının (Toprak Analizleri,
  // Operasyon...) arasında kayboluyordu. Platformun asıl farkı bunlar olduğu
  // için ANA ALAN'ın hemen ardına, kendi başlığı altına alındılar.
  {
    title: "KARAR DESTEK",
    items: [
      { to: "/ekim?view=karar-motoru", icon: Sprout, label: "Ne Ekmeliyim? (Karar Motoru)", featureFlag: "planting" },
      { to: "/sezon-karar-takvimi", icon: CalendarClock, label: "Sezon Karar Takvimi" },
      { to: "/hasat-lojistigi", icon: Factory, label: "Ne Zaman Sökmeliyim? (Hasat)" },
      { to: "/urun-tanima", icon: Sprout, label: "Ürün Tanıma (Uydu)", featureFlag: "remote_sensing" },
      { to: "/karbon-ayak-izi", icon: Leaf, label: "Karbon Ayak İzi" },
      { to: "/uzaktan-algilama", icon: Satellite, label: "Uzaktan Algılama", featureFlag: "remote_sensing" },
    ]
  },
  {
    title: "ÜRETİM",
    items: [
      { to: "/ekim", icon: Sprout, label: "Ekim Planlama", featureFlag: "planting" },
      { to: "/sulama", icon: Droplets, label: "Sulama & Kaynak", featureFlag: "irrigation" },
      { to: "/operasyon", icon: Settings2, label: "Operasyon", featureFlag: "operations" },
      { to: "/toprak", icon: FlaskConical, label: "Toprak Analizleri", featureFlag: "soil" },
      { to: "/toprak-biyolojisi", icon: Bug, label: "Toprak Biyolojisi" },
    ]
  },
  {
    title: "ANALİZ & AI",
    items: [
      { to: "/uydu", icon: Satellite, label: "Uydu / NDVI", featureFlag: "remote_sensing" },
      { to: "/copilot", icon: Sparkles, label: "AI Copilot", featureFlag: "ai" },
      { to: "/hastalik", icon: Brain, label: "AI Hastalık", featureFlag: "ai" },
      { to: "/ai-bilgi-kutuphanesi", icon: Brain, label: "AI Bilgi Kütüphanesi", featureFlag: "ai" },
      // 2026-08-19 — TÜM AI çıktısının prompt/guardrail/RAG otoritesi.
      // Kullanıcı isteği gereği SADECE admin katmanı görür; backend ayrıca
      // ai_governance:view/manage izinlerini zorunlu kılar (menüden gizlemek
      // tek başına güvenlik önlemi değildir).
      { to: "/ai-yonetimi", icon: BrainCircuit, label: "AI Yönetişimi", adminTierOnly: true, featureFlag: "ai" },
    ]
  },
  {
    title: "SAHA & LOJİSTİK",
    items: [
      { to: "/harita-paneli", icon: Compass, label: "Harita Paneli", featureFlag: "gis" },
      { to: "/harita-studyosu", icon: Layers, label: "Harita Stüdyosu", featureFlag: "map_studio" },
      { to: "/saha-operasyonlari", icon: Kanban, label: "Görev Yönetimi", featureFlag: "field_ops" },
      { to: "/otomasyon-kurallari", icon: Zap, label: "Otomasyon Kuralları", featureFlag: "automation" },
      { to: "/saha", icon: Smartphone, label: "Saha Mobil" },
      { to: "/formlar", icon: FileSpreadsheet, label: "Formlar & Anket", featureFlag: "forms" },
      { to: "/lojistik", icon: Truck, label: "Lojistik & Randevu", featureFlag: "logistics" },
      // 2026-08-19 — Hasat ekranından AYRILAN kampanya lojistiği (fabrika
      // kapasitesi/kantar/haftalık yük). Aynı sayfanın ?view=lojistik
      // sekmesi — IT-41'in "Saha Raporları" girdisiyle AYNI kalıp (pahalı
      // çizelge hesabı iki route'ta iki kez çalışmasın diye).
      { to: "/hasat-lojistigi?view=lojistik", icon: Factory, label: "Kampanya Lojistiği" },
      { to: "/kantar", icon: Scale, label: "Kantar", featureFlag: "factory" },
    ]
  },
  {
    // IT-41 — rapor ekranları tek menüde. Toprak Analizleri veri girişi
    // ağırlıklı olduğu için ÜRETİM'e taşındı (son hal kararı).
    title: "RAPORLAR",
    items: [
      { to: "/rapor-olusturucu", icon: FileBarChart2, label: "Rapor Oluşturucu", featureFlag: "report_builder" },
      { to: "/saha-operasyonlari?view=raporlar", icon: ClipboardCheck, label: "Saha Raporları", featureFlag: "reports" },
      { to: "/verimlilik", icon: BarChart3, label: "Verimlilik", featureFlag: "reports" },
      { to: "/karne", icon: Award, label: "Çiftçi Karne", featureFlag: "reports" },
      { to: "/ufyd-dashboard", icon: LineChart, label: "UFYD Dashboard", featureFlag: "ufyd" },
    ]
  },
  {
    title: "BELGE & FİNANS",
    items: [
      { to: "/e-fatura", icon: Receipt, label: "E-Faturalar", featureFlag: "invoicing" },
      { to: "/irsaliye", icon: FileSpreadsheet, label: "İrsaliyeler", featureFlag: "invoicing" },
    ]
  },
  {
    title: "İLETİŞİM",
    items: [
      { to: "/bildirimler", icon: Bell, label: "Bildirimler" },
      { to: "/duyuru-yonetimi", icon: Radio, label: "Duyuru Yönetimi", adminTierOnly: true, featureFlag: "communication" },
      { to: "/kampanyalar", icon: Megaphone, label: "Kampanyalar", featureFlag: "communication" },
      { to: "/sablon-yonetimi", icon: MessagesSquare, label: "Şablon Yönetimi", adminTierOnly: true, featureFlag: "communication" },
      { to: "/iletisim-politikalari", icon: ShieldOff, label: "İletişim Politikaları", adminTierOnly: true, featureFlag: "communication" },
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
      { to: "/kullanicilar", icon: UserCog, label: "Kullanıcılar", adminTierOnly: true },
      { to: "/ozel-roller", icon: ShieldCheck, label: "Özel Roller", adminTierOnly: true },
      // SON HAL #6 — Lookup Yönetimi + Destek Kataloğu, Form Yönetimi'nin
      // sekmelerine taşındı (aynı ekran ailesi); nav'da tek giriş kalır.
      { to: "/alan-tanimlari", icon: LayoutList, label: "Form Yönetimi", adminTierOnly: true },
      { to: "/idari-alanlar", icon: Landmark, label: "İdari Alanlar", featureFlag: "admin_areas" },
      { to: "/organizasyon-hiyerarsisi", icon: Workflow, label: "Organizasyon Hiyerarşisi", adminTierOnly: true, featureFlag: "organization" },
      { to: "/onay-bekleyenlerim", icon: CheckSquare, label: "Onay Bekleyenlerim", featureFlag: "approvals" },
      { to: "/bize-ulasin", icon: Inbox, label: "Bize Ulaşın", featureFlag: "case_management" },
      { to: "/integration-hub", icon: Cable, label: "Integration Hub", featureFlag: "integration_hub" },
      { to: "/audit", icon: Activity, label: "Audit Log", adminTierOnly: true, featureFlag: "audit" },
      // SON HAL (2026-07-23) — Geliştirici Portalı / Platform Core /
      // Experience Profile / Ayarlar buradan KALDIRILDI: kullanıcı isteği
      // üzerine bunlar artık kooperatifin kendi Sistem menüsünden değil,
      // God Mode > Tenant Yönetimi > "Sistem Ekranları" üzerinden (var olan
      // "Bu Kooperatif Olarak Gir" impersonation mekanizmasıyla) yönetiliyor
      // — bkz. PlatformAdmin.jsx. Route'lar App.js'te DURUYOR (impersonation
      // sonrası doğrudan o sayfaya yönlendirilir), sadece bu menüden kalktı.
    ]
  }
];

// Bir nav öğesi verilen pathname'i kapsıyor mu? ("/" sadece tam eşleşme;
// diğerleri detay rotalarını da kapsar: /ciftciler → /ciftciler/:id)
function itemMatchesPath(item, pathname) {
  const toPath = item.to.split("?")[0];
  if (toPath === "/") return pathname === "/";
  return pathname === toPath || pathname.startsWith(toPath + "/");
}

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

  // Kapanır-açılır gruplar — SON HAL #8: varsayılan artık KAPALI (kullanıcı
  // talebi: "Menülerde default kapalı gelsin"). {grupBaşlığı: true} = açık,
  // yoksa/false = kapalı — önceki tersti (varsayılan açık, false=kapalı).
  // localStorage'da saklanır; aktif rotayı içeren grup navigasyonda
  // otomatik açılır (kullanıcı sonradan elle kapatabilir).
  const [openGroups, setOpenGroups] = useState(() => {
    try { return JSON.parse(localStorage.getItem("toprax_nav_open") || "{}"); }
    catch { return {}; }
  });
  function persistOpenGroups(next) {
    setOpenGroups(next);
    try { localStorage.setItem("toprax_nav_open", JSON.stringify(next)); } catch {}
  }
  function toggleGroup(title) {
    persistOpenGroups({ ...openGroups, [title]: openGroups[title] !== true });
  }
  useEffect(() => {
    const active = navGroups.find((g) => g.items.some((it) => itemMatchesPath(it, location.pathname)));
    if (active && openGroups[active.title] !== true) {
      persistOpenGroups({ ...openGroups, [active.title]: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // Sayfa değişince mobil çekmece (sol menü overlay'i) HER ZAMAN kapanır —
  // sadece sidebar'daki NavLink'e tıklanınca değil (ör. bir sayfadan
  // "Ekim Karar Motoru"na programatik yönlendirme geldiğinde mobileOpen
  // takılı kalıp yeni sayfanın içeriğini menünün altında bırakıyordu).
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  // SON HAL #8 — "Sol panel yana doğru genişleyip daraltılabilir yapı
  // olmalı": sidebar artık daraltılabilir (ikon-rayı, 68px) / genişletilebilir
  // (tam, 256px) — tercih localStorage'da kalıcı. Sadece masaüstünde
  // (md+) anlamlı; mobil çekmece davranışı DEĞİŞMEDİ.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("toprax_nav_collapsed") === "1");
  function toggleCollapsed() {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem("toprax_nav_collapsed", next ? "1" : "0"); } catch {}
      return next;
    });
  }
  // Mobil çekmece açıkken masaüstü "daralt" tercihi YOK SAYILIR — dar bir
  // ikon rayı, tüm ekranı kaplayan mobil menüde anlamsız olurdu (etiketler
  // görünmeli). Sadece masaüstünde (mobileOpen=false, md+) daralma etkilidir.
  const effectiveCollapsed = collapsed && !mobileOpen;
  const sidebarWidthClass = effectiveCollapsed ? "w-[68px]" : "w-64";
  const mainMarginClass = collapsed ? "md:ml-[68px]" : "md:ml-64";

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

      <aside className={`${sidebarWidthClass} bg-[var(--bg)] border-r border-[var(--border)] flex flex-col fixed h-screen z-40 transition-[width,transform] duration-200 ${mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}`}>
        <div className="p-5 border-b border-[var(--border)] flex items-center gap-2">
          <div className="flex items-center gap-2.5 flex-1 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-[var(--primary)] flex items-center justify-center shrink-0">
              <Wheat size={18} className="text-white"/>
            </div>
            {!effectiveCollapsed && (
              <div className="min-w-0">
                <div className="font-display text-lg leading-none truncate">Toprax</div>
                <div className="text-[10px] text-[var(--text-dim)] tracking-widest mt-0.5 truncate">KOOPERATİF EDİSYONU</div>
              </div>
            )}
          </div>
          {/* SON HAL #8 — sol paneli daralt/genişlet düğmesi (sadece masaüstü;
              mobil zaten hamburger ile aç/kapa). Tercih kalıcıdır. */}
          <button
            onClick={toggleCollapsed}
            data-testid="sidebar-collapse-toggle"
            title={collapsed ? "Menüyü genişlet" : "Menüyü daralt"}
            className="hidden md:flex text-[var(--text-dim)] hover:text-[var(--primary)] shrink-0"
          >
            <ChevronRight size={15} className={`transition-transform ${collapsed ? "" : "rotate-180"}`} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto overflow-x-hidden scrollbar p-3">
          {navGroups.map((g) => {
            const visibleItems = g.items.filter((item) =>
              (!item.adminTierOnly || ADMIN_TIER_ROLES.has(user.role)) &&
              (!item.featureFlag || flagsByKey[item.featureFlag] !== false)
            );
            if (visibleItems.length === 0) return null;
            const isOpen = effectiveCollapsed ? true : openGroups[g.title] === true;
            const hasActive = g.items.some((it) => itemMatchesPath(it, location.pathname));
            return (
              <div key={g.title} className="mb-1">
                {!effectiveCollapsed && (
                  <button
                    type="button"
                    onClick={() => toggleGroup(g.title)}
                    data-testid={`navgroup-${g.title.toLowerCase().replace(/[^a-z0-9ğüşıöç]+/gi, "-")}`}
                    className={`w-full flex items-center gap-1.5 text-[10px] tracking-widest px-3 mb-1 mt-2 select-none transition-colors ${
                      hasActive && !isOpen ? "text-[var(--primary)]" : "text-[var(--text-dim)] hover:text-white"
                    }`}
                  >
                    <ChevronRight size={11} className={`transition-transform ${isOpen ? "rotate-90" : ""}`} />
                    <span className="flex-1 text-left truncate">{g.title}</span>
                  </button>
                )}
                {isOpen && visibleItems.map((item) => {
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
                             title={effectiveCollapsed ? item.label : undefined}
                             data-testid={`nav-${toPath.replace("/", "") || "home"}`}
                             className={({ isActive }) => {
                               const active = isActive && (!toQuery || window.location.search.includes(toQuery));
                               return `group flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${effectiveCollapsed ? "justify-center" : ""} ${
                                 active ? "bg-[var(--primary)]/10 text-[var(--primary)]" : "text-[var(--text-dim)] hover:bg-[var(--surface)] hover:text-white"
                               }`;
                             }}>
                      <item.icon size={15} className="shrink-0"/>
                      {!effectiveCollapsed && <span className="truncate">{item.label}</span>}
                    </NavLink>
                  );
                })}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-[var(--border)] p-3">
          <div className={`flex items-center gap-3 px-3 py-2 ${effectiveCollapsed ? "flex-col" : ""}`}>
            {/* SON HAL — ada tıklayınca Profil sayfası açılır */}
            <div
              className={`flex items-center gap-3 cursor-pointer rounded-lg -mx-1 px-1 py-0.5 hover:bg-[var(--surface)] transition-colors ${effectiveCollapsed ? "" : "flex-1 min-w-0"}`}
              role="button" tabIndex={0} title="Profilim"
              data-testid="profile-link"
              onClick={() => { nav("/profil"); setMobileOpen(false); }}
              onKeyDown={(e) => { if (e.key === "Enter") nav("/profil"); }}
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--primary)] to-[var(--primary-dark)] flex items-center justify-center text-white font-bold text-sm shrink-0">
                {(user.full_name || "?").charAt(0)}
              </div>
              {!effectiveCollapsed && (
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{user.full_name || "Kullanıcı"}</div>
                  <div className="text-[10px] text-[var(--text-dim)] uppercase tracking-wider">{user.role || ""}</div>
                </div>
              )}
            </div>
            <div className="flex items-center gap-3">
              {/* SON HAL — tema düğmesi (aydınlık varsayılan, tercih kalıcı) */}
              <button
                data-testid="theme-toggle"
                onClick={() => setTheme(getTheme() === "dark" ? "light" : "dark")}
                className="text-[var(--text-dim)] hover:text-[var(--primary)]"
                title={getTheme() === "dark" ? "Aydınlık temaya geç" : "Koyu temaya geç"}
              >
                {getTheme() === "dark" ? <Sun size={16}/> : <Moon size={16}/>}
              </button>
              <WorkspaceDrawer />
              <button data-testid="logout-button" onClick={logout} className="text-[var(--text-dim)] hover:text-[var(--danger)]"><LogOut size={16}/></button>
            </div>
          </div>
        </div>
      </aside>

      <main className={`flex-1 min-w-0 ${mainMarginClass} min-h-screen pt-14 md:pt-0 overflow-x-hidden transition-[margin] duration-200`}>
        <ErrorBoundary resetKey={location.pathname}><Outlet /></ErrorBoundary>
      </main>
      <AnnouncementPopup />
    </div>
  );
}
