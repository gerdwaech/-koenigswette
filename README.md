# KÖNIGSWETTE – deploy-ready MVP

## Lokal starten
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

## Produktion / Render
Build command:
```bash
pip install -r requirements.txt
```

Start command:
```bash
gunicorn --workers 1 --threads 4 --timeout 60 app:app
```

Environment variables:
- `SECRET_KEY` = lange zufällige Zeichenfolge
- `ADMIN_PIN` = eigene Admin-PIN
- `DB_PATH` = `/var/data/koenigswette.db`

Für SQLite muss bei Render ein Persistent Disk unter `/var/data` eingebunden werden. Eine Instanz / ein Gunicorn-Worker ist für dieses MVP vorgesehen.

Öffentliche Seite: `/`
Admin: `/admin`
Ergebnis: `/result`
Healthcheck: `/health`

## Enthalten
- freie Kandidatenanlage durch jeden Nutzer
- Mehrfachwetten / unterschiedliche Kandidaten
- Live-Pool und dynamischer Pool-Faktor
- WhatsApp-Share-Link
- Wettannahme öffnen/schließen
- Zahlstatus im Adminbereich
- König festlegen
- automatische Ergebnis-/Poolauswertung

Zahlungsanbieter ist noch nicht integriert; Einsätze und Zahlstatus werden erfasst.
