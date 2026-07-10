import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API });

client.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

let refreshing = null;

function logoutToLogin() {
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
  if (window.location.pathname !== "/login") window.location.href = "/login";
}

client.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config;
    if (err.response && err.response.status === 401 && !original._retried) {
      const refreshToken = localStorage.getItem("refresh_token");
      if (!refreshToken) {
        logoutToLogin();
        return Promise.reject(err);
      }
      original._retried = true;
      try {
        // Aynı anda birden fazla 401 gelirse tek bir refresh isteği paylaşılır.
        if (!refreshing) {
          refreshing = axios.post(`${API}/auth/refresh`, { refresh_token: refreshToken })
            .finally(() => { refreshing = null; });
        }
        const { data } = await refreshing;
        localStorage.setItem("token", data.token);
        original.headers.Authorization = `Bearer ${data.token}`;
        return client(original);
      } catch (refreshErr) {
        logoutToLogin();
        return Promise.reject(err);
      }
    }
    return Promise.reject(err);
  }
);

export default client;
