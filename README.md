# SmartSearchRadius

Ein Suchradius für Kleinanzeigen, der sich nach der Anfahrtszeit richtet.

## Das Problem

Wer bei Kleinanzeigen im Umkreis von 100 km sucht, bekommt einen Kreis um die eigene PLZ, gemessen in Luftlinie. Die Straße hält sich an diesen Kreis nicht. Eine Anzeige 70 km entfernt, hinter einem Mittelgebirge oder über Landstraßen durch drei Ortschaften, kostet dann plötzlich doppelt so viel Fahrzeit, wie man bei dem Radius erwartet hätte. Gleichzeitig fällt die Anzeige 120 km entfernt direkt an der Autobahn aus der Suche, obwohl man sie in ähnlicher Zeit erreicht.

Ob sich eine Abholung lohnt, entscheidet oft eher die Zeit im Auto. Ein Kilometerkreis bildet die schlecht ab.

## Die Idee

SmartSearchRadius ersetzt den Kreis durch die Fläche, die man von der Start-PLZ aus in einer gewählten Zeit mit Auto oder Fahrrad tatsächlich erreicht (Isochrone). Die Fläche folgt dem Straßennetz. Entlang der Autobahn reicht sie weit hinaus, im Hinterland endet sie früher. Die Streamlit-App durchsucht kleinanzeigen.de nach einem Suchbegriff und zeigt nur die Anzeigen, die in dieser Fläche liegen, auf einer Karte und als Liste. Der Suchradius passt sich so an die Frage an, die man beim Suchen eigentlich hat: Wie lange fahre ich hin?

## Voraussetzungen

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- ein kostenloser API-Key für OpenRouteService (Registrierung unter https://openrouteservice.org/dev/#/signup)

## Installation und Start

```sh
uv sync
cp .env.example .env
```

In `.env` den eigenen Key bei `ORS_API_KEY` eintragen. Danach die App starten:

```sh
uv run streamlit run src/smartsearchradius/app.py
```

In der Seitenleiste stehen Start-PLZ, Fahrzeit (5 bis 60 Minuten), Verkehrsmittel, Suchbegriff und der Über-Fetch-Radius (10 bis 200 km). Der Über-Fetch-Radius sollte größer sein als die Strecke, die man in der gewählten Zeit auf der Autobahn schafft, sonst fehlen genau die gut erreichbaren Anzeigen schon in der Rohmenge. Dazu kommen optionale Filter, die direkt in der Kleinanzeigen-Suche wirken: Preis, privat oder gewerblich, Angebot oder Gesuch, nur mit Versand und Kategorie-ID.

## Funktionsweise

1. **plz_lookup.py** löst die Start-PLZ offline über `data/plz_centroids.csv` in Koordinaten auf.
2. **isochrone.py** holt bei OpenRouteService das Polygon der erreichbaren Fläche (Isochrone) für Fahrzeit und Verkehrsmittel (`driving-car` oder `cycling-regular`). **cache.py** legt jede Isochrone in `cache.duckdb` ab, damit eine Wiederholung mit gleichem Startpunkt, gleicher Fahrzeit und gleichem Verkehrsmittel kein ORS-Kontingent verbraucht.
3. **scraper.py** fragt die Kleinanzeigen-Suche mit Über-Fetch-Radius und Filtern ab und liest bis zu 5 Ergebnisseiten aus. Der Radius sollte großzügig gewählt sein, weil er nur die Rohmenge eingrenzt.
4. **matcher.py** löst die PLZ jeder Anzeige in Koordinaten auf und prüft, ob der Punkt im Polygon liegt.
5. **app.py** zeigt Startpunkt, Isochrone und Treffer auf einer folium-Karte und listet die Treffer darunter.

Eine ORS-Anfrage bekommt 60 Sekunden Zeit. Bricht die Verbindung ab, versucht `isochrone.py` es ein zweites Mal und meldet danach einen Fehler in der App (`ORS_TIMEOUT_SECONDS` und `ORS_ATTEMPTS` in `isochrone.py`).

`cache.duckdb` und die WAL-Datei `cache.duckdb.wal`, die DuckDB beim Schreiben daneben anlegt, bleiben lokal und stehen in `.gitignore`. Wer `cache.duckdb` löscht, leert den Cache. Die nächste Suche legt die Datei neu an.

## Einschränkungen

- OpenRouteService begrenzt Isochronen auf 60 Minuten. `isochrone.py` lehnt längere Fahrzeiten ab, der Regler endet bei 60.
- Anzeigen, deren PLZ sich nicht auflösen lässt, fehlen auf der Karte. Die App listet sie separat in einem aufklappbaren Bereich.
- Jede Anzeige wird am Mittelpunkt ihrer PLZ verortet. Liegt dieser Punkt nahe am Rand der Isochrone, kann die tatsächliche Adresse auf der anderen Seite liegen.
- Der Scraper liest das HTML von kleinanzeigen.de aus. Ändert Kleinanzeigen das Markup, liefert die Suche Fehler oder keine Treffer mehr, und die Selektoren in `scraper.py` müssen angepasst werden.
- Die Verbindung zu kleinanzeigen.de funktioniert, liefert aber nicht verlässlich dieselben Ergebnisse wie die Kleinanzeigen-App oder die Website bei gleicher Suche. Die angezeigten Artikel können deshalb von denen in der App abweichen, einzelne Anzeigen fehlen oder kommen hinzu. Dazu trägt auch bei, dass der Scraper höchstens 5 Ergebnisseiten ausliest.
- `cache.duckdb` und die CSV werden relativ zum Repo-Checkout aufgelöst (`Path(__file__).resolve().parents[2]` in `cache.py` und `plz_lookup.py`). Die App deshalb aus einem Checkout starten. Als installiertes Paket findet sie diese Dateien nicht.

## Hinweis

Dies ist ein privates Hobbyprojekt. Es steht in keiner Verbindung zu Kleinanzeigen (kleinanzeigen.de) und wird von dort weder unterstützt noch gebilligt. Automatisierter Zugriff kann gegen die Nutzungsbedingungen von Kleinanzeigen verstoßen. Die Nutzung erfolgt auf eigenes Risiko und ist nur für den persönlichen Gebrauch mit wenigen Anfragen gedacht. Der Scraper wartet 1,5 Sekunden zwischen zwei Ergebnisseiten (`REQUEST_DELAY_SECONDS` in `scraper.py`).

## Daten und Lizenz

- **Code:** MIT, siehe [LICENSE](LICENSE).
- **PLZ-Daten** (`data/plz_centroids.csv`): © [GeoNames](https://www.geonames.org) unter [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), siehe [data/README.md](data/README.md).
