# Fightbase Gesamtprüfung – 8. Oktober 2026

## Korrigiert

- **Termine:** Uhrzeiten mit offiziellen Arena-/Veranstalterangaben abgeglichen. Schofield–Bahdi 15:15 Uhr Chicago-Ortszeit, Fundora-Veranstaltung erster Kampf 14:00 Uhr Las-Vegas-Ortszeit, Fury–Joshua Veranstaltungsbeginn 17:00 Uhr Cardiff-Ortszeit. Bei fehlender zuverlässiger Uhrzeit bleibt sie ausdrücklich offen. Nicht mit der exakten Ringwalk-Zeit verwechseln.
- **Boxerbilanzen:** 16 zu den acht angekündigten Hauptkämpfen gehörende Boxer mit datierten W-L-D-KO-Zahlen und individueller Quellenadresse. Andere historische Boxer bleiben bei unvollständiger Bilanz als unbekannt gekennzeichnet.
- **Kampfergebnisse:** Sieger, Kampfausgang und ggf. Runde aus dem historischen Archiv werden in Übersicht und Details gezeigt.
- **Events:** Bestätigte Kampfankündigungen werden mit konsistenter Event-ID in der Eventübersicht gespeichert.
- **Fotos:** Nur ein Bild je eindeutig identifizierter Wikidata-Boxerperson; P18, Berufsangabe und exakter Name müssen zusammenpassen. Alte unzuverlässige Commons-Suchen auch in der Vergleichsseite abgeschaltet. Asynchrones Nachladen und Caching. Bildqualität oder aktuelles Aufnahmejahr nicht garantiert.
- **Prognosen:** Drei Ergebnisse (Sieg A / Unentschieden / Sieg B = 100 %) plus Balkendiagramm bei kommenden Kämpfen mit beiden W/L-Daten; eindeutig heuristische Demo, nicht kalibrierte tatsächliche Gewinnwahrscheinlichkeit.
- **Performance:** Lokale HTML-Antworten und Foto-API werden über Tests überprüft. Foto-Anfragen blockieren den Seitenaufruf nicht mehr. Eine Garantie für drei Sekunden inklusive externen Bildern kann ohne reale Browsertests nicht abgegeben werden.
- **Oberfläche:** Bereits zuvor verbesserte Schriftgrößen sowie zusätzlicher Bildfokus und passende Platzhalter.

## Stand je Requirement
| Anforderung | Stand |
| --- | --- |
| REQ-F-001 Kommende Kämpfe | Teilweise; acht datierte Paarungen, keine weltweite Live-Vollständigkeit |
| REQ-F-002 Ergebnisse | Historisches Archiv, Sieger/Ausgang soweit vorhanden; jüngste Ergebnisse nicht vollständig |
| REQ-F-003 Name/Nationalität/Alter/Organisation | Teilweise; Verfügbarkeit abhängig von Quelle |
| REQ-F-004 W/L/D/KO | 16 geprüfte Datensätze; übrige Boxer teils ohne Karrierebilanz |
| REQ-F-005 Boxorganisationen/Titel | Verbandsinformationen und offizielle Titel-Links, keine aktuelle komplette Titelträger-Datenbank |
| REQ-F-006 Suchfunktion | Im vorhandenen Datenbestand für Kämpfer, Kämpfe und Organisationen |
| REQ-F-007 Drei Prognosen | In Kampfdetails, wenn Daten vorhanden; alte manuelle Vergleiche weiter mit zwei Ausgängen |
| REQ-F-008 Balkendiagramm | In neuen Kampfdetails mit Daten |
| REQ-NF-001–003 Darstellung | Design vorhanden; Browser-Sichtprüfung noch notwendig |
| REQ-NF-004 3 Sekunden | Lokal per automatischen Routentests geprüft; echte Internet-Performance noch nicht bewiesen |

## Herkunft
- Open Boxing Archiv (MIT): https://github.com/edhwright/open-boxing
- Kostenlose TheSportsDB-API: https://www.thesportsdb.com/
- Boxerprofile und datierte Ankündigungen: URLs in boxing-app/verified_fights.py
- Personenbilder: Wikidata und Wikimedia Commons; Urheber/Lizenz sind pro Datei zu prüfen.

Die Seite ist weiterhin keine vollständig aktuelle FotMob-Alternative. Es gibt weder einen umfassenden kostenlosen Weltkampfdatenfeed noch vollständige Statistiken und aktuelle freigabefähige Boxerfotos für sämtliche Boxer.
