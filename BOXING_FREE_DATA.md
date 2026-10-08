# Fightbase – kostenlose Boxdaten

Diese Version verwendet die öffentliche **TheSportsDB v1 API** (öffentlicher Schlüssel `123`) und benötigt **kein RapidAPI-Abonnement**.

## Start

```powershell
cd boxing-app
python -m pip install -r requirements.txt
python app.py
```

Öffne http://127.0.0.1:5000. Die Synchronisierung findet beim ersten Öffnen im Hintergrund statt und anschließend etwa alle sechs Stunden, solange Flask läuft.

## Wichtige Einschränkungen

- Der kostenlose Feed liefert nur begrenzte Fighting-/Boxing-Ereignisse, nicht alle Kämpfe weltweit.
- Es werden ausschließlich ausdrücklich als Boxing erkannte Einträge angezeigt; keine erfundenen Kämpfe.
- Alter und Boxerprofile können unvollständig sein; echte Kampfbilanzen und offizielle Ranglisten sind über diesen Feed nicht verlässlich erhältlich.
- Bestehende Daten aus einer früheren API-Version bleiben in SQLite vorhanden und können weiterhin angezeigt werden; die neue Synchronisierung aktualisiert nur TheSportsDB-Daten.
- Das bestehende Fightbase-Vergleichstool bleibt unter `/vergleich` erhalten.

Quelle: https://www.thesportsdb.com/docs_api_guide.php
