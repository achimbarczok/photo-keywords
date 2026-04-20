# Requirements Document

## Einleitung

Dieses Dokument beschreibt die Anforderungen für eine Antwort-Validierung mit automatischem Retry-Mechanismus im Lightroom Ollama Keyword Generator. Das Problem: Ollama-Vision-Modelle liefern manchmal statt einer komma-getrennten Stichwortliste erklärende Texte, Ablehnungen oder ganze Sätze (z.B. "Ich kann dieses Foto nicht analysieren, da es sich um eine Fossilienpräparation handelt" statt "Fossil, Präparat, Museum, Naturkunde"). Die Validierung erkennt solche ungültigen Antworten anhand konfigurierbarer Heuristiken und wiederholt die Anfrage automatisch mit einem verstärkten Prompt, bis eine gültige Stichwortliste vorliegt oder die maximale Retry-Anzahl erreicht ist.

## Glossar

- **Antwort_Validator**: Die Komponente, die eine geparste Ollama-Antwort (Liste von Strings) daraufhin prüft, ob sie eine gültige Stichwortliste darstellt oder eine ungültige Antwort (Satz, Erklärung, Ablehnung) ist.
- **Validierungs_Ergebnis**: Das Ergebnis einer Validierungsprüfung, bestehend aus einem Boolean (gültig/ungültig) und einer Begründung bei Ungültigkeit.
- **Retry_Prompt**: Ein verstärkter/klarerer Prompt, der bei fehlgeschlagener Validierung anstelle des ursprünglichen Prompts verwendet wird, um das Modell zu einer korrekten Stichwortliste zu bewegen.
- **Max_Retries**: Die konfigurierbare maximale Anzahl von Wiederholungsversuchen bei ungültiger Antwort.
- **Ablehnungs_Phrase**: Ein vordefinierter Textbaustein, der auf eine Verweigerung des Modells hindeutet (z.B. "Ich kann nicht", "I cannot", "I'm sorry").
- **Durchschnittliche_Wortanzahl**: Die mittlere Anzahl von Wörtern pro Eintrag in der geparsten Stichwortliste, als Heuristik zur Erkennung von Sätzen statt Stichwörtern.
- **Ollama_Client**: Die bestehende Komponente, die mit der lokalen Ollama-Instanz kommuniziert und Bildanalyse-Anfragen sendet.
- **KlassifikationsRouter**: Die bestehende Komponente, die den Zwei-Stufen-Prozess (Klassifikation → spezialisierte Stichwort-Generierung) orchestriert.
- **BatchProcessor**: Die bestehende Komponente, die die Batch-Verarbeitung von Fotos orchestriert.

## Anforderungen

### Anforderung 1: Antwort-Validierung

**User Story:** Als Fotograf möchte ich, dass ungültige Modellantworten (Sätze, Erklärungen, Ablehnungen) automatisch erkannt werden, damit nur echte Stichwortlisten als Ergebnis akzeptiert werden.

#### Akzeptanzkriterien

1. WHEN der Ollama_Client eine geparste Antwort (Liste von Strings) erhält, THE Antwort_Validator SHALL prüfen, ob die Antwort eine gültige Stichwortliste darstellt.
2. THE Antwort_Validator SHALL eine Antwort als ungültig bewerten, WHEN die Durchschnittliche_Wortanzahl pro Eintrag einen konfigurierbaren Schwellenwert überschreitet (Standard: 3 Wörter).
3. THE Antwort_Validator SHALL eine Antwort als ungültig bewerten, WHEN ein Eintrag eine bekannte Ablehnungs_Phrase enthält.
4. THE Antwort_Validator SHALL eine Antwort als ungültig bewerten, WHEN die Antwort aus genau einem Eintrag besteht, der mehr Wörter als der konfigurierbare Schwellenwert für Einzeleinträge enthält (Standard: 4 Wörter).
5. THE Antwort_Validator SHALL ein Validierungs_Ergebnis zurückgeben, das den Gültigkeitsstatus und bei Ungültigkeit eine Begründung enthält.
6. THE Antwort_Validator SHALL eine leere Antwortliste als ungültig bewerten.
7. FOR ALL gültigen Stichwortlisten (kurze, komma-getrennte Begriffe ohne Ablehnungsphrasen), THE Antwort_Validator SHALL die Antwort als gültig bewerten.

### Anforderung 2: Automatischer Retry-Mechanismus

**User Story:** Als Fotograf möchte ich, dass bei einer ungültigen Modellantwort automatisch ein erneuter Versuch mit einem verstärkten Prompt gestartet wird, damit ich möglichst immer verwertbare Stichwörter erhalte.

#### Akzeptanzkriterien

1. WHEN der Antwort_Validator eine Antwort als ungültig bewertet, THE Ollama_Client SHALL die Anfrage automatisch mit dem Retry_Prompt wiederholen.
2. THE Ollama_Client SHALL die Anzahl der Wiederholungsversuche auf den konfigurierten Max_Retries-Wert begrenzen (Standard: 2).
3. WHEN die maximale Retry-Anzahl erreicht ist und die Antwort weiterhin ungültig ist, THE Ollama_Client SHALL die letzte erhaltene Antwort zurückgeben.
4. THE Ollama_Client SHALL bei jedem Retry den Retry_Prompt verwenden, der das Modell explizit anweist, ausschließlich eine komma-getrennte Stichwortliste ohne Erklärungen zurückzugeben.
5. THE Ollama_Client SHALL den Retry_Prompt als konfigurierbaren Parameter unterstützen, mit einem sinnvollen Standardwert.

### Anforderung 3: Protokollierung von Retries

**User Story:** Als Fotograf möchte ich nachvollziehen können, wann und warum Retries stattgefunden haben, damit ich die Qualität meiner Prompt-Konfiguration beurteilen kann.

#### Akzeptanzkriterien

1. WHEN ein Retry ausgelöst wird, THE Ollama_Client SHALL den Bildpfad, die Retry-Nummer, die Begründung der Ungültigkeit und den verwendeten Prompt-Typ in die Logdatei schreiben.
2. WHEN alle Retries erschöpft sind und die Antwort weiterhin ungültig ist, THE Ollama_Client SHALL eine Warnung protokollieren, die den Bildpfad und die Anzahl der durchgeführten Retries enthält.
3. WHEN ein Retry zu einer gültigen Antwort führt, THE Ollama_Client SHALL protokollieren, dass der Retry erfolgreich war, einschließlich der Retry-Nummer.

### Anforderung 4: Integration in BatchProcessor und KlassifikationsRouter

**User Story:** Als Fotograf möchte ich, dass die Antwort-Validierung sowohl im normalen Batch-Modus als auch im Klassifikations-Modus funktioniert, damit alle Verarbeitungswege von der Qualitätssicherung profitieren.

#### Akzeptanzkriterien

1. WHEN der BatchProcessor den Ollama_Client zur Bildanalyse verwendet, THE Ollama_Client SHALL die Antwort-Validierung und den Retry-Mechanismus automatisch anwenden.
2. WHEN der KlassifikationsRouter den Ollama_Client zur Stichwort-Generierung verwendet, THE Ollama_Client SHALL die Antwort-Validierung und den Retry-Mechanismus automatisch anwenden.
3. THE Antwort-Validierung SHALL transparent für BatchProcessor und KlassifikationsRouter ablaufen, ohne dass diese Komponenten angepasst werden müssen.

### Anforderung 5: Konfiguration der Validierung

**User Story:** Als Fotograf möchte ich die Validierungsparameter anpassen können, damit ich die Heuristiken an verschiedene Modelle und Sprachen anpassen kann.

#### Akzeptanzkriterien

1. THE Keyword_Generator SHALL folgende Validierungsparameter über die Konfiguration unterstützen: Max_Retries, Schwellenwert für Durchschnittliche_Wortanzahl, Schwellenwert für Einzeleintrag-Wortanzahl und Retry_Prompt.
2. THE Keyword_Generator SHALL sinnvolle Standardwerte für alle Validierungsparameter bereitstellen (Max_Retries: 2, Durchschnittliche_Wortanzahl: 3, Einzeleintrag-Wortanzahl: 4).
3. WHEN kein Retry_Prompt konfiguriert ist, THE Keyword_Generator SHALL einen Standardwert verwenden, der das Modell anweist, ausschließlich komma-getrennte Stichwörter ohne Erklärungen zu liefern.

### Anforderung 6: Ablehnungs-Erkennung

**User Story:** Als Fotograf möchte ich, dass typische Ablehnungsantworten des Modells zuverlässig erkannt werden, damit diese nicht als Stichwörter übernommen werden.

#### Akzeptanzkriterien

1. THE Antwort_Validator SHALL eine vordefinierte Liste von Ablehnungs_Phrasen enthalten, die sowohl deutsche als auch englische Formulierungen abdeckt.
2. THE Antwort_Validator SHALL die Ablehnungs-Erkennung case-insensitiv durchführen.
3. THE Antwort_Validator SHALL mindestens folgende Ablehnungs_Phrasen erkennen: "ich kann nicht", "ich kann das nicht", "i cannot", "i can't", "i'm sorry", "es tut mir leid", "nicht möglich", "unable to".
4. THE Antwort_Validator SHALL eine Antwort als ungültig bewerten, WHEN ein beliebiger Eintrag der Stichwortliste eine Ablehnungs_Phrase als Teilstring enthält.
