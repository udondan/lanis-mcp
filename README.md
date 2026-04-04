# lanis-mcp

Ein [MCP-Server](https://modelcontextprotocol.io/) für das **Schulportal Hessen (Lanis)**, der KI-Assistenten wie Claude ermöglicht, direkt auf Schulinformationen zuzugreifen – Vertretungsplan, Kalender, Hausaufgaben, Nachrichten und mehr.

---

## Was ist lanis-mcp?

`lanis-mcp` verbindet deine KI (z. B. Claude) mit dem [Schulportal Hessen](https://start.schulportal.hessen.de/). Sobald der Server eingerichtet ist, kannst du deiner KI ganz natürlich Fragen stellen wie:

> „Was steht heute im Vertretungsplan?"
> „Welche Hausaufgaben habe ich diese Woche?"
> „Zeig mir alle Termine im April."

Der Server kommuniziert über das standardisierte MCP-Protokoll und ist **ausschließlich lesend** – er verändert keine Daten im Schulportal.

---

## Voraussetzungen

- Ein aktiver **Lanis-Account** (Schulportal Hessen)
- Die **Schul-ID** deiner Schule (siehe [Schul-ID herausfinden](#schul-id-herausfinden))
- [`uv`](https://docs.astral.sh/uv/) installiert (modernes Python-Paketverwaltungstool)
- Ein MCP-kompatibler Client, z. B. [Claude Desktop](https://claude.ai/download)

---

## Einrichtung

### Schul-ID herausfinden

Falls du deine Schul-ID nicht kennst, kannst du sie über das Tool `get_schools` ermitteln. Frage deine KI einfach:

> „Suche die Schul-ID für die [Name deiner Schule] in [Stadt]."

Das Tool `get_schools` benötigt **keine Anmeldung** und listet alle Schulen im Schulportal Hessen mit ihrer ID auf.

### Claude Desktop konfigurieren

Öffne die Konfigurationsdatei von Claude Desktop:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Füge einen Eintrag unter `mcpServers` hinzu. Wähle einen der drei Authentifizierungsmodi:

#### Modus 1 – Benutzername & Passwort (empfohlen)

```json
{
  "mcpServers": {
    "lanis": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/udondan/lanis-mcp", "lanis-mcp"],
      "env": {
        "LANIS_SCHOOL_ID": "1234",
        "LANIS_USERNAME": "vorname.nachname",
        "LANIS_PASSWORD": "dein-passwort"
      }
    }
  }
}
```

#### Modus 2 – Session-Cookie (schneller, kein Passwort)

```json
{
  "mcpServers": {
    "lanis": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/udondan/lanis-mcp", "lanis-mcp"],
      "env": {
        "LANIS_SCHOOL_ID": "1234",
        "LANIS_SESSION_ID": "dein-session-cookie"
      }
    }
  }
}
```

> **Hinweis:** Der Session-Cookie läuft nach einiger Zeit ab. Bei Ablauf gibt der Server eine entsprechende Fehlermeldung zurück – einfach die Anfrage wiederholen oder auf Modus 1 wechseln.

#### Modus 3 – Schule nach Name & Stadt

```json
{
  "mcpServers": {
    "lanis": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/udondan/lanis-mcp", "lanis-mcp"],
      "env": {
        "LANIS_SCHOOL_NAME": "Mustergymnasium",
        "LANIS_SCHOOL_CITY": "Musterstadt",
        "LANIS_USERNAME": "vorname.nachname",
        "LANIS_PASSWORD": "dein-passwort"
      }
    }
  }
}
```

Nach dem Speichern Claude Desktop neu starten.

---

## Docker MCP

### Docker-Image bauen und registrieren

Voraussetzung: [`mise`](https://mise.jdx.dev) installiert.

```bash
# Nur bauen
mise run docker-build

# Nur im Docker MCP Katalog registrieren
mise run docker-register

# Beides nacheinander
mise run docker
```

---

## Verfügbare Tools

Alle Tools sind **nur lesend** und verändern keine Daten. Die meisten Tools unterstützen die Ausgabeformate `markdown` (Standard, für Menschen lesbar) und `json` (maschinenlesbar).

### Einrichtung

| Tool                     | Beschreibung                                                         | Auth erforderlich |
| ------------------------ | -------------------------------------------------------------------- | :---------------: |
| `get_schools`            | Listet alle Schulen im Schulportal Hessen mit ID, Name und Stadt     |        ❌         |
| `get_available_apps`     | Zeigt, welche der unterstützten Apps an deiner Schule verfügbar sind |        ✅         |
| `check_app_availability` | Prüft, ob eine bestimmte App an deiner Schule verfügbar ist          |        ✅         |

### Stundenplan & Unterricht

| Tool                    | Beschreibung                                                        | Parameter | Auth erforderlich |
| ----------------------- | ------------------------------------------------------------------- | --------- | :---------------: |
| `get_substitution_plan` | Heutiger Vertretungsplan (Klasse, Fach, Raum, Lehrer, Hinweise)     | –         |        ✅         |
| `get_timetable`         | Wöchentlicher Stundenplan (Fach, Raum, Lehrer je Stunde und Tag)    | –         |        ✅         |
| `get_learning_groups`   | Lerngruppen/Kurse, in denen du eingeschrieben bist, inkl. Lehrkraft | –         |        ✅         |

### Kalender

| Tool                    | Beschreibung                                     | Parameter                                          | Auth erforderlich |
| ----------------------- | ------------------------------------------------ | -------------------------------------------------- | :---------------: |
| `get_calendar`          | Schulkalender für einen beliebigen Zeitraum      | `start`, `end` (JJJJ-MM-TT), `include_responsible` |        ✅         |
| `get_calendar_of_month` | Schulkalender für den aktuellen Monat (Kurzform) | `include_responsible`                              |        ✅         |

> **Hinweis zu `include_responsible`:** Wenn `true`, wird für jeden Termin eine zusätzliche API-Anfrage gestellt. Bei vielen Terminen kann dies langsam sein.

### Hausaufgaben & Aufgaben

| Tool        | Beschreibung                                                                          | Auth erforderlich |
| ----------- | ------------------------------------------------------------------------------------- | :---------------: |
| `get_tasks` | Aufgaben und Hausaufgaben aus „Mein Unterricht" (Fach, Lehrer, Beschreibung, Anhänge) |        ✅         |

### Nachrichten

| Tool                | Beschreibung                              | Parameter                            | Auth erforderlich |
| ------------------- | ----------------------------------------- | ------------------------------------ | :---------------: |
| `get_conversations` | Nachrichten aus dem „Nachrichten"-Bereich | `number` (Standard: 10, `-1` = alle) |        ✅         |

> **Hinweis:** `-1` lädt alle Nachrichten und kann den Lanis-Server stark belasten. Bitte sparsam verwenden.

### Dateien

| Tool                    | Beschreibung                                                                | Parameter                               | Auth erforderlich |
| ----------------------- | --------------------------------------------------------------------------- | --------------------------------------- | :---------------: |
| `get_file_storage`      | Inhalt des Schulischen Dateispeichers (Ordner & Dateien mit Download-Links) | `folder_id` (optional, für Unterordner) |        ✅         |
| `get_file_distribution` | Verteilte Dateien und Ankündigungen (Dateiverteilung / GRB Infos)           | –                                       |        ✅         |

### Portal

| Tool          | Beschreibung                                                     | Auth erforderlich |
| ------------- | ---------------------------------------------------------------- | :---------------: |
| `get_apps`    | Alle App-Kacheln auf dem Lanis-Dashboard (Name, Link, Kategorie) |        ✅         |
| `get_folders` | Ordner/Kategorien auf dem Lanis-Dashboard                        |        ✅         |
| `get_votes`   | Aktive Abstimmungen und Wahlen (z. B. Schülerratswahl)           |        ✅         |

---

## Beispiele

Hier sind typische Fragen, die du deiner KI stellen kannst:

### Einrichtung & Überblick

```
Welche Schul-ID hat das Gymnasium Musterstadt?
```

```
Welche Lanis-Apps sind an meiner Schule verfügbar?
```

### Stundenplan & Vertretung

```
Was steht heute im Vertretungsplan?
```

```
Zeig mir meinen Stundenplan für diese Woche.
```

```
In welchen Kursen bin ich eingeschrieben und wer sind meine Lehrkräfte?
```

```
Wer vertritt heute Herrn Müller in der 3. Stunde?
```

### Kalender

```
Welche Schultermine gibt es im April?
```

```
Zeig mir alle Termine zwischen dem 1. und 15. März.
```

```
Was sind die nächsten Schulveranstaltungen diesen Monat?
```

### Hausaufgaben & Aufgaben

```
Welche Hausaufgaben habe ich aktuell?
```

```
Gibt es Aufgaben mit Anhängen, die ich herunterladen kann?
```

```
Was muss ich für Mathematik vorbereiten?
```

### Nachrichten

```
Zeig mir meine letzten 5 Nachrichten.
```

```
Habe ich ungelesene Nachrichten?
```

```
Was hat die Schule zuletzt kommuniziert?
```

### Dateien

```
Was liegt im Schulischen Dateispeicher?
```

```
Gibt es neue verteilte Dateien oder Ankündigungen?
```

---

## Ausgabeformate

Die meisten Tools unterstützen zwei Ausgabeformate:

- **`markdown`** (Standard): Für Menschen lesbar, ideal für die direkte Anzeige in der KI-Konversation
- **`json`**: Maschinenlesbar, nützlich wenn du die Daten weiterverarbeiten möchtest

Du kannst das Format in deiner Anfrage angeben:

```
Zeig mir den Vertretungsplan als JSON.
```

> **Hinweis:** Antworten sind auf **25.000 Zeichen** begrenzt. Bei sehr langen Ergebnissen wird die Ausgabe gekürzt und ein Hinweis angezeigt. Verwende in diesem Fall Filter (z. B. einen engeren Datumsbereich beim Kalender), um die Ergebnisse einzugrenzen.

---

## Fehlerbehebung

### „Session abgelaufen" / Session expired

Der Session-Cookie ist abgelaufen (nur bei Modus 2 relevant). Der Server setzt die Verbindung automatisch zurück. Einfach die Anfrage erneut stellen – beim nächsten Versuch wird eine neue Session aufgebaut.

### „App nicht verfügbar an deiner Schule"

Nicht alle Schulen haben alle Lanis-Module aktiviert. Mit `get_available_apps` kannst du prüfen, welche der unterstützten Apps an deiner Schule freigeschaltet sind.

### Kein Vertretungsplan verfügbar

Der Vertretungsplan ist nur an Schultagen verfügbar. An Wochenenden und Feiertagen gibt es keinen Plan.

### Keine Termine / Aufgaben gefunden

Prüfe, ob du den richtigen Zeitraum angegeben hast. Für den Kalender müssen `start` und `end` im Format `JJJJ-MM-TT` angegeben werden.

### Verbindungsfehler

Stelle sicher, dass die Umgebungsvariablen in der Claude Desktop Konfiguration korrekt gesetzt sind und dass du Zugang zum Schulportal Hessen hast (ggf. VPN oder Schulnetzwerk erforderlich).
