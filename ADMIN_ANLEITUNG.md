# Fightbase – Admin-Fotos, Nav-Hover, geprüfte Daten

## Neu: größere Navigation
Die Navigation hat größere Klickflächen, 16-Pixel-Schrift und einen roten Gaming-Hover: **Nur der gerade berührte Menüpunkt vergrößert sich**, die anderen bleiben an ihrer Position. Tastatur-Fokus und Mobilansicht wurden ebenfalls gestaltet.

## Einmalige Admin-Einrichtung
Adresse: http://127.0.0.1:5000/admin

Der Admin ist deaktiviert, bis du lokal ein langes Passwort und einen geheimen Sitzungsschlüssel eingerichtet hast.

1. Öffne boxing-app und erstelle dort die Datei .env (nicht in GitHub hochladen).
2. Erzeuge den Geheimschlüssel im Terminal: python -c "import secrets; print(secrets.token_urlsafe(40))"
3. Schreibe in boxing-app/.env:

    FIGHTBASE_ADMIN_PASSWORD=DEIN_SELBSTGEWAEHLTES_PASSWORT
    FIGHTBASE_SECRET_KEY=DEN_AUSGEGEBENEN_ZUFAELLIGEN_SCHLUESSEL_HIER_EINFUEGEN

4. Installiere die neue Abhängigkeit: python -m pip install -r requirements.txt
5. Beende Flask mit Strg + C und starte python app.py neu. Öffne /admin.

Passwort mindestens 10 Zeichen, Secret mindestens 32 Zeichen lang. Die .env wird durch die .gitignore geschützt.

## Boxerfotos selbst hochladen
- Boxer im Admin suchen und ein JPG-, PNG- oder WebP-Bild auswählen. Maximal 5 MB und mindestens 250 × 250 Pixel.
- Pillow kontrolliert Bilddatei/Abmessungen, korrigiert EXIF-Ausrichtung, begrenzt auf 1600 × 1600 Pixel und erzeugt eine saubere WebP-Kopie.
- Das Foto ersetzt das vorherige Bild **für das gewählte Boxerprofil**. Das eigene Foto wird in Boxerprofil, Duell und Boxerliste angezeigt.
- Dateiort: boxing-app/uploads/fighter_photos. Diese lokalen Bilddateien werden NICHT zu GitHub hochgeladen.
- Optional Fotograf/Originalquelle angeben. **Nur Bilder hochladen, an denen du die notwendigen Nutzungsrechte besitzt.**
- Bei mehreren Profilen mit demselben Namen bitte die richtige Profil-ID auswählen.

## Bilanz manuell korrigieren
- Siege, Niederlagen, Unentschieden und K.o.-Siege sowie eine öffentlich zugängliche Quelle eintragen.
- Zahlen werden validiert, KO-Siege dürfen Siege nicht überschreiten.
- Manuell eingetragene, belegte Zahlen haben Vorrang vor automatischen Importdaten und bleiben nach Neustart erhalten.
- Änderungen gelten pro Boxer-ID; bei Dubletten müssen gegebenenfalls mehrere Datensätze geprüft werden.

## Fehlende kommende Boxkämpfe
- Im Admin als Paarung mit Datum, Ort, Gewichtsklasse, Quelle und optional bestätigter Veranstaltungsbeginn-Uhrzeit ergänzen.
- Für bislang unbekannte Boxer wird ein zunächst leerer Profil-Stammdatensatz angelegt. Anschließend Foto/Bilanz pflegen.
- Manuell hinzugefügte Kämpfe sind auch wieder löschbar. Keine erfundenen Termine oder Ringwalk-Uhrzeiten.

## Grenzen und Datensicherung
Eine vollständig aktuelle weltweite Box-API steht in diesem kostenlosen Setup weiterhin nicht zur Verfügung. Der Admin ermöglicht die Pflege echter Daten, ersetzt aber keinen lizenzierten Live-Feed.

Für Backups lokal sichern:
- boxing-app/fightbase.db
- boxing-app/uploads/

Die SQLite-Datenbank wurde in einem früheren Entwicklungsstand versehentlich auf GitHub eingecheckt. Beim Aktualisieren mit git pull **keine lokalen Daten löschen**. Bei Git-Konflikten zuerst Backup und git status prüfen.


## Neu: Alle Boxerfotos mit einer ZIP-Datei importieren

Du musst nicht mehr jedes Foto einzeln hochladen.

### ZIP unter Windows vorbereiten

1. Lege einen Ordner `Boxerfotos` auf deinem PC an.
2. Speichere die Bilder darin, **benannt nach dem Boxer in Fightbase**:
   - `Tyson Fury.jpg`
   - `Anthony Joshua.png`
   - `Oleksandr Usyk.webp`
3. Rechtsklick auf den Ordner → **Senden an → ZIP-komprimierter Ordner**
   (oder in Windows 11: **In ZIP-Datei komprimieren**).
4. Öffne Fightbase und melde dich unter `http://127.0.0.1:5000/admin` an.
5. Oben im Bereich **Alle Boxerfotos auf einmal** die ZIP-Datei auswählen und
   **ZIP importieren und automatisch zuordnen** anklicken.
6. Fightbase zeigt danach einen **Importbericht mit Vorschaubildern**. Einträge
   ohne Treffer, mit mehreren gleichnamigen Boxern oder mit Dateifehlern werden
   erklärt und **nicht** blind zugeordnet.

### Falls zwei Profile denselben Namen haben

Standardmäßig genügt `Tyson Fury.jpg`, **sofern der Name in der Datenbank
eindeutig ist**. Bei mehreren gleichen Namen wird absichtlich nicht geraten.
In diesem Fall die Profil-ID aus der Admin-Boxerkarte übernehmen und so benennen:

`Tyson Fury__reviewed-tyson-fury.jpg`

Die Schreibweise des Namens muss mit dem gewählten Boxerprofil übereinstimmen.
Ein falsch geschriebener oder unbekannter Name wird im Importbericht als
`übersprungen` angezeigt. Fightbase überprüft **nicht**, ob das Gesicht im
Foto wirklich zum Dateinamen passt – bitte die Bilder selbst korrekt auswählen.

### Grenzen und Sicherheit

- Pro ZIP maximal **250 Dateien** und maximal **64 MB komprimiert**.
- Insgesamt maximal **120 MB entpackter Bildinhalt**.
- Pro Foto maximal **5 MB**, maximal **16 Megapixel**, mindestens 250×250 Pixel.
- Unterstützte Dateien: JPG, JPEG, PNG und WebP.
- Fotos werden in sicheres, kompaktes WebP umgewandelt; ZIP-Pfade werden
  niemals direkt in den Upload-Ordner entpackt.
- **Vorhandene eigene Bilder bleiben erhalten**, es sei denn, du aktivierst
  die Checkbox **„Bereits selbst hochgeladene Bilder ersetzen“**.
- Nach dem Upload wird die originale ZIP-Datei nicht gespeichert. Die
  automatisch zugeordneten WebP-Fotos liegen **nur auf deinem Computer** in
  `boxing-app/uploads/fighter_photos`, nicht im GitHub-Repository.
- ZIP-Dateien und Fotos nur aus vertrauenswürdiger Quelle verwenden und nur
  Bilder hochladen, für deren Nutzung du eine Berechtigung hast.
- Der Importbericht bleibt lokal in deiner SQLite-Datenbank erhalten.
