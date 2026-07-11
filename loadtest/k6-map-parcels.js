// k6-map-parcels.js -- PR-14: Yuk Testi (Harita / Parsel Listesi)
// Kullanim: BASE_URL=... TOKEN=... k6 run loadtest/k6-map-parcels.js
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8001";
const TOKEN = __ENV.TOKEN || "";

export const options = {
  stages: [
    { duration: "30s", target: 20 },
    { duration: "1m", target: 100 },   // harita ekrani genelde en yogun kullanilan ekran
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<1200"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const headers = { Authorization: `Bearer ${TOKEN}` };
  const res = http.get(`${BASE_URL}/api/parcels?skip=0&limit=100`, { headers });
  check(res, { "status 200": (r) => r.status === 200 });
  sleep(1);
}
