import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { Wheat, Lock, Mail, Loader2 } from "lucide-react";

export default function Login() {
  const [email, setEmail] = useState("admin@turkseker.com.tr");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  useEffect(() => {
    if (localStorage.getItem("token")) {
      const user = JSON.parse(localStorage.getItem("user") || "{}");
      if (user.role === "platform_admin") nav("/platform");
      else nav(user.role === "ciftci" ? "/ciftci" : "/");
    }
  }, [nav]);

  async function submit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { data } = await api.post("/auth/login", { email, password });
      localStorage.setItem("token", data.token);
      localStorage.setItem("refresh_token", data.refresh_token || "");
      localStorage.setItem("user", JSON.stringify(data.user));
      // Role'e göre doğru panele yönlendir
      if (data.user.role === "platform_admin") {
        nav("/platform");
      } else if (data.user.role === "ciftci") {
        nav("/ciftci");
      } else {
        nav("/");
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Giriş başarısız");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-stretch bg-[var(--bg)] grain relative overflow-hidden">
      {/* Left brand panel */}
      <div className="hidden md:flex md:w-1/2 relative bg-gradient-to-br from-[#0b1f15] via-[#0a1a13] to-[#0a0f0d] p-12 flex-col justify-between">
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[var(--primary)] flex items-center justify-center">
              <Wheat size={22} className="text-[#052e16]" />
            </div>
            <div>
              <div className="font-display text-2xl text-white">Tarım Eko</div>
              <div className="text-xs text-[var(--text-dim)] tracking-widest">KOOPERATİF EDİSYONU</div>
            </div>
          </div>
        </div>

        <div className="relative z-10">
          <h1 className="font-display text-5xl leading-[1.05] text-white mb-6">
            Tarladan<br/>
            yönetim<br/>
            <span className="text-[var(--primary)]">masasına.</span>
          </h1>
          <p className="text-[var(--text-dim)] max-w-md text-[15px] leading-relaxed">
            100.000+ sözleşmeli üreticinizi, parsellerinizi, hasatınızı tek bir platformda yönetin.
            Kendi sunucunuzda. Tam veri sahipliği.
          </p>
        </div>

        <div className="relative z-10 flex gap-8 text-xs text-[var(--text-dim)]">
          <div><div className="text-[var(--primary)] font-display text-2xl">17</div>Modül</div>
          <div><div className="text-[var(--primary)] font-display text-2xl">On-Premise</div>Dağıtım</div>
          <div><div className="text-[var(--primary)] font-display text-2xl">KVKK</div>Uyumlu</div>
        </div>

        <div className="absolute -bottom-20 -right-20 w-96 h-96 rounded-full bg-[var(--primary)]/10 blur-3xl" />
      </div>

      {/* Right login form */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-sm fade-in">
          <div className="md:hidden mb-10 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[var(--primary)] flex items-center justify-center">
              <Wheat size={22} className="text-[#052e16]" />
            </div>
            <div className="font-display text-xl">Tarım Eko</div>
          </div>

          <div className="mb-8">
            <div className="text-[11px] text-[var(--primary)] tracking-widest mb-2">GİRİŞ</div>
            <h2 className="font-display text-3xl">Hoş geldiniz</h2>
            <p className="text-sm text-[var(--text-dim)] mt-2">Kooperatif yönetim panelinize erişin</p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-xs text-[var(--text-dim)] mb-1.5 block">E-POSTA</label>
              <div className="relative">
                <Mail size={16} className="absolute left-4 top-3.5 text-[var(--text-dim)]" />
                <input
                  data-testid="login-email-input"
                  className="input pl-11"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="ornek@kooperatif.com"
                  required
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-[var(--text-dim)] mb-1.5 block">ŞİFRE</label>
              <div className="relative">
                <Lock size={16} className="absolute left-4 top-3.5 text-[var(--text-dim)]" />
                <input
                  data-testid="login-password-input"
                  type="password"
                  className="input pl-11"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            </div>

            {error && <div className="text-sm text-[var(--danger)] bg-red-500/10 border border-red-500/20 rounded-lg p-3">{error}</div>}

            <button
              data-testid="login-submit-button"
              type="submit"
              disabled={loading}
              className="btn btn-primary w-full justify-center py-3.5 mt-2"
            >
              {loading ? <><Loader2 size={16} className="animate-spin" /> Giriş yapılıyor…</> : "Giriş yap"}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-[var(--border)] text-xs text-[var(--text-dim)] space-y-1">
            <div className="text-[10px] tracking-widest mb-2">DEMO HESAPLAR</div>
            <div>admin@turkseker.com.tr / admin123 <span className="text-[var(--primary)]">— Süper Admin</span></div>
            <div>ahmet.yilmaz@turkseker.com.tr / ahmet123 <span className="text-[var(--text-dim)]">— Fabrika Müdürü</span></div>
            <div>mehmet.demir@turkseker.com.tr / mehmet123 <span className="text-[var(--text-dim)]">— Ziraat Müh.</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}
