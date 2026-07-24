/**
 * PUBLIC RAPOR GÖRÜNTÜLEYİCİ (Denetim raporu #7 / Faz 6)
 *
 * `/rapor/:token` — login GEREKMEZ (forms_module.py'nin `/form/:token`
 * public sayfasıyla AYNI kalıp: `api` istemcisi zaten token yoksa
 * Authorization header eklemiyor, 401 üretmediği için interceptor'ın
 * refresh/logout mantığı hiç tetiklenmez).
 */
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/api";
import { FileBarChart2, Download, AlertTriangle } from "lucide-react";

export default function PublicReportViewer() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/public/reports/${token}`)
      .then((r) => setData(r.data))
      .catch((err) => setError(err.response?.data?.detail || "Rapor yüklenemedi"));
  }, [token]);

  function downloadCsv() {
    window.open(`${api.defaults.baseURL}/public/reports/${token}/export.csv`, "_blank");
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[var(--bg)] grain flex items-center justify-center p-4">
        <div className="card p-8 max-w-md text-center">
          <AlertTriangle className="mx-auto mb-3 text-red-400" size={32}/>
          <div className="font-display text-lg mb-1">Rapor Görüntülenemiyor</div>
          <div className="text-sm text-[var(--text-dim)]">{error}</div>
        </div>
      </div>
    );
  }

  if (!data) {
    return <div className="min-h-screen bg-[var(--bg)] grain flex items-center justify-center text-[var(--text-dim)]">Yükleniyor…</div>;
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] grain p-4 md:p-8" data-testid="public-report-page">
      <div className="max-w-4xl mx-auto">
        <header className="flex items-center justify-between mb-6 print:hidden">
          <div className="flex items-center gap-2">
            <FileBarChart2 className="text-[var(--primary)]" size={22}/>
            <div>
              <h1 className="font-display text-2xl">{data.template_name}</h1>
              <div className="text-xs text-[var(--text-dim)]">
                Oluşturulma: {(data.generated_at || "").slice(0, 16).replace("T", " ")} ·
                Toplam {data.total} kayıt {data.truncated && "(ilk 500 kayıt)"}
              </div>
            </div>
          </div>
          <button onClick={downloadCsv} className="btn btn-primary text-sm flex items-center gap-1.5">
            <Download size={14}/> CSV İndir
          </button>
        </header>

        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] text-[var(--text-dim)] uppercase tracking-wider border-b border-[var(--border)]">
                {data.columns.map((c) => <th key={c} className="p-3">{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, i) => (
                <tr key={i} className="border-b border-[var(--border)]">
                  {data.columns.map((c) => <td key={c} className="p-3">{String(row[c] ?? "—")}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          {data.rows.length === 0 && <div className="text-center text-[var(--text-dim)] py-10">Kayıt yok</div>}
        </div>
      </div>
    </div>
  );
}
