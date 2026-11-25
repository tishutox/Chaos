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
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI-Server |
| `COMFY_WORKFLOW` | `workflow_api.json` | Pfad zum exportierten Workflow |
| `COMFY_PROMPT_NODE_ID` | automatisch | ID des positiven CLIPTextEncode-Nodes |
| `COMFY_OUTPUT_NODE_ID` | automatisch | ID des SaveImage-Nodes |
| `UI_ORIGINS` | lokal (Port 5000) und `https://chaos-pt2r.onrender.com` | Kommagetrennte erlaubte Browser-Origins |

Der Dienst ist für eine vertrauenswürdige lokale Umgebung vorgesehen und hat keine Authentifizierung. Nicht öffentlich oder auf allen Netzwerkinterfaces bereitstellen. Die CORS-Liste ist kein Ersatz für Zugriffsschutz. `/health` prüft nur, ob FastAPI erreichbar ist; die Generierung meldet Verbindungs- und Workflow-Fehler separat.

## Einstellungen und Workspace

Die Einstellungen werden lokal im Browser gespeichert. Eine leere Backend-URL verwendet `http://localhost:8000`; der Basis-Prompt wird an den optimierten Prompt angehängt. Bildauflösung, Freistellen und Negativ-Prompt werden zurzeit ausschließlich im ComfyUI-Workflow festgelegt. Die übrigen 3D-Einstellungen und der API-Key sind Platzhalter und beeinflussen die Pipeline nicht. Der API-Key wird unverschlüsselt im localStorage gespeichert und nicht übertragen.

Die Workspace-Verwaltung verwendet IndexedDB `asset-generator`, Store `assets`, mit den Feldern `id`, `kind`, `name`, `createdAt`, `linkedAssetId` und `data` (Blob). Ein JSON-Backup enthält gespeicherte Einstellungen und Assets, aber keinen API-Key und keine ungespeicherten Formularänderungen. Ein Import ersetzt nach Bestätigung Einstellungen und Assets; der vorhandene API-Key bleibt erhalten. „Lokale Assets löschen“ leert nur den Asset-Store. Daten und Backups sind nicht verschlüsselt.

## Deployment

Die Flask-Oberfläche läuft z. B. mit `gunicorn main:app --bind 0.0.0.0:$PORT` auf Render. Die Pipeline läuft immer auf dem eigenen Rechner. Die Render-Seite ruft `http://localhost:8000` im Browser des Nutzers auf, daher muss auf dem jeweiligen Rechner `.\start.ps1` laufen. Das Backend erlaubt dafür die Render-Origin und antwortet auf Private-Network-Preflights. Chrome/Edge fragen ggf. nach der Erlaubnis für den Zugriff auf lokale Geräte; diese bestätigen. Firefox oder Browser-Erweiterungen (Adblocker, Tracking-Schutz) können localhost-Anfragen blockieren. Dann die Seite lokal unter http://127.0.0.1:5000 verwenden.
