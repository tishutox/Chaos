# Asset Generator

Lokaler Arbeitsbereich für Pixel-Art-Assets. Die bestehende Flask-Webseite läuft auf Port 5000; ein separates FastAPI-Backend auf Port 8000 orchestriert Ollama und ComfyUI. Stufe 1.1 erzeugt ein PNG; die 3D-Konvertierung und der Asset-Verlauf sind noch nicht implementiert.

## Einrichtung und Start

Voraussetzungen: Python, Ollama mit einem lokal heruntergeladenen Modell, eine laufende ComfyUI-Installation und ein eigener ComfyUI-Workflow im API-Format. Die benötigten Modelle und Custom Nodes müssen in ComfyUI installiert sein.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ollama pull llama3.2
```

Ollama auf `127.0.0.1:11434` und ComfyUI auf `127.0.0.1:8188` starten. Erstellt in ComfyUI einen Workflow mit einem **positiven CLIPTextEncode**, Bildgenerierung, Hintergrundentfernung, Nearest-Neighbor-Resize (z. B. 64 × 64 oder 128 × 128) und einem **SaveImage**-Ausgabe-Node. Ein Pixel-Art-Modell bzw. LoRA und ein passender Background-Removal-Node müssen separat installiert werden. Prüft den Workflow zuerst in ComfyUI und exportiert ihn über **Save (API Format)** als `workflow_api.json` im Projektverzeichnis. Dieser installationsspezifische Workflow wird nicht mitgeliefert oder in Git gespeichert.

Das Backend erkennt den positiven CLIPTextEncode-Node (über den KSampler) und den SaveImage-Node automatisch. Nur falls das nicht passt, setzt `COMFY_PROMPT_NODE_ID` und `COMFY_OUTPUT_NODE_ID`. Backend starten:

```powershell
.\start.ps1
```

`http://127.0.0.1:8000/status` zeigt, ob Ollama, ComfyUI und der Workflow erreichbar sind.

Für die lokale Webseite in einem zweiten Terminal:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

Die Webseite ist unter http://127.0.0.1:5000 erreichbar. Der Workflow muss ein PNG mit Alpha-Kanal ausgeben; das Backend prüft das Ausgabeformat, erzeugt Transparenz und Pixelkanten aber nicht selbst. Ollama erweitert die Eingabe, FastAPI setzt den Text in den angegebenen Node, wartet über ComfyUIs History-API auf den Auftrag und liefert das Bild zurück. ComfyUI speichert seine Ausgabe zusätzlich entsprechend seiner eigenen Konfiguration. Das Bild lässt sich herunterladen und wird für Workspace-Backups lokal in IndexedDB gespeichert.

Optionale Umgebungsvariablen für FastAPI:

| Variable | Standard | Bedeutung |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama-Server |
| `OLLAMA_MODEL` | `llama3.2` | Installiertes Ollama-Modell |
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI-Server (nur lokaler Modus) |
| `COMFY_API_KEY` | leer | Comfy-Cloud-API-Key (z. B. `comfyui-…`). Wenn gesetzt, wird statt des lokalen ComfyUI die Cloud-API verwendet. |
| `COMFY_CLOUD_BASE_URL` | `https://cloud.comfy.org` | Basis-URL der Comfy-Cloud-API |
| `IMAGE_API` | `cloudflare` | Bild-Backend: `cloudflare` (Workers AI FLUX), `pollinations` (Pollinations.ai) oder leer (ComfyUI lokal/Cloud). |
| `GEMINI_API_KEY` | leer | Google-Gemini-Key für die Prompt-Erweiterung (Cloud). Ohne Key läuft die Erweiterung lokal über Ollama. |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Gemini-Modell für die Prompt-Erweiterung. |
| `CLOUDFLARE_API_TOKEN` | leer | Cloudflare-API-Token für Workers AI. |
| `CLOUDFLARE_ACCOUNT_ID` | leer | Cloudflare-Account-ID. |
| `CLOUDFLARE_MODEL` | `@cf/black-forest-labs/flux-1-schnell` | Cloudflare-Bildmodell. |
| `COMFY_WORKFLOW` | `workflow_api.json` | Pfad zum exportierten Workflow |
| `COMFY_PROMPT_NODE_ID` | automatisch | ID des positiven CLIPTextEncode-Nodes |
| `COMFY_OUTPUT_NODE_ID` | automatisch | ID des SaveImage-Nodes |
| `UI_ORIGINS` | lokal (Port 5000) und `https://chaos-pt2r.onrender.com` | Kommagetrennte erlaubte Browser-Origins |

Der Dienst ist für eine vertrauenswürdige lokale Umgebung vorgesehen und hat keine Authentifizierung. Nicht öffentlich oder auf allen Netzwerkinterfaces bereitstellen. Die CORS-Liste ist kein Ersatz für Zugriffsschutz. `/health` prüft nur, ob FastAPI erreichbar ist; die Generierung meldet Verbindungs- und Workflow-Fehler separat.

## Einstellungen und Workspace

Die Einstellungen werden lokal im Browser gespeichert. Eine leere Backend-URL verwendet `http://localhost:8000`; der Basis-Prompt wird an den optimierten Prompt angehängt. Bildauflösung, Freistellen und Negativ-Prompt werden zurzeit ausschließlich im ComfyUI-Workflow festgelegt. Die übrigen 3D-Einstellungen und der API-Key sind Platzhalter und beeinflussen die Pipeline nicht. Der API-Key wird unverschlüsselt im localStorage gespeichert und nicht übertragen.

Die Workspace-Verwaltung verwendet IndexedDB `asset-generator`, Store `assets`, mit den Feldern `id`, `kind`, `name`, `createdAt`, `linkedAssetId` und `data` (Blob). Ein JSON-Backup enthält gespeicherte Einstellungen und Assets, aber keinen API-Key und keine ungespeicherten Formularänderungen. Ein Import ersetzt nach Bestätigung Einstellungen und Assets; der vorhandene API-Key bleibt erhalten. „Lokale Assets löschen“ leert nur den Asset-Store. Daten und Backups sind nicht verschlüsselt.

## Cloud-Hosting (Render)

Die komplette Pipeline läuft in der Cloud — kein lokaler Rechner nötig:

- **Frontend** (Flask): als Render-Web-Service mit Startbefehl `gunicorn main:app --bind 0.0.0.0:$PORT`.
- **Backend** (FastAPI): als zweiter Render-Web-Service mit Startbefehl `uvicorn backend:app --host 0.0.0.0 --port $PORT`.
- **Umgebungsvariablen** auf dem Backend-Service setzen: `GEMINI_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `IMAGE_API=cloudflare` und `UI_ORIGINS=https://<frontend-domain>`.
- Im Frontend (Einstellungen) die Backend-URL auf `https://<backend-domain>` setzen; ohne Eintrag verwendet das Frontend `http://<hostname>:8000`.

Damit ist die Generierung von jedem Gerät mit Internetzugang erreichbar. Lokale Dienste (Ollama/ComfyUI) werden nicht benötigt: die Prompt-Erweiterung läuft über Gemini und die Bild-Erzeugung über Cloudflare (mit Pollinations als Fallback bei Inhaltsfiltern).
