# Fightbase: Requirement-Check (08.10.2026)

Dieser Stand trennt **belegte Fakten** von **fehlenden Daten**.

## Lieferumfang
- 8 angekündigte echte Kämpfe mit beiden Boxern, Datum, Veranstaltungsbeginn in Ortszeit, Arena, Quelle und Prüfdatum 08.10.2026. Termine können sich ändern; kein Echtzeit-Abgleich aus einer vollständig kostenlosen API.
- Übernommene, belegte Bilanzen bei sechs aktiven Boxern: Schofield, Bahdi, Dubois, Wardley, Fury und Joshua. Andere Karrierebilanzen werden **nicht erfunden**.
- Historische echte Boxkämpfe und Ergebnisse aus Open Boxing mit KO/TKO/Entscheidung soweit im Archiv vorhanden.
- Nur genau **ein** per Wikidata-Entity (exakter Name + Boxerberuf + P18) zugeordnetes Wikimedia-Foto. Bei fehlender/uneindeutiger Quelle wird absichtlich kein Foto angezeigt. Fotos müssen nicht neu sein. Alte unüberprüfte Fotoauswahlen werden nicht genutzt.
- WBA/WBC/IBF/WBO: Informationen und Verlinkung auf offizielle Titel- und Ranglistenseiten. Ohne Live-Daten werden keine aktuellen Titelträger behauptet.
- Suchfelder für Boxer, Kämpfe und Organisationen.
- Drei-Ausgänge-Demomodell für kommende Kämpfe mit Bilanz: Sieg A + Unentschieden + Sieg B = 100 %; drei geteilte Balken; heuristisch, keine kalibrierten Quoten.

## Noch nicht vollständig erfüllt
- REQ-F-001/003/004/005: Weltweit vollständiger aktueller Kampfplan, alle Boxer mit Nationalität/Alter/Bilanz/Organisation und täglich aktualisierte Weltmeisterlisten. Für diese Vollständigkeit fehlt ein verlässlicher frei verwendbarer Live-Feed.
- REQ-NF-004: Eine Ladezeit <= 3 Sekunden für **alle** Daten wurde noch nicht mit realen Netzbedingungen nachgemessen. HTML kommt lokal aus SQLite, Fotos werden erst nachträglich geladen. Beim ersten Start braucht der Import Zeit.
- REQ-F-007: Das Demo-Modell ist noch keine objektiv auf realen historischen Kämpfen trainierte Prognose.

## Referenzen
Kalender:
- https://fightnights.com/Floyd-Schofield-vs-Lucas-Bahdi-WBA-Lightweight-Title-Fight-3880
- https://www.fightnights.com/Daniel-Dubois-vs-Fabio-Wardley-II-WBO-World-Heavyweight-Title-3883
- https://www.fightnights.com/Tyson-Fury-vs-Anthony-Joshua-3890

Boxer-Statistiken: in boxing-app/verified_fights.py hinterlegt.

Bilder: https://www.wikidata.org/ und https://commons.wikimedia.org/wiki/Main_Page. Lizenz ist für jede Datei individuell zu prüfen; Bildjahr nicht garantiert.

Organisationen: https://www.wbaboxing.com/wba-ranking · https://wbcboxing.com/en/ · https://www.ibf-usba-boxing.com/ · https://wboboxing.com/rankings/
