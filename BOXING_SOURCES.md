# Fightbase – echte Daten ohne Bezahl-Abo

## 1. Historische Boxer und Kämpfe – Open Boxing
Quelle: https://github.com/edhwright/open-boxing
Originaldaten: src/db/data/bouts.csv und src/db/data/champions.csv
Lizenz: MIT (siehe https://github.com/edhwright/open-boxing/blob/main/LICENSE.md)

Der historische Datenauszug liegt in \`boxing-app/data/openboxing_archive.json\`. Fightbase übernimmt ihn **lokal** beim Start automatisch in \`fightbase.db\`. Der Import ist wiederholbar, benötigt weder API-Key noch Onlinezugang, verändert keine bisherigen Analysen und enthält ausschließlich in der Quelle als FINISHED markierte Duelle.

Zusätzlich versucht Fightbase einmal wöchentlich, neu verfügbare historische Ergebnisse über die kostenlose Open-Boxing-JSON-API zu ergänzen. Bei Netzfehlern bleibt der lokale Bestand erhalten.

**Wichtig:** Die Open-Boxing-Daten reichen in der gelieferten CSV bis 2023; alte SCHEDULED-Einträge wurden bewusst ausgeschlossen. Es ist **kein** aktueller, vollständiger Profikampfsportkalender. Der Datensatz konzentriert sich auf Titelkämpfe; Bilanz (Wins/Losses) für den Boxer insgesamt wird nicht daraus erfunden. Es werden einzelne Kampfergebnisse dargestellt, nicht ein vollständiges Fighter-Record.

## 2. Kommende Kämpfe – TheSportsDB
Quelle: https://www.thesportsdb.com/
Kostenloser v1-Endpunkt mit öffentlichem Schlüssel 123. Boxabdeckung unvollständig; nur Kämpfe mit zwei ausdrücklich benannten Boxern erscheinen im kommenden Kampfkalender. MMA-/ONE-Events werden nicht als Boxkämpfe ausgegeben.

## 3. Bilder
Bestehende Wikipedia-/Wikimedia-Foto-Funktion. Genau ein Foto pro Boxer; Bilder sind nicht garantiert neu. Lizenzen und Urheber nennen, bevor Fightbase öffentlich eingesetzt wird.

## Nutzung
\`\`\`powershell
cd boxing-app
python -m pip install -r requirements.txt
python app.py
\`\`\`
Die Startseite öffnet bei fehlenden Live-Duellen automatisch das historische Ergebnisarchiv. Suche Boxer im Tab »Boxer«.
