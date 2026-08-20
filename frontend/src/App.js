import { BrowserRouter, Routes, Route, Navigate, Outlet } from "react-router-dom";
import "@/App.css";
import ErrorBoundary from "@/components/ErrorBoundary";
import Login from "@/pages/Login";
import SetupWizard from "@/pages/SetupWizard";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Farmers from "@/pages/Farmers";
import FarmerDetail from "@/pages/FarmerDetail";
import Parcels from "@/pages/Parcels";
import ParcelDetail from "@/pages/ParcelDetail";
import HaritaPaneli from "@/pages/HaritaPaneli";
import Vra from "@/pages/Vra";
import DemoScenario from "@/pages/DemoScenario";
import RemoteSensing from "@/pages/RemoteSensing";
import ProductionCycleDetail from "@/pages/ProductionCycleDetail";
import Sulama from "@/pages/Sulama";
import Operasyon from "@/pages/Operasyon";
import Verimlilik from "@/pages/Verimlilik";
import Toprak from "@/pages/Toprak";
import FarmerHome from "@/pages/FarmerHome";
import PlatformAdmin from "@/pages/PlatformAdmin";
import { KullaniciYonetimi, OzelRoller } from "@/pages/UserManagement";
import { Sozlesmeler, Lojistik, Karne, Bildirimler } from "@/pages/Other";
import ContractDetail from "@/pages/ContractDetail";
import EkimKaydi from "@/pages/EkimKaydi";
import SezonKararTakvimi from "@/pages/SezonKararTakvimi";
import AdminAreaDetail from "@/pages/AdminAreaDetail";
import ToprakBiyolojisi from "@/pages/ToprakBiyolojisi";
import HasatLojistigi from "@/pages/HasatLojistigi";
import KarneDetail from "@/pages/KarneDetail";
import Profil from "@/pages/Profil";
import { FormListesi, FormBuilder, FormDoldur, FormDashboard } from "@/pages/Forms";
import { FormYonetimiHub } from "@/pages/FormYonetimi";
import AdminAreaManagement from "@/pages/AdminAreaManagement";
import UfydDashboard from "@/pages/UfydDashboard";
import SahaOperasyonlari from "@/pages/SahaOperasyonlari";
import AutomationRules from "@/pages/AutomationRules";
import NotificationDetail from "@/pages/NotificationDetail";
import { SablonYonetimi } from "@/pages/TemplateManagement";
import AnnouncementManagement from "@/pages/AnnouncementManagement";
import CampaignManagement from "@/pages/CampaignManagement";
import CommunicationPolicies from "@/pages/CommunicationPolicies";
import EgitimYonetimi from "@/pages/EgitimYonetimi";
import IntegrationHub from "@/pages/IntegrationHub";
import DeveloperPortal from "@/pages/DeveloperPortal";
import PlatformCore from "@/pages/PlatformCore";
import AiKnowledgeLibrary from "@/pages/AiKnowledgeLibrary";
import AiGovernance from "@/pages/AiGovernance";
import Sustainability from "@/pages/Sustainability";
import ParcelCarbonDetail from "@/pages/ParcelCarbonDetail";
import CropDetection from "@/pages/CropDetection";
import { ExperienceProfileYonetimi } from "@/pages/ExperienceProfiles";
import MobilDashboard from "@/pages/MobilDashboard";
import OrganizationChart from "@/pages/OrganizationChart";
import PendingApprovals from "@/pages/PendingApprovals";
import CaseManagement from "@/pages/CaseManagement";
import ReportBuilder from "@/pages/ReportBuilder";
import PublicReportViewer from "@/pages/PublicReportViewer";
import HaritaStudyosu from "@/pages/HaritaStudyosu";
import PublicMapViewer from "@/pages/PublicMapViewer";
import {
  AyarlarEntegrasyon, HastalikTespiti, EFaturalar, Irsaliyeler,
  KantarKayitlari, AuditLog, UyduGorunutu, SahaPWA, AICopilot
} from "@/pages/Extras";

function PrivateRoute({ children, adminOnly = false }) {
  const token = localStorage.getItem("token");
  if (!token) return <Navigate to="/login" />;
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  if (adminOnly && user.role === "ciftci") return <Navigate to="/ciftci" />;
  return children || <Outlet />;
}

function PlatformRoute({ children }) {
  const token = localStorage.getItem("token");
  if (!token) return <Navigate to="/login" />;
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  // platform_admin normal kooperatif ekranlarına girmez, sadece /platform kullanır.
  if (user.role !== "platform_admin") return <Navigate to="/login" />;
  return children;
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
       <ErrorBoundary>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/kurulum" element={<SetupWizard />} />
          <Route path="/platform" element={<PlatformRoute><PlatformAdmin /></PlatformRoute>} />
          <Route path="/form/:token" element={<FormDoldur isPublic={true} />} />
          <Route path="/rapor/:token" element={<PublicReportViewer />} />
          <Route path="/harita/:token" element={<PublicMapViewer />} />
          <Route path="/ciftci" element={<PrivateRoute><FarmerHome /></PrivateRoute>} />
          <Route path="/m" element={<PrivateRoute><MobilDashboard /></PrivateRoute>} />
          <Route path="/ciftci/form/:id" element={<PrivateRoute><FormDoldur isPublic={false} /></PrivateRoute>} />
          <Route element={<PrivateRoute adminOnly={true}><Layout /></PrivateRoute>}>
            <Route path="/" element={<Dashboard />} />
            {/* /arama emekli edildi — arama Dashboard'a gömüldü, eski linkler kırılmasın */}
            <Route path="/arama" element={<Navigate to="/" replace />} />
            <Route path="/ciftciler" element={<Farmers />} />
            <Route path="/ciftciler/:id" element={<FarmerDetail />} />
            <Route path="/parseller" element={<Parcels />} />
            <Route path="/parseller/:id" element={<ParcelDetail />} />
            <Route path="/harita-paneli" element={<HaritaPaneli />} />
            <Route path="/uretim-sezonlari/:id" element={<ProductionCycleDetail />} />
            <Route path="/sozlesmeler" element={<Sozlesmeler />} />
            <Route path="/sozlesmeler/:id" element={<ContractDetail />} />
            <Route path="/ekim" element={<EkimKaydi />} />
            {/* Karar destek katmanı (2026-08-19) */}
            <Route path="/idari-alanlar/:id" element={<AdminAreaDetail />} />
            <Route path="/sezon-karar-takvimi" element={<SezonKararTakvimi />} />
            <Route path="/toprak-biyolojisi" element={<ToprakBiyolojisi />} />
            <Route path="/hasat-lojistigi" element={<HasatLojistigi />} />
            <Route path="/toprak" element={<Toprak />} />
            <Route path="/sulama" element={<Sulama />} />
            <Route path="/operasyon" element={<Operasyon />} />
            <Route path="/verimlilik" element={<Verimlilik />} />
            <Route path="/lojistik" element={<Lojistik />} />
            <Route path="/karne" element={<Karne />} />
            <Route path="/karne/:farmerId" element={<KarneDetail />} />
            <Route path="/bildirimler" element={<Bildirimler />} />
            <Route path="/bildirimler/:id" element={<NotificationDetail />} />
            <Route path="/profil" element={<Profil />} />
            <Route path="/uydu" element={<UyduGorunutu />} />
            <Route path="/uzaktan-algilama" element={<RemoteSensing />} />
            <Route path="/vra" element={<Vra />} />
            <Route path="/senaryo-oynatici" element={<DemoScenario />} />
            <Route path="/copilot" element={<AICopilot />} />
            <Route path="/hastalik" element={<HastalikTespiti />} />
            <Route path="/saha" element={<SahaPWA />} />
            <Route path="/e-fatura" element={<EFaturalar />} />
            <Route path="/irsaliye" element={<Irsaliyeler />} />
            <Route path="/kantar" element={<KantarKayitlari />} />
            <Route path="/audit" element={<AuditLog />} />
            <Route path="/ayarlar" element={<AyarlarEntegrasyon />} />
            <Route path="/kullanicilar" element={<KullaniciYonetimi />} />
            <Route path="/ozel-roller" element={<OzelRoller />} />
            {/* SON HAL #6 — Form Yönetimi / Lookup Yönetimi / Destek Kataloğu
                tek sayfada (sekmeli) birleştirildi; eski route'lar geriye
                dönük uyumluluk için yönlendirilir (/arama -> / deseniyle AYNI). */}
            <Route path="/alan-tanimlari" element={<FormYonetimiHub />} />
            <Route path="/lookup-yonetimi" element={<Navigate to="/alan-tanimlari" replace />} />
            <Route path="/idari-alanlar" element={<AdminAreaManagement />} />
            <Route path="/destek-katalogu" element={<Navigate to="/alan-tanimlari" replace />} />
            <Route path="/sablon-yonetimi" element={<SablonYonetimi />} />
            <Route path="/duyuru-yonetimi" element={<AnnouncementManagement />} />
            <Route path="/kampanyalar" element={<CampaignManagement />} />
            <Route path="/iletisim-politikalari" element={<CommunicationPolicies />} />
            <Route path="/organizasyon-hiyerarsisi" element={<OrganizationChart />} />
            <Route path="/onay-bekleyenlerim" element={<PendingApprovals />} />
            <Route path="/bize-ulasin" element={<CaseManagement />} />
            <Route path="/rapor-olusturucu" element={<ReportBuilder />} />
            <Route path="/harita-studyosu" element={<HaritaStudyosu />} />
            <Route path="/egitim-yonetimi" element={<EgitimYonetimi />} />
            <Route path="/integration-hub" element={<IntegrationHub />} />
            <Route path="/gelistirici-portali" element={<DeveloperPortal />} />
            <Route path="/platform-core" element={<PlatformCore />} />
            <Route path="/ai-bilgi-kutuphanesi" element={<AiKnowledgeLibrary />} />
            <Route path="/ai-yonetimi" element={<AiGovernance />} />
            <Route path="/karbon-ayak-izi" element={<Sustainability />} />
            <Route path="/parseller/:id/karbon" element={<ParcelCarbonDetail />} />
            <Route path="/urun-tanima" element={<CropDetection />} />
            <Route path="/experience-profiles" element={<ExperienceProfileYonetimi />} />
            <Route path="/ufyd-dashboard" element={<UfydDashboard />} />
            <Route path="/saha-operasyonlari" element={<SahaOperasyonlari />} />
            <Route path="/otomasyon-kurallari" element={<AutomationRules />} />
            {/* Denetim düzeltmesi (2026-07-24) — Ekim Karar Motoru artık
                /ekim'in "Karar Motoru" sekmesi (/arama -> / deseniyle AYNI). */}
            <Route path="/ekim-planlama" element={<Navigate to="/ekim?view=karar-motoru" replace />} />
            <Route path="/formlar" element={<FormListesi />} />
            <Route path="/formlar/yeni" element={<FormBuilder />} />
            <Route path="/formlar/:id/duzenle" element={<FormBuilder />} />
            <Route path="/formlar/:id/dashboard" element={<FormDashboard />} />
            <Route path="/formlar/:id/doldur" element={<FormDoldur isPublic={false} />} />
          </Route>
        </Routes>
       </ErrorBoundary>
      </BrowserRouter>
    </div>
  );
}

export default App;
