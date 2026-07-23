import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";
import { applyTheme, applyAccent } from "@/lib/theme";

// SON HAL — tema render'dan ÖNCE uygulanır (koyu-flaş önlenir).
// Varsayılan AYDINLIK; tercih localStorage("toprax_theme")'de.
applyTheme();
// SON HAL #10 — kullanıcının seçtiği renk bloğu da render'dan önce
// uygulanır (localStorage("toprax_accent") — Login.jsx sunucudaki
// profil değerini bu önbelleğe senkronlar, bkz. theme.js docstring'i).
applyAccent();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);

// IT-35 — PWA service worker (app-shell cache, bkz. public/sw.js docstring'i).
// Dev VE prod'da kasıtlı olarak kayıt edilir (test edilebilirlik için).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
