# Fightbase – Admin und Datenpflege (FH-Projekt)

Fightbase zeigt ab 11. Oktober 2026 **keine Boxerfotos** mehr an. Foto-Suche, Foto-Upload, Bildvorschläge und ZIP-Fotoimport sind aus der Anwendung entfernt.

## Lokaler Admin

Adresse: http://127.0.0.1:5000/admin

Einmalige Einrichtung in `boxing-app/.env` (nicht in GitHub hochladen):

```env
FIGHTBASE_ADMIN_PASSWORD=EIN_LANGES_SELBSTGEWAEHLTES_PASSWORT
FIGHTBASE_SECRET_KEY=EIN_MINDESTENS_32_ZEICHEN_LANGER_ZUFAELLIGER_WERT
```

Zufälligen Sitzungsschlüssel lokal erzeugen: `python -c "import secrets; print(secrets.token_urlsafe(40))"`.

Installiere die Abhängigkeiten im Ordner `boxing-app` mit `python -m pip install -r requirements.txt`, starte `python app.py`, und melde dich über `/admin` an.

## Boxerstatistiken pflegen

- Boxer suchen und die Siege, Niederlagen, Unentschieden und K.o.-Siege bearbeiten.
- Belege die Zahlen mit einer öffentlichen Quellen-URL.
- K.o.-Siege dürfen die Anzahl der Siege nicht überschreiten.
- Manuelle Bilanzangaben haben Vorrang vor automatisch importierten Daten.

## Kämpfe hinzufügen

Fehlende, tatsächlich angekündigte Kämpfe lassen sich mit Paarung, Datum, Veranstaltungsort und überprüfbarer Quelle anlegen und später löschen. Nicht bestätigte Uhrzeiten bleiben leer.

## API-Daten

Unter `/admin` kann der optionale Boxing-Data-API-Zugang getestet oder manuell synchronisiert werden. Auf dem kostenlosen Hosting muss der API-Schlüssel nicht konfiguriert sein. **Niemals API-Schlüssel oder Admin-Passwörter in GitHub hochladen.**

## Backups

Die lokale SQLite-Datei `boxing-app/fightbase.db` enthält historische Daten, Admin-Einträge und Vergleiche. Vor größeren Änderungen lokal sichern. Auf kostenlosen Web-Hosts ohne dauerhaften Datenträger können nach einem Neustart manuell hinzugefügte Daten verloren gehen.
