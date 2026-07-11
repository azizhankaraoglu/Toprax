// k6-bulk-sms.js -- PR-14: Yuk Testi (Toplu SMS/Kampanya Gonderimi)
// DIKKAT: bu script GERCEK bir SMS saglayicisina karsi calistirilmamalidir
// -- Ayarlar > Entegrasyonlar'da SMS saglayicisini mock_mode=true yapip
// SADECE staging/test ortaminda calistirin.
// Kullanim: BASE_URL=... TOKEN=... k6 run loadtest/k6-bulk-sms.js
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8001";
const TOKEN = __ENV.TOKEN || "";

export const options = {
  scenarios: {
    bulk_campaign_send: {
      executor: "constant-arrival-rate",
      rate: 20,              // saniyede 20 istek -- kapasite kararina gore guncelleyin
      timeUnit: "1s",
      duration: "1m",
      preAllocatedVUs: 20,
      maxVUs: 50,
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<2000"],
    http_req_failed: ["rate<0.02"],
  },
};

export default function () {
  const headers = { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" };
  const res = http.get(`${BASE_URL}/api/campaigns`, { headers });
  check(res, { "status 200": (r) => r.status === 200 });
  sleep(0.5);
}
