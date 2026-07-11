// k6-query-engine.js -- PR-14: Yuk Testi (Query Engine)
//
// Kurulum: https://k6.io/docs/get-started/installation/
// Kullanim:
//   BASE_URL=http://localhost:8001 TOKEN=<gecerli_jwt> k6 run loadtest/k6-query-engine.js
//
// Hedef eszamanli kullanici sayisi ve kabul edilebilir p95 esigi bir
// kapasite/is karari oldugu icin (bkz. ROADMAP-URUNLESTIRME.md PR-14
// "Sizin Yapmanız Gerekir") asagidaki `stages` ve `thresholds` degerleri
// MAKUL BIR BASLANGIC varsayimidir -- gercek hedefe gore guncelleyin.
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8001";
const TOKEN = __ENV.TOKEN || "";

export const options = {
  stages: [
    { duration: "30s", target: 10 },   // isinma
    { duration: "1m", target: 50 },    // hedef yuk
    { duration: "30s", target: 0 },    // sogutma
  ],
  thresholds: {
    http_req_duration: ["p(95)<800"],  // p95 < 800ms -- ORNEK esik, kapasite kararina gore guncelleyin
    http_req_failed: ["rate<0.01"],    // %1'den az hata
  },
};

export default function () {
  const headers = { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" };

  // Çiftçi listesi sorgusu (Query Engine tek okuma yolu, IT-08)
  const res = http.post(
    `${BASE_URL}/api/query/farmers`,
    JSON.stringify({ page: 1, page_size: 25, sort_by: "created_at", sort_dir: "desc" }),
    { headers }
  );
  check(res, {
    "status 200": (r) => r.status === 200,
    "yanit hizli (<1s)": (r) => r.timings.duration < 1000,
  });

  sleep(1);
}
