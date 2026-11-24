# Asset Generator

Leere Flask-Website als Ausgangspunkt für euer Uniprojekt.

## Starten

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Danach ist die Website unter [http://127.0.0.1:5000](http://127.0.0.1:5000) erreichbar.

Die Startseite liegt in `templates/index.html`, das Styling in `static/style.css` und die Flask-Anwendung in `main.py`.

## Werkzeugleiste

Das Haus führt zum leeren Arbeitsbereich zurück. Auf kleinen Bildschirmen öffnet das Menü-Icon die Werkzeugleiste. Das Exportmenü zeigt die vorgesehenen Formate PNG, GLB, FBX und OBJ; die Asset-Exporte selbst sind noch nicht implementiert.

2D-Generator, 3D-Konverter, Asset-Verlauf, Bildupload, Pipeline-Status und Rückgängig/Wiederholen sind derzeit Platzhalter und deaktiviert. Die Einstellungen sind über die Werkzeugleiste erreichbar. Sie werden nach dem Speichern lokal im Browser abgelegt; die Generatoren sind noch nicht angebunden und verwenden die Werte daher noch nicht.

Der Verbindungstest ruft `GET /health` an der angegebenen Backend-URL direkt aus dem Browser auf. Das Backend muss CORS für die Website erlauben; eine HTTPS-Website kann kein HTTP-Backend aufrufen, wenn der Browser Mixed Content blockiert. Der API-Key wird dabei nicht übertragen. Der optionale API-Key wird unverschlüsselt im localStorage gespeichert und ist für Skripte dieser Website sowie Personen mit Zugriff auf das Browserprofil lesbar.

Die Workspace-Verwaltung verwendet die IndexedDB-Datenbank `asset-generator` mit dem Store `assets`. Ein Asset hat die Felder `id` (eindeutiger String), `kind` (`2d` oder `3d`), `name`, `createdAt` (ISO-Datum), `linkedAssetId` (String oder `null`) und `data` (Blob). Die Anzeige des Speicherverbrauchs ist eine Browser-Schätzung für die gesamte Website, nicht nur für diese Datenbank. Die noch ausstehenden Generatoren und der Verlauf müssen an diesen Store angebunden werden.

Der JSON-Export enthält gespeicherte Einstellungen und Assets, aber keinen API-Key und keine ungespeicherten Formularänderungen. Ein Import ersetzt nach Bestätigung Einstellungen und Assets; der vorhandene API-Key bleibt erhalten. „Lokale Assets löschen“ leert nur den Asset-Store, nicht Einstellungen oder API-Key. Die Daten und Backups sind nicht verschlüsselt.

## Deployment auf Render

Erstellt einen **Web Service** mit diesem Repository und verwendet folgende Befehle:

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn main:app --bind 0.0.0.0:$PORT`
