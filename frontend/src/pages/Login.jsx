import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/api";
import { Wheat, Lock, Mail, Loader2, MessageCircleQuestion, Send, CheckCircle2, X, KeyRound } from "lucide-react";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [totpRequired, setTotpRequired] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  // İletişim formu (2026-07-11) — hesabı olmayan ziyaretçiler için: giriş
  // yapamayan biri, hesap oluşturana kadar kurumla iletişime geçebilsin.
  // Kimlik doğrulama GEREKTİRMEZ (/public/contact-request), Bize Ulaşın'a
  // (Case Management) "Hesap / Giriş Talebi" kategorisiyle düşer.
  const [showContact, setShowContact] = useState(false);
  const [contactForm, setContactForm] = useState({ full_name: "", phone: "", email: "", message: "" });
  const [contactError, setContactError] = useState("");
  const [contactLoading, setContactLoading] = useState(false);
  const [contactSent, setContactSent] = useState(false);

  async function submitContact(e) {
    e.preventDefault();
    setContactError("");
    setContactLoading(true);
    try {
      await api.post("/public/contact-request", contactForm);
      setContactSent(true);
      setContactForm({ full_name: "", phone: "", email: "", message: "" });
    } catch (err) {
      setContactError(err.response?.data?.detail || "Talep gönderilemedi, lütfen tekrar deneyin");
    } finally {
      setContactLoading(false);
    }
  }

  function toggleContact() {
    setShowContact((v) => !v);
    setContactSent(false);
    setContactError("");
  }

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
      const body = { email, password };
      if (totpRequired) body.totp_code = totpCode;
      const { data } = await api.post("/auth/login", body);
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
      // God Mode hesapları (totp_enabled=True) şifre doğrulandıktan sonra
      // backend'den "TOTP_REQUIRED" döner — bu, form'u yeniden göndermeden
      // sadece authenticator kodu alanını açar (e-posta/şifre yeniden
      // istenmez, ikisi de state'te zaten duruyor).
      if (err.response?.data?.detail === "TOTP_REQUIRED") {
        setTotpRequired(true);
        setError("");
      } else {
        setError(err.response?.data?.detail || "Giriş başarısız");
      }
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
                  disabled={totpRequired}
                />
              </div>
            </div>

            {totpRequired && (
              <div>
                <label className="text-xs text-[var(--text-dim)] mb-1.5 block">DOĞRULAMA KODU (AUTHENTICATOR)</label>
                <div className="relative">
                  <KeyRound size={16} className="absolute left-4 top-3.5 text-[var(--text-dim)]" />
                  <input
                    data-testid="login-totp-input"
                    className="input pl-11 tracking-[0.3em]"
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="123456"
                    inputMode="numeric"
                    autoFocus
                    required
                  />
                </div>
              </div>
            )}

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

          <div className="mt-6 text-center">
            <button
              type="button"
              data-testid="no-account-contact-toggle"
              onClick={toggleContact}
              className="text-xs text-[var(--text-dim)] hover:text-[var(--primary)] inline-flex items-center gap-1.5"
            >
              <MessageCircleQuestion size={14} />
              Giriş için kullanıcınız yok mu? Buradan talep oluşturabilirsiniz
            </button>
          </div>

          {showContact && (
            <div className="mt-4 card p-5 relative" data-testid="contact-request-panel">
              <button
                type="button"
                onClick={toggleContact}
                className="absolute top-3 right-3 text-[var(--text-dim)] hover:text-white"
                aria-label="Kapat"
              >
                <X size={16} />
              </button>

              {contactSent ? (
                <div className="text-center py-2" data-testid="contact-request-success">
                  <CheckCircle2 size={28} className="text-[var(--primary)] mx-auto mb-2" />
                  <p className="text-sm">Talebiniz alındı.</p>
                  <p className="text-xs text-[var(--text-dim)] mt-1">
                    Kurumunuzun yetkilisi en kısa sürede sizinle iletişime geçecektir.
                  </p>
                </div>
              ) : (
                <form onSubmit={submitContact} className="space-y-3">
                  <div>
                    <div className="text-[11px] text-[var(--primary)] tracking-widest mb-1">HESAP / GİRİŞ TALEBİ</div>
                    <p className="text-xs text-[var(--text-dim)]">
                      Kurumunuzda henüz bir kullanıcı hesabınız yoksa, aşağıdaki formla
                      talep oluşturun — yetkiliniz sizinle iletişime geçecektir.
                    </p>
                  </div>
                  <input
                    data-testid="contact-fullname-input"
                    className="input text-sm"
                    placeholder="Ad Soyad"
                    required
                    value={contactForm.full_name}
                    onChange={(e) => setContactForm((f) => ({ ...f, full_name: e.target.value }))}
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      data-testid="contact-phone-input"
                      className="input text-sm"
                      placeholder="Telefon"
                      value={contactForm.phone}
                      onChange={(e) => setContactForm((f) => ({ ...f, phone: e.target.value }))}
                    />
                    <input
                      data-testid="contact-email-input"
                      type="email"
                      className="input text-sm"
                      placeholder="E-posta"
                      value={contactForm.email}
                      onChange={(e) => setContactForm((f) => ({ ...f, email: e.target.value }))}
                    />
                  </div>
                  <textarea
                    data-testid="contact-message-input"
                    className="input text-sm min-h-[80px]"
                    placeholder="Talebinizi kısaca açıklayın (örn. hangi kurum/kooperatif, hangi rol)"
                    required
                    value={contactForm.message}
                    onChange={(e) => setContactForm((f) => ({ ...f, message: e.target.value }))}
                  />
                  <p className="text-[10px] text-[var(--text-dim)]">
                    Telefon veya e-postadan en az birini girmeniz gerekir.
                  </p>

                  {contactError && (
                    <div className="text-xs text-[var(--danger)] bg-red-500/10 border border-red-500/20 rounded-lg p-2.5">
                      {contactError}
                    </div>
                  )}

                  <button
                    data-testid="contact-submit-button"
                    type="submit"
                    disabled={contactLoading}
                    className="btn btn-primary w-full justify-center py-2.5 text-sm"
                  >
                    {contactLoading ? <><Loader2 size={14} className="animate-spin" /> Gönderiliyor…</> : <><Send size={14} /> Talep Gönder</>}
                  </button>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
