# Agentic CV Matching Portal 

Dieses Projekt ist ein agentenbasiertes Rekrutierungs- und Matching-Portal, das speziell beispielweise auf die Anforderungen der Automobilindustrie zugeschnitten ist. 

Das System nutzt **Pydantic AI** zur Steuerung spezialisierter LLM-Sub-Agenten, **FastMCP** (Model Context Protocol) zur Bereitstellung systemnaher Werkzeuge und **MLflow** zur strukturierten Überwachung und Evaluierung der Extraktionsgüte.

---
## Demo
<video src="demo/demo_phase_prod.mp4" controls width="700">
  Your browser does not support the video tag.
</video>
*Demonstration der produktiven Matching-Pipeline (Phase 2).*

<video src="demo/demo_phase_exp.mp4" controls width="700">
  Your browser does not support the video tag.
</video>
*Mlflow Anwendung mit Datensätze, Experimente, Evaluation .*

## Schnellstart über Docker Compose

Die einfachste Methode, um die gesamte Anwendung (Streamlit-Frontend, FastMCP-Server, MLflow-Server und alle Systemabhängigkeiten) auszuführen, ist die Verwendung von Docker. Es müssen keine lokalen Python-Abhängigkeiten manuell installiert werden.

### Voraussetzungen
*   [Docker Desktop](https://www.docker.com/products/docker-desktop/) installiert und aktiv.

### Schritte zur Ausführung:
1.  **Projekt klonen:**
    Das Projekt mit glit clone herunterladen
1.  **Container bauen und starten:**
    Öffnen Sie ein Terminal im Projektordner und führen Sie folgenden Befehl aus:
    ```bash
    docker compose up --build
    ```
2.  **Dienste im Browser öffnen:**
    *   **Streamlit Web-Portal:** [http://localhost:8501](http://localhost:8501)
    *   **MLflow Tracking Dashboard:** [http://localhost:8050](http://localhost:8050)

Um die Container im Hintergrund zu stoppen, drücken Sie `Strg+C` oder führen Sie `docker compose down` aus.


##  Funktionsweise \& System-Szenarien

Das Portal unterstützt zwei isolierte Betriebsmodi, die über die Benutzeroberfläche ausgewählt werden können:

### Szenario A: HR Recruiter Mode
*   **Ziel:** Mehrere Bewerber-Lebensläufe gegen eine einzige Ziel-Stellenausschreibung prüfen.
*   **Ablauf:** Sie fügen die Anforderungen ein (als Text oder URL) und laden ein oder mehrere Lebenslauf-PDFs hoch. Das System extrahiert per Referenz alle Anforderungen und Kompetenzen, führt eine gewichtete Punkteberechnung durch und stellt die Ergebnisse als interaktive Radar-Diagramme und Tabellen dar.

### Szenario B: Job Seeker Mode
*   **Ziel:** Den eigenen Lebenslauf hochladen und passende Positionen live am Markt finden.
*   **Ablauf:** Sie laden Ihren Lebenslauf hoch und geben optionale Suchbegriffe und Ortsfilter an. Die Pipeline extrahiert Ihre Fähigkeiten, sucht über das integrierte Scraper-Modul (*JobSpy*) live auf Jobbörsen nach passenden Inseraten und berechnet eine detaillierte Gap-Analyse.

---

##  Evaluation \& Experimente (MLflow)

Während der lokale oder dockerbasierte Web-Betrieb in **Phase 2** angesiedelt ist, können Sie die Qualität der Extraktionen und die Konvergenz zwischen KI-Entscheidungen und menschlichen HR-Spezialisten in **Phase 1** evaluieren:

1.  Die im Jupyter-Notebook definierten Läufe registrieren strukturierte Ground-Truth-Daten direkt in den MLflow-Tabellen (`eval_datset_job_description`, etc.).
2.  Über benutzerdefinierte Scorer-Funktionen (z. B. `cv_truthfulness_scorer`) wird die inhaltliche Fehlerfreiheit überprüft.
3.  Die Auswertungen und die Übereinstimmungsstatistiken (Konvergenzkurven) können jederzeit unter [http://localhost:8050](http://localhost:8050) eingesehen und verglichen werden.

---
