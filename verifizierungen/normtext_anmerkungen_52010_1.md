# Anmerkungen zum Normtext und gewählte Lesarten (DIN EN ISO 52010-1:2018-03)

Dieses Register legt die beim Umsetzen der DIN EN ISO 52010-1:2018-03 getroffenen Auslegungsentscheidungen offen: dokumentierte Druckfehler und Auslegungsspielräume des Normtexts, je Eintrag mit Fundstelle, Beleg und der von RoomCurve gewählten Lesart; keine Codebefunde. Prüfgrundlage: Lesung am Seitenbild der genannten Ausgabe (07/2026, zwei unabhängige Durchgänge). Gleiche Kategorie wie die dokumentierte Spaltenvertauschung Tabelle 28 der 52016-1 (EPB-Kommentar 28).

## N1 — Gleichung (15), S. 24: arcsin-Umfang im Druckbild
Der arcsin-Operator steht nur über dem Zähler; wörtlich würde ein Winkel durch eine dimensionslose Zahl geteilt, was mit der Fallunterscheidung Gl. (16) kein konsistentes Azimut ergibt. Intendiert: arcsin des gesamten Quotienten. Code: atan2-Formulierung, numerisch äquivalent zur intendierten Lesart (max. 1,4e-11 Grad; zweite unabhängige Rechnung: 7e-14 Grad).

## N2 — Tabelle 8, Zeile 8 („klar"), S. 20: Bedingung „ε < 6,200"
Gedruckt überlappt die Bedingung sämtliche Klassen 1–7. Intendiert (Anschluss an Klasse 7): ε ≥ 6,200. Code setzt die intendierte Lesart um; Kommentar an der Koeffiziententabelle.

## N3 — Interne Fehlverweise auf „Gleichung (20)" für I_ext
Abschnitt 6.4.4.2 (S. 29) und der Text nach Gl. (24) (S. 27) verweisen für die extraterrestrische Bestrahlungsstärke auf „Gleichung (20)"; nummeriert ist sie als (27). Gl. (20) ist die Luftmasse. Code zitiert korrekt (27).

## N4 — Tabelle 7, Fußnote e, S. 19: Azimut-Konvention widersprüchlich
Text „nach Osten positiv" vs. Mapping „Ost = −90". Betrifft nur die (nicht implementierte) Verschattung nach 6.4.5. Für die Flächenorientierung γ_ic gilt die widerspruchsfreie Fußnote d der Tabelle 6, der der Code folgt.

## Z1 — (Kein Normmangel, Transkriptionsnotiz) Tabelle 8, Klasse 1
Untergrenze in der Norm: 1,000 ≤ ε. Code führte 0,000; auf 1,000 korrigiert Sachlich folgenlos, da ε ≥ 1 analytisch aus Gl. (30) folgt; Gleitkomma-Schutz: Unterschreitungen fallen auf Klasse 1 (nicht Klasse 8).
