# Startet das lokale Backend (FastAPI, Port 8000). Ollama und ComfyUI müssen separat laufen.
Set-Location $PSScriptRoot
if (-not (Test-Path .\workflow_api.json)) {
    Write-Warning "workflow_api.json fehlt. In ComfyUI 'Save (API Format)' wählen und die Datei hier ablegen."
}
& .\.venv\Scripts\python.exe -m uvicorn backend:app --host 0.0.0.0 --port 8000
