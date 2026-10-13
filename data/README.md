# PLZ-Daten

`plz_centroids.csv` enthält pro deutscher Postleitzahl einen Ortsnamen und einen Koordinatenpunkt (Spalten `plz`, `ort`, `lat`, `lon`). Die App nutzt die Datei, um PLZ offline in Koordinaten aufzulösen.

## Quelle und Lizenz

Abgeleitet aus dem Postleitzahlen-Dump von [GeoNames](https://www.geonames.org) für Deutschland: https://download.geonames.org/export/zip/DE.zip

Lizenz: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), Urheber GeoNames. Die Datei fällt nicht unter die MIT-Lizenz des Codes.

## Änderungen gegenüber dem Original

- Auf eine Zeile pro PLZ zusammengefasst.
- `lat` und `lon` sind der Mittelwert aller GeoNames-Einträge zu dieser PLZ.
- `ort` ist einer der GeoNames-Ortsnamen zu dieser PLZ. Bei Großkunden-PLZ steht dort der Name einer Organisation, zum Beispiel `01053,Commerzbank AG`.
