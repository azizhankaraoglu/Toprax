import { useCallback, useEffect, useState } from "react";
import api from "@/api";

/**
 * useFetch — sayfalarda (frontend/src/pages/*.jsx) 40+ dosyada AYNI şekilde
 * tekrarlanan "useState + useEffect + api.get(url).then((r) => setX(r.data))"
 * kalıbını tek bir yere toplar. Genel refactoring (2026-07-11) kapsamında
 * eklendi — DAVRANIŞI DEĞİŞTİRMEZ, sadece boilerplate'i azaltır.
 *
 * Var olan sayfaların çoğu loading/error state'ini hiç kullanmıyordu (bkz.
 * Operasyon.jsx, Other.jsx) — bu hook geriye dönük UYUMLU: loading/error
 * alanlarını kullanmak istemeyen bir çağıran sadece `data`yı okuyabilir,
 * davranış birebir aynı kalır (mount'ta bir kere GET, sonucu state'e yaz).
 *
 * @param {string|null} url - null/"" verilirse istek atılmaz (koşullu fetch).
 * @param {object} [options]
 * @param {object} [options.params] - axios params (query string).
 * @param {any} [options.initialData] - ilk state değeri (çoğu sayfada []).
 * @returns {{data, setData, loading, error, reload}}
 *   - data: son başarılı yanıt (r.data) ya da initialData
 *   - setData: dışarıdan optimistic update için (mevcut sayfalardaki
 *     "setX((prev) => ...)" kalıplarıyla uyumlu)
 *   - loading: ilk yükleme VEYA reload() sırasında true
 *   - error: son hatanın (varsa) backend detail mesajı, yoksa ""
 *   - reload: aynı url/params ile yeniden fetch eder (mutasyon sonrası
 *     "load()" çağrılarının yerini alır)
 */
export function useFetch(url, { params, initialData = null } = {}) {
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(!!url);
  const [error, setError] = useState("");

  const paramsKey = params ? JSON.stringify(params) : "";

  const reload = useCallback(() => {
    if (!url) return Promise.resolve();
    setLoading(true);
    return api
      .get(url, { params })
      .then((r) => {
        setData(r.data);
        setError("");
        return r.data;
      })
      .catch((err) => {
        setError(err.response?.data?.detail || "Veri alınamadı");
        throw err;
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, paramsKey]);

  useEffect(() => {
    reload().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);

  return { data, setData, loading, error, reload };
}

export default useFetch;
