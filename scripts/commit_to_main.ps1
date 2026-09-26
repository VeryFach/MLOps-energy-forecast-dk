# Helper PowerShell untuk Windows lokal
# Usage: powershell -ExecutionPolicy Bypass -File scripts/commit_to_main.ps1
Write-Host "=== Git status sebelum commit ==="
git status
Write-Host ""
Write-Host "=== Remote ==="
git remote -v
Write-Host ""
Write-Host "=== Menambahkan file tugas ==="
git add src/ingest_data.py
git add src/preprocess.py
git add src/data/.gitkeep
git add data/raw/sample_consumption.csv
git add data/raw/sample_weather.csv
git add data/processed/sample_merged_data.csv
git add .gitignore
git add README.md
git add docs/README.md
git add src/energy_forecast/data/fetch_energy_dk.py
git add src/energy_forecast/data/fetch_weather.py
git add src/energy_forecast/data/merge_data.py

Write-Host ""
Write-Host "=== Status setelah add ==="
git status
Write-Host ""
Write-Host "=== Commit ==="
git commit -m @"
feat: tambah ingest_data.py & preprocess.py timestamp non-destruktif + sampel data + docs Codespaces

- src/ingest_data.py: Requests Energi Data Service + Open-Meteo, save_with_timestamp non-destruktif (Poin 2-3)
- src/preprocess.py: cleaning missing values, dedup, ffill, lag 168h (Poin 4)
- src/data/.gitkeep untuk rubrik Persiapan Lingkungan (Poin 1)
- data/raw/sample_*.csv + sample_merged_data.csv lolos .gitignore (Luaran 2)
- patch fetch_energy_dk/fetch_weather/merge_data (timestamp + clean_missing_values)
- update README.md & docs/README.md cara jalan di Codespaces (Luaran 3 + Poin 5)
"@

Write-Host ""
Write-Host "=== Push ke main ==="
git push origin main
Write-Host ""
Write-Host "=== Selesai ==="
git log --oneline -3
git ls-files | Select-String -Pattern "src/(ingest_data|preprocess|data/)|sample_"
