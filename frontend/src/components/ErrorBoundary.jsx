/**
 * ErrorBoundary — bir sayfa/bileşen render sırasında hata fırlatırsa TÜM
 * uygulamanın çökmesini (React'in ağacı söküp "siyah ekran" bırakmasını)
 * ÖNLER. Bunun yerine okunur bir hata kartı + teknik detay + "Yenile"
 * gösterir. `resetKey` (genelde route pathname) değişince hata temizlenir,
 * böylece kullanıcı sol menüden başka bir ekrana geçince otomatik toparlanır
 * (tam sayfa yenileme gerekmez).
 *
 * NOT: React'te error boundary SADECE class component olabilir
 * (getDerivedStateFromError / componentDidCatch hook karşılığı yok).
 */
import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, stack: "" };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ stack: info?.componentStack || "" });
    // Gerçek hatayı konsola tam stack ile bas — asıl bug'ı teşhis için.
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary] Sayfa render hatası:", error, info?.componentStack);
  }

  componentDidUpdate(prevProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null, stack: "" });
    }
  }

  render() {
    if (this.state.error) {
      const msg = this.state.error?.message || String(this.state.error);
      return (
        <div className="p-6 max-w-3xl mx-auto">
          <div className="card p-6" style={{ border: "1px solid rgba(239,68,68,0.35)" }}>
            <div className="flex items-center gap-2 mb-3">
              <span style={{ fontSize: "1.5rem" }}>⚠️</span>
              <h2 className="font-display text-xl">Bu ekran yüklenirken bir hata oluştu</h2>
            </div>
            <p className="text-sm text-[var(--text-dim)] mb-4">
              Sayfa açılırken beklenmeyen bir hata oluştu ve durduruldu (uygulamanın
              geri kalanı çalışmaya devam ediyor). Sol menüden başka bir ekrana
              geçebilir veya sayfayı yenileyebilirsiniz. Aşağıdaki teknik detay
              geliştiriciye iletilebilir.
            </p>
            <pre
              className="text-xs p-3 rounded overflow-auto"
              style={{
                background: "var(--surface-2, rgba(0,0,0,0.25))",
                color: "#fca5a5",
                maxHeight: "16rem",
                whiteSpace: "pre-wrap",
              }}
            >
{msg}
{this.state.stack}
            </pre>
            <div className="flex gap-2 mt-4">
              <button className="btn btn-primary" onClick={() => window.location.reload()}>
                Sayfayı Yenile
              </button>
              <button className="btn btn-ghost" onClick={() => { window.location.href = "/"; }}>
                Ana Sayfa
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
