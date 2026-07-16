import { BrowserRouter, Routes, Route, Navigate, Outlet } from "react-router-dom";
import "@/App.css";
import Login from "@/pages/Login";
import SetupWizard from "@/pages/SetupWizard";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import GlobalSearch from "@/pages/GlobalSearch";
import Farmers from "@/pages/Farmers";
import FarmerDetail from "@/pages/FarmerDetail";
import Parcels from "@/pages/Parcels";
import ParcelDetail from "@/pages/ParcelDetail";
import HaritaPaneli from "@/pages/HaritaPaneli";
import RemoteSensing from "@/pages/RemoteSensing";
import ProductionCycleDetail from "@/pages/ProductionCycleDetail";
import Sulama from "@/pages/Sulama";
import Operasyon from "@/pages/Operasyon";
import Verimlilik from "@/pages/Verimlilik";
import Toprak from "@/pages/Toprak";
import FarmerHome from "@/pages/FarmerHome";
import PlatformAdmin from "@/pages/PlatformAdmin";
import { KullaniciYonetimi, OzelRoller } from "@/pages/UserManagement";
import { Sozlesmeler, Ekim, Lojistik, Karne, Bildirimler } from "@/pages/Other";
import { FormListesi, FormBuilder, FormDoldur, FormDashboard } from "@/pages/Forms";
import { AlanTanimlari, LookupYonetimi } from "@/pages/FormYonetimi";
import AdminAreaManagement from "@/pages/AdminAreaManagement";
import { DestekKatalogu } from "@/pages/SupportCatalog";
import UfydDashboard from "@/pages/UfydDashboard";
import SahaOperasyonlari from "@/pages/SahaOperasyonlari";
import AutomationRules from "@/pages/AutomationRules";
import { SablonYonetimi } from "@/pages/TemplateManagement";
import AnnouncementManagement from "@/pages/AnnouncementManagement";
import CampaignManagement from "@/pages/CampaignManagement";
import CommunicationPolicies from "@/pages/CommunicationPolicies";
import EgitimYonetimi from "@/pages/EgitimYonetimi";
import IntegrationHub from "@/pages/IntegrationHub";
import DeveloperPortal from "@/pages/DeveloperPortal";
import PlatformCore from "@/pages/PlatformCore";
import AiKnowledgeLibrary from "@/pages/AiKnowledgeLibrary";
import { ExperienceProfileYonetimi } from "@/pages/ExperienceProfiles";
import MobilDashboard from "@/pages/MobilDashboard";
import OrganizationChart from "@/pages/OrganizationChart";
import PendingApprovals from "@/pages/PendingApprovals";
import CaseManagement from "@/pages/CaseManagement";
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
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/kurulum" element={<SetupWizard />} />
          <Route path="/platform" element={<PlatformRoute><PlatformAdmin /></PlatformRoute>} />
          <Route path="/form/:token" element={<FormDoldur isPublic={true} />} />
          <Route path="/ciftci" element={<PrivateRoute><FarmerHome /></PrivateRoute>} />
          <Route path="/m" element={<PrivateRoute><MobilDashboard /></PrivateRoute>} />
          <Route path="/ciftci/form/:id" element={<PrivateRoute><FormDoldur isPublic={false} /></PrivateRoute>} />
          <Route element={<PrivateRoute adminOnly={true}><Layout /></PrivateRoute>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/arama" element={<GlobalSearch />} />
            <Route path="/ciftciler" element={<Farmers />} />
            <Route path="/ciftciler/:id" element={<FarmerDetail />} />
            <Route path="/parseller" element={<Parcels />} />
            <Route path="/parseller/:id" element={<ParcelDetail />} />
            <Route path="/harita-paneli" element={<HaritaPaneli />} />
            <Route path="/uretim-sezonlari/:id" element={<ProductionCycleDetail />} />
            <Route path="/sozlesmeler" element={<Sozlesmeler />} />
            <Route path="/ekim" element={<Ekim />} />
            <Route path="/toprak" element={<Toprak />} />
            <Route path="/sulama" element={<Sulama />} />
            <Route path="/operasyon" element={<Operasyon />} />
            <Route path="/verimlilik" element={<Verimlilik />} />
            <Route path="/lojistik" element={<Lojistik />} />
            <Route path="/karne" element={<Karne />} />
            <Route path="/bildirimler" element={<Bildirimler />} />
            <Route path="/uydu" element={<UyduGorunutu />} />
            <Route path="/uzaktan-algilama" element={<RemoteSensing />} />
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
            <Route path="/alan-tanimlari" element={<AlanTanimlari />} />
            <Route path="/lookup-yonetimi" element={<LookupYonetimi />} />
            <Route path="/idari-alanlar" element={<AdminAreaManagement />} />
            <Route path="/destek-katalogu" element={<DestekKatalogu />} />
            <Route path="/sablon-yonetimi" element={<SablonYonetimi />} />
            <Route path="/duyuru-yonetimi" element={<AnnouncementManagement />} />
            <Route path="/kampanyalar" element={<CampaignManagement />} />
            <Route path="/iletisim-politikalari" element={<CommunicationPolicies />} />
            <Route path="/organizasyon-hiyerarsisi" element={<OrganizationChart />} />
            <Route path="/onay-bekleyenlerim" element={<PendingApprovals />} />
            <Route path="/bize-ulasin" element={<CaseManagement />} />
            <Route path="/egitim-yonetimi" element={<EgitimYonetimi />} />
            <Route path="/integration-hub" element={<IntegrationHub />} />
            <Route path="/gelistirici-portali" element={<DeveloperPortal />} />
            <Route path="/platform-core" element={<PlatformCore />} />
            <Route path="/ai-bilgi-kutuphanesi" element={<AiKnowledgeLibrary />} />
            <Route path="/experience-profiles" element={<ExperienceProfileYonetimi />} />
            <Route path="/ufyd-dashboard" element={<UfydDashboard />} />
            <Route path="/saha-operasyonlari" element={<SahaOperasyonlari />} />
            <Route path="/otomasyon-kurallari" element={<AutomationRules />} />
            <Route path="/formlar" element={<FormListesi />} />
            <Route path="/formlar/yeni" element={<FormBuilder />} />
            <Route path="/formlar/:id/duzenle" element={<FormBuilder />} />
            <Route path="/formlar/:id/dashboard" element={<FormDashboard />} />
            <Route path="/formlar/:id/doldur" element={<FormDoldur isPublic={false} />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
