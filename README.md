# Asset Generator

Hochschulprojekt: ein browserbasierter Generator für Pixel-Art-Game-Assets (2D). Die Generierung läuft vollständig in der Cloud und ist von jedem Gerät mit Internetzugang erreichbar — kein lokaler Rechner nötig.

## Architektur

```
Frontend (Flask)  →  Backend (FastAPI)  →  Gemini (Prompt) + Cloudflare (Bild)  →  PNG
```

1. Die **Prompt-Erweiterung** läuft über **Google Gemini** (`gemini-3.1-flash-lite`).
2. Die **Bild-Erzeugung** läuft über **Cloudflare Workers AI** (FLUX.1-schnell).
3. Das Backend erzeugt daraus ein **pixeliertes PNG mit transparentem Hintergrund** (Nearest-Neighbor-Pixelierung + Eck-Floodfill).

Fallbacks: Bei Gemini-Überlastung werden feste Pixel-Art-Tags angehängt; blockiert Cloudflares Inhaltsfilter einen Prompt (z. B. Waffen-Assets), springt die Bild-Erzeugung automatisch auf **Pollinations.ai** um.

Die 3D-Konvertierung (2D → Minecraft-/Voxel-Assets) und der Asset-Verlauf sind als nächste Stufen vorgesehen, noch nicht implementiert.

## Live-Deployment (Render)

| Dienst | URL |
|---|---|
| Frontend | `https://chaos-pt2r.onrender.com` |
| Backend | `https://chaos-backend-li2y.onrender.com` |

Die Website ist damit überall nutzbar — auch auf Mobilgeräten.

## Cloud-Einrichtung (Render)

- **Frontend** (Flask): Startbefehl `gunicorn main:app --bind 0.0.0.0:$PORT`. Variable `BACKEND_URL=https://chaos-backend-li2y.onrender.com` setzen; das Frontend liest sie aus einem `<meta name="backend-url">`-Tag und nutzt sie automatisch.
- **Backend** (FastAPI): Startbefehl `uvicorn backend:app --host 0.0.0.0 --port $PORT`.

## Umgebungsvariablen (Backend)

| Variable | Standard | Bedeutung |
|---|---|---|
| `IMAGE_API` | `cloudflare` | Bild-Backend: `cloudflare` (Workers AI FLUX), `pollinations` (Pollinations.ai) oder leer (ComfyUI lokal/Cloud) |
| `GEMINI_API_KEY` | leer | Google-Gemini-Key für die Prompt-Erweiterung. Ohne Key läuft die Erweiterung lokal über Ollama. |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Gemini-Modell für die Prompt-Erweiterung |
| `CLOUDFLARE_API_TOKEN` | leer | Cloudflare-API-Token für Workers AI |
| `CLOUDFLARE_ACCOUNT_ID` | leer | Cloudflare-Account-ID |
| `CLOUDFLARE_MODEL` | `@cf/black-forest-labs/flux-1-schnell` | Cloudflare-Bildmodell |
| `UI_ORIGINS` | lokal (Port 5000) + `https://chaos-pt2r.onrender.com` | Kommagetrennte erlaubte Browser-Origins |
| `BACKEND_URL` | leer | (Frontend) Backend-URL, die in das `backend-url`-Meta-Tag injiziert wird |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://127.0.0.1:11434` / `llama3.2` | Nur für den lokalen Ollama-Fallback |
| `COMFY_URL` / `COMFY_API_KEY` / `COMFY_CLOUD_BASE_URL` | lokal / leer / `https://cloud.comfy.org` | Nur für den ComfyUI-Modus (lokal oder Comfy Cloud) |
| `COMFY_WORKFLOW` / `COMFY_PROMPT_NODE_ID` / `COMFY_OUTPUT_NODE_ID` | `workflow_api.json` / automatisch | Nur für den ComfyUI-Modus |

Das Backend hat keine Authentifizierung. Die CORS-Liste ist kein Ersatz für Zugriffsschutz. `/health` prüft nur die Erreichbarkeit von FastAPI; `/status` zeigt den aktiven Bild-/LLM-Modus.

## Lokale Entwicklung (optional)

Für die lokale Entwicklung (ohne Cloud-APIs) kann das Backend mit ComfyUI + Ollama betrieben werden:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\start.ps1          # FastAPI-Backend auf Port 8000
python main.py       # Flask-Frontend auf Port 5000
```

Dafür müssen Ollama (mit `llama3.2`) und eine ComfyUI-Installation mit einem per **Save (API Format)** exportierten `workflow_api.json` laufen. Diese installationsspezifische Datei wird nicht in Git gespeichert. Beim lokalen ComfyUI-Modus gibt das Backend das Bild zurück und erzeugt Transparenz/Pixelkanten über die Eck-Floodfill-Logik.

## Einstellungen und Workspace

Die Einstellungen werden lokal im Browser gespeichert. Eine leere Backend-URL greift auf die injizierte Backend-URL (bzw. lokale Erkennung) zurück; der Basis-Prompt wird an den optimierten Prompt angehängt. Der API-Key wird unverschlüsselt im localStorage gespeichert und nicht übertragen.

Die Workspace-Verwaltung verwendet IndexedDB `asset-generator`, Store `assets`, mit den Feldern `id`, `kind`, `name`, `createdAt`, `linkedAssetId` und `data` (Blob). Ein JSON-Backup enthält gespeicherte Einstellungen und Assets, aber keinen API-Key und keine ungespeicherten Formularänderungen. Ein Import ersetzt nach Bestätigung Einstellungen und Assets. „Lokale Assets löschen“ leert nur den Asset-Store. Daten und Backups sind nicht verschlüsselt.
