# Fightbase – kostenlose Boxing Data API verbinden

Die Boxing Data API bietet laut https://boxing-data.com/pricing/ einen **Basic-Tarif für $0 mit 100 Anfragen pro Monat** an. Welche Endpunkte dieser Tarif tatsächlich freischaltet, lässt sich erst mit deinem persönlichen Schlüssel testen. Die Verbindung ist optional. Fightbase funktioniert weiterhin ohne API-Schlüssel, mit lokalem Open-Boxing-Archiv und deinen Admin-Daten.

## Schritt 1: Wirklich nur kostenlosen Tarif auswählen

1. Öffne die Anleitung: https://boxing-data.com/docs/getting-started/
2. Folge dem Link **Boxing Data API on RapidAPI**.
3. Konto erstellen, **Basic / Free ($0)** prüfen und bewusst auswählen.
4. **Keinen kostenpflichtigen Tarif** aktivieren. Prüfe vor Bestätigung, ob Gebühren, automatische Upgrades oder Zahlungsdaten verlangt werden.
5. Kopiere den persönlichen RapidAPI-Schlüssel. **Nicht im Chat teilen und niemals zu GitHub hochladen.**

## Schritt 2: API-Schlüssel nur lokal speichern

Im lokalen Fightbase-Ordner `boxing-app/.env` (dort liegt ggf. bereits dein Admin-Passwort) diese zusätzlichen Zeilen ergänzen:

```dotenv
BOXING_API_KEY=HIER_DEIN_ECHTER_RAPIDAPI_KEY
BOXING_API_AUTO_SYNC=true
```

Bestehende `FIGHTBASE_ADMIN_PASSWORD` und `FIGHTBASE_SECRET_KEY` **nicht löschen**. Die Datei `.env` wird von Git ignoriert. Danach Flask stoppen (Strg + C), `python -m pip install -r requirements.txt`, `python app.py` starten.

## Schritt 3: Verbindung überprüfen

Öffne `http://127.0.0.1:5000/admin`, melde dich an und benutze im Abschnitt **Kostenlose Boxing Data API**:

- **Verbindung testen**: genau **eine** API-Anfrage an den dokumentierten Boxer-Suchendpunkt. Fightbase meldet, ob die Verbindung funktioniert, und importiert eventuelle gefundene Profile.
- **Boxer & Kämpfe synchronisieren**: im Hintergrund höchstens fünf Anfragen für aktuelle Paarungen, Ergebnisse und Boxerprofile. Der Anbieter kann einzelne Endpunkte im Gratis-Tarif sperren; Fightbase zeigt dann einen Fehler und behält vorhandene lokale Daten.
- Fightbase versucht bei aktiviertem `BOXING_API_AUTO_SYNC=true` höchstens einmal je sieben Tage automatisch zu aktualisieren, solange dein lokaler Flask-Server läuft.

### Sparsamer Anfragenverbrauch

- Basic wird mit 100 Anfragen/Monat beworben.
- Fightbase setzt vorsichtshalber **eine eigene feste Grenze von 30 Versuchen pro UTC-Monat** (Tests, Fehler und automatische Aufrufe zählen ebenfalls).
- Die einzelnen Anfragen und der Zähler werden in `fightbase.db` gespeichert. Die Zählung schützt nur diese Fightbase-Installation. Direkte Tests auf RapidAPI oder andere Programme zählen beim Anbieter zusätzlich.
- Es erfolgen **keine automatischen Wiederholungen bei HTTP 403/429**. Ein abgewiesener Endpunkt wird bis zum Monatswechsel von Fightbase nicht weiter abgefragt.
- Kämpfe und Bilanzen werden in SQLite zwischengespeichert; normale Seitenaufrufe benötigen keine RapidAPI-Anfrage.
- Wenn du die automatischen Abfragen deaktivieren möchtest, setze `BOXING_API_AUTO_SYNC=false`.
- Wichtig: Kosten und automatische Tarifwechsel hängen vom **gewählten RapidAPI-Abo** ab. Fightbase selbst kann keine RapidAPI-Abrechnung kontrollieren. Keine Garantie, dass alle gewünschten Endpunkte im Gratisplan verfügbar sind.

## Was die Daten liefern können

- Boxerlisten mit vollständigen W/L/D/KO-Zahlen, Alter und Nationalität, sofern der Endpunkt im Tarif verfügbar ist.
- Veranstaltungsdaten und kommende/abgeschlossene Kämpfe, sofern die jeweiligen Endpunkte freigeschaltet sind und echte Einträge zurückgeben.
- Fotos kommen weiterhin von verifizierten Wikidata-/Wikimedia-Quellen bzw. deinen eigenen Uploads; diese API garantiert keine schönen Portraits.
- Gezielte Admin-Korrekturen von Bilanzen und Fotos behalten Vorrang. Der Import überschreibt weder die `history`-Analysen noch die lokalen Bilder.
- Ein API-Fight ohne zwei identifizierbare Boxer, mit altem Termin oder ohne belastbare Daten wird nicht als kommender Kampf hinzugefügt.

## Technische Details

Code: `boxing-app/boxing_rapidapi.py`. Die API-Aufrufe dürfen nur die erlaubten Pfade `/v2/fighters/`, `/v2/fights/schedule`, `/v2/fights/` verwenden. Die API-Schlüssel werden nur zur Anfrage im HTTP-Header verwendet, nicht in Logs oder SQLite gespeichert. Kontingentprüfung und Anfragebuchung erfolgen mit Lock vor dem HTTP-Aufruf. Die Anbindung ist durch Offline-Mocktests abgesichert; der echte Gratis-Tarif ist erst nach deinem eigenen Schlüssel überprüfbar.

Quellen:
https://boxing-data.com/docs/endpoints/fighters/
https://boxing-data.com/docs/endpoints/fights/
https://boxing-data.com/pricing/
