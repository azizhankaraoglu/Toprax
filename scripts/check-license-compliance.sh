#!/usr/bin/env bash
# check-license-compliance.sh -- PR-17: Bagimlilik Lisans Uyumluluk Raporu
#
# backend/requirements.txt'teki paketlerin lisanslarini tarar,
# docs/legal/BAGIMLILIK-LISANS-RAPORU.md'yi uretir. GPL/AGPL (copyleft)
# lisansli paketleri "kirmizi bayrakli" olarak isaretler -- ticari/
# on-premise satista bu tur lisanslar dagitilan yazilimin da acik kaynak
# olmasini gerektirebilir (nihai karar hukuk danismanina/kullaniciya aittir,
# bkz. PR-17 "Sizin Yapmanız Gerekir").
#
# Kullanim: bash scripts/check-license-compliance.sh

set -euo pipefail
cd "$(dirname "$0")/.."

pip install --quiet pip-licenses

python3 - << 'PYEOF'
import subprocess, json, re

reqs = [l.split("==")[0].strip().lower().replace("_", "-") for l in open("backend/requirements.txt")
        if l.strip() and not l.startswith("#")]

out = subprocess.run(["pip-licenses", "--format=json"], capture_output=True, text=True).stdout
data = json.loads(out)
by_name = {d["Name"].lower().replace("_", "-"): d for d in data}

rows, concerning = [], []
for r in reqs:
    d = by_name.get(r)
    if not d:
        rows.append((r, "?", "bulunamadı (kurulu değil bu ortamda)"))
        continue
    lic = d["License"]
    rows.append((d["Name"], d["Version"], lic))
    if re.search(r"\bGPL\b|AGPL|GPLv2|GPLv3|GPL-2|GPL-3", lic) and "LGPL" not in lic:
        concerning.append((d["Name"], lic))

with open("docs/legal/BAGIMLILIK-LISANS-RAPORU.md", "w", encoding="utf-8") as f:
    f.write("# Bağımlılık Lisans Uyumluluk Raporu (PR-17)\n\n")
    f.write("> Otomatik üretildi: `scripts/check-license-compliance.sh`. Ticari/on-premise satış için "
            "riskli kabul edilen lisanslar (GPL/AGPL) ayrıca işaretlenir.\n\n")
    f.write(f"**Taranan paket sayısı:** {len(rows)}  \n")
    f.write(f"**Kırmızı bayraklı (GPL/AGPL) paket sayısı:** {len(concerning)}\n\n")
    if concerning:
        f.write("## ⚠️ Kırmızı Bayraklı Paketler\n\n")
        for name, lic in concerning:
            f.write(f"- **{name}**: {lic} -- nihai kullanım kararı verilmeli\n")
        f.write("\n")
    else:
        f.write("## ✅ Kırmızı bayraklı (GPL/AGPL) paket bulunamadı\n\n")
    f.write("## Backend (Python) — Tüm Paketler\n\n| Paket | Sürüm | Lisans |\n|---|---|---|\n")
    for name, ver, lic in sorted(rows):
        f.write(f"| {name} | {ver} | {lic} |\n")
    f.write("\n## Frontend (Node/npm)\n\nBu ortamda `node_modules/` kurulu değilse şu komutla üretin:\n\n")
    f.write("```bash\ncd frontend && npx license-checker --summary\nnpx license-checker --csv > ../docs/legal/frontend-licenses.csv\n```\n")

print(f"Rapor yazıldı: docs/legal/BAGIMLILIK-LISANS-RAPORU.md ({len(rows)} paket, {len(concerning)} kırmızı bayraklı)")
PYEOF
