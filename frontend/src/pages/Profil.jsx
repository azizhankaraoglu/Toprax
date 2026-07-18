/**
 * PROFİLİM (SON HAL) — route /profil
 *
 * Kullanıcının KENDİ hesabı: bilgi görüntüleme, ad/telefon düzenleme,
 * şifre değiştirme ve tema tercihi. Backend: GET/PUT /me/profile +
 * PUT /me/password (users.py — izin gerektirmez, sadece oturum).
 * Sidebar footer'daki ad/avatar alanına tıklayınca açılır.
 */
import { useEffect, useState } from "react";
import api from "@/api";
import Breadcrumb from "@/components/Breadcrumb";
import { getTheme, setTheme } from "@/lib/theme";
import { UserCircle, KeyRound, Sun, Moon, Check } from "lucide-react";

const ROLE_LABELS = {
  super_admin: "Sistem Yöneticisi", kurum_yoneticisi: "Kurum Yöneticisi",
  il_yoneticisi: "İl Yöneticisi", fabrika_muduru: "Fabrika Müdürü",
  ilce_yoneticisi: "İlçe Yöneticisi", ziraat_muhendisi: "Ziraat Mühendisi",
  saha_personeli: "Saha Personeli", kantar_personeli: "Kantar Personeli",
  toprak_personeli: "Toprak Personeli", ciftci: "Çiftçi",
};

export default function Profil() {
  const [me, setMe] = useState(null);
  const [form, setForm] = useState({ full_name: "", phone: "" });
  const [profileMsg, setProfileMsg] = useState("");
  const [pw, setPw] = useState({ current_password: "", new_password: "", new_password2: "" });
  const [pwMsg, setPwMsg] = useState(null);        // {ok, text}
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/me/profile").then((r) => {
      setMe(r.data);
      setForm({ full_name: r.data.full_name || "", phone: r.data.phone || "" });
    });
  }, []);

  async function saveProfile(e) {
    e.preventDefault();
    setBusy(true); setProfileMsg("");
    try {
      const { data } = await api.put("/me/profile", form);
      setMe(data);
      // Sidebar'daki ad anında güncellensin diye localStorage'daki user da tazelenir
      try {
        const u = JSON.parse(localStorage.getItem("user") || "{}");
        localStorage.setItem("user", JSON.stringify({ ...u, full_name: data.full_name, phone: data.phone }));
      } catch {}
      setProfileMsg("Kaydedildi.");
    } catch (err) {
      setProfileMsg(err.response?.data?.detail || "Kaydedilemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function changePassword(e) {
    e.preventDefault();
    setPwMsg(null);
    if (pw.new_password !== pw.new_password2) {
      setPwMsg({ ok: false, text: "Yeni şifreler birbirini tutmuyor." });
      return;
    }
    setBusy(true);
    try {
      await api.put("/me/password", {
        current_password: pw.current_password, new_password: pw.new_password,
      });
      setPw({ current_password: "", new_password: "", new_password2: "" });
      setPwMsg({ ok: true, text: "Şifreniz değiştirildi." });
    } catch (err) {
      setPwMsg({ ok: false, text: err.response?.data?.detail || "Şifre değiştirilemedi." });
    } finally {
      setBusy(false);
    }
  }

  if (!me) return <div className="p-10 text-[var(--text-dim)]">Yükleniyor…</div>;

  const theme = getTheme();

  return (
    <div className="p-8 max-w-[860px]" data-testid="profil-page">
      <Breadcrumb items={[{ label: "Profilim" }]} />
      <header className="mb-6 flex items-center gap-4">
        <div className="w-14 h-14 rounded-full bg-gradient-to-br from-[var(--primary)] to-[var(--primary-dark)] flex items-center justify-center text-white font-bold text-xl">
          {(me.full_name || "?").charAt(0)}
        </div>
        <div>
          <h1 className="font-display text-3xl">{me.full_name}</h1>
          <p className="text-[var(--text-dim)] text-sm mt-0.5">
            {me.email} · <span className="badge badge-neutral">{ROLE_LABELS[me.role] || me.role}</span>
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Bilgiler */}
        <form onSubmit={saveProfile} className="card p-5" data-testid="profile-form">
          <h3 className="font-display text-lg mb-1 flex items-center gap-2"><UserCircle size={18}/> Bilgilerim</h3>
          <p className="text-xs text-[var(--text-dim)] mb-4">
            E-posta ve rol buradan değiştirilemez — rol değişikliği için sistem yöneticinize başvurun.
          </p>
          <label className="text-xs text-[var(--text-dim)] block mb-1">Ad Soyad</label>
          <input className="input mb-3" value={form.full_name} required
                 onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                 data-testid="profile-fullname" />
          <label className="text-xs text-[var(--text-dim)] block mb-1">Telefon</label>
          <input className="input mb-3" value={form.phone}
                 onChange={(e) => setForm({ ...form, phone: e.target.value })}
                 placeholder="05xx xxx xx xx" data-testid="profile-phone" />
          <label className="text-xs text-[var(--text-dim)] block mb-1">E-posta</label>
          <input className="input mb-4 opacity-60" value={me.email} disabled />
          <div className="flex items-center gap-3">
            <button className="btn btn-primary" disabled={busy} data-testid="profile-save">Kaydet</button>
            {profileMsg && <span className="text-sm text-[var(--primary)]">{profileMsg}</span>}
          </div>
        </form>

        {/* Şifre */}
        <form onSubmit={changePassword} className="card p-5" data-testid="password-form">
          <h3 className="font-display text-lg mb-4 flex items-center gap-2"><KeyRound size={18}/> Şifre Değiştir</h3>
          <label className="text-xs text-[var(--text-dim)] block mb-1">Mevcut şifre</label>
          <input className="input mb-3" type="password" required value={pw.current_password}
                 onChange={(e) => setPw({ ...pw, current_password: e.target.value })}
                 data-testid="pw-current" />
          <label className="text-xs text-[var(--text-dim)] block mb-1">Yeni şifre (en az 8 karakter)</label>
          <input className="input mb-3" type="password" required minLength={8} value={pw.new_password}
                 onChange={(e) => setPw({ ...pw, new_password: e.target.value })}
                 data-testid="pw-new" />
          <label className="text-xs text-[var(--text-dim)] block mb-1">Yeni şifre (tekrar)</label>
          <input className="input mb-4" type="password" required minLength={8} value={pw.new_password2}
                 onChange={(e) => setPw({ ...pw, new_password2: e.target.value })}
                 data-testid="pw-new2" />
          <div className="flex items-center gap-3">
            <button className="btn btn-primary" disabled={busy} data-testid="pw-save">Şifreyi Değiştir</button>
            {pwMsg && (
              <span className={`text-sm ${pwMsg.ok ? "text-[var(--success)]" : "text-[var(--danger)]"}`}
                    data-testid="pw-msg">{pwMsg.text}</span>
            )}
          </div>
        </form>
      </div>

      {/* Tema tercihi */}
      <div className="card p-5 mt-4" data-testid="theme-panel">
        <h3 className="font-display text-lg mb-1">Görünüm</h3>
        <p className="text-xs text-[var(--text-dim)] mb-4">
          Tercihiniz bu tarayıcıda saklanır. Varsayılan: Aydınlık.
        </p>
        <div className="flex gap-3">
          <button
            className={`btn ${theme === "light" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => theme !== "light" && setTheme("light")}
            data-testid="theme-light"
          >
            <Sun size={15}/> Aydınlık {theme === "light" && <Check size={14}/>}
          </button>
          <button
            className={`btn ${theme === "dark" ? "btn-primary" : "btn-ghost"}`}
            onClick={() => theme !== "dark" && setTheme("dark")}
            data-testid="theme-dark"
          >
            <Moon size={15}/> Koyu {theme === "dark" && <Check size={14}/>}
          </button>
        </div>
      </div>
    </div>
  );
}
