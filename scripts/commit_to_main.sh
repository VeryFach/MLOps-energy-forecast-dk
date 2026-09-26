#!/bin/bash
# Helper: commit semua perubahan tugas ke branch main (run di Codespaces/Linux)
# Usage: bash scripts/commit_to_main.sh
set -e
echo "=== Git status sebelum commit ==="
git status
echo ""
echo "=== Remote ==="
git remote -v
echo ""
echo "=== Menambahkan file tugas ==="
git add src/ingest_data.py src/preprocess.py src/data/.gitkeep
git add data/raw/sample_consumption.csv data/raw/sample_weather.csv data/processed/sample_merged_data.csv
git add .gitignore README.md docs/README.md
git add src/energy_forecast/data/fetch_energy_dk.py src/energy_forecast/data/fetch_weather.py src/energy_forecast/data/merge_data.py
echo ""
echo "=== Status setelah add ==="
git status
echo ""
echo "=== Commit ==="
git commit -m "feat: tambah ingest_data.py & preprocess.py timestamp non-destruktif + sampel data + docs Codespaces

- src/ingest_data.py: Requests Energi Data Service + Open-Meteo, save_with_timestamp non-destruktif (Poin 2-3)
- src/preprocess.py: cleaning missing values, dedup, ffill, lag 168h (Poin 4)
- src/data/.gitkeep untuk rubrik Persiapan Lingkungan (Poin 1)
- data/raw/sample_*.csv + sample_merged_data.csv lolos .gitignore (Luaran 2)
- patch fetch_energy_dk/fetch_weather/merge_data (timestamp + clean_missing_values)
- update README.md & docs/README.md cara jalan di Codespaces (Luaran 3 + Poin 5)"

echo ""
echo "=== Push ke main ==="
git push origin main
echo ""
echo "=== Selesai ==="
git log --oneline -3
git ls-files | grep -E "src/(ingest_data|preprocess|data/)|sample_"
