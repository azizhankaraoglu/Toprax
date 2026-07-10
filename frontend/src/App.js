import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "@/App.css";
import Login from "@/pages/Login";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Farmers from "@/pages/Farmers";
import FarmerDetail from "@/pages/FarmerDetail";
import Parcels from "@/pages/Parcels";
import ParcelDetail from "@/pages/ParcelDetail";
import Sulama from "@/pages/Sulama";
import Operasyon from "@/pages/Operasyon";
import Verimlilik from "@/pages/Verimlilik";
import Toprak from "@/pages/Toprak";
import FarmerHome from "@/pages/FarmerHome";
import PlatformAdmin from "@/pages/PlatformAdmin";
import { KullaniciYonetimi, OzelRoller } from "@/pages/UserManagement";
import { Sozlesmeler, Ekim, Lojistik, Karne, Bildirimler } from "@/pages/Other";
import { FormListesi, FormBuilder, FormDoldur, FormDashboard } from "@/pages/Forms";
import {
  AyarlarEntegrasyon, HastalikTespiti, EFaturalar, Irsaliyeler,
  KantarKayitlari, AuditLog, UyduGorunutu, SahaPWA, AICopilot
} from "@/pages/Extras";

function PrivateRoute({ children, adminOnly = false }) {
  const token = localStorage.getItem("token");
  if (!token) return <Navigate to="/login" />;
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  if (adminOnly && user.role === "ciftci") return <Navigate to="/ciftci" />;
  return children;
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
          <Route path="/platform" element={<PlatformRoute><PlatformAdmin /></PlatformRoute>} />
          <Route path="/form/:token" element={<FormDoldur isPublic={true} />} />
          <Route path="/ciftci" element={<PrivateRoute><FarmerHome /></PrivateRoute>} />
          <Route path="/ciftci/form/:id" element={<PrivateRoute><FormDoldur isPublic={false} /></PrivateRoute>} />
          <Route element={<PrivateRoute adminOnly={true}><Layout /></PrivateRoute>}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/ciftciler" element={<Farmers />} />
            <Route path="/ciftciler/:id" element={<FarmerDetail />} />
            <Route path="/parseller" element={<Parcels />} />
            <Route path="/parseller/:id" element={<ParcelDetail />} />
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
