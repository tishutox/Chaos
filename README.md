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

Das Haus führt zum leeren Arbeitsbereich zurück. Auf kleinen Bildschirmen öffnet das Menü-Icon die Werkzeugleiste. Das Exportmenü zeigt die vorgesehenen Formate PNG, GLB und OBJ; die Exporte selbst sind noch nicht implementiert.

2D-Generator, 3D-Konverter, Asset-Verlauf, Bildupload, Pipeline-Status, Rückgängig/Wiederholen und Einstellungen sind derzeit Platzhalter und deaktiviert. Es gibt noch keine gespeicherten Assets oder Workspace-Daten, die zurückgesetzt werden könnten.

## Deployment auf Render

Erstellt einen **Web Service** mit diesem Repository und verwendet folgende Befehle:

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn main:app --bind 0.0.0.0:$PORT`
