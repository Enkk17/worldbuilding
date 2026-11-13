# Diario lavori — completamento M6 e avvio M7

**Progetto:** `K:\WORLDWEAVE-10`  
**Data del resoconto:** 12 novembre 2026  
**Stato:** M6 implementata nel codice, ma gate database/deployment non verificato; M7 avviata e ancora incompleta. M8 e M9 non avviate.

> **Aggiornamento successivo (13 novembre 2026): M6–M9 completate e verificate.**
>
> Il presente documento è mantenuto come cronaca storica del passaggio precedente. Gli esiti finali sono:
>
> - **M7** completata: migrazione `0006_search_m7` con indici GIN di espressione (`coalesce`/`||` su `::text`, immutabili) al posto di `concat_ws` (`STABLE`, non indicizzabile); query di servizio allineata all'indice e verificata con `EXPLAIN` (`ix_entities_search_fts`); UI command palette Ctrl/⌘K; `backend/tests/test_search.py` verde.
> - **M8** completata: migrazione `0007_import_export_m8`; bundle ZIP portabili con `manifest.json`, `universe.json`, indici JSON, Markdown per record, asset e `checksums.sha256`; validazione (versione schema, checksum, sicurezza dei percorsi, integrità dei riferimenti) ed esecuzione con politica di conflitto; `backend/tests/test_import_export.py` verde.
> - **M9** completata e verificata: `backend/tests/test_release_e2e.py` (dieci scenari) e `backend/tests/test_security_audit.py` (18 test) verdi; suite backend completa **115 passed**; convergenza realtime e durabilità al riavvio verificate su server `uvicorn` reale con PostgreSQL; drill backup/restore eseguito su PostgreSQL (`pg_dump -Fc`, azzeramento, `pg_restore --exit-on-error`, verifica integrità via API); script operativi estesi al volume media con sidecar SHA-256; build web di produzione e typecheck verdi; migrazione da database pulito con indici FTS presenti; documentazione sincronizzata.
> - **Gate operativi residui:** conferma della CI GitHub Actions al prossimo push e drill clean start/stop/backup/restore su host Windows con Docker Desktop.
>
> Evidenze dettagliate in `docs/MILESTONE_ACCEPTANCE.md`; stato per modulo in `docs/IMPLEMENTATION_STATUS.md`.


## Richiesta e ambito

La richiesta era completare M6, eseguire i test opportuni e poi procedere fino alla milestone 9. Il lavoro effettivamente svolto in questo passaggio ha completato funzionalità e verifiche automatiche M6, avviato una prima implementazione backend M7 e ripetuto la suite/typecheck/build. Non è corretto dichiarare concluse le milestone M6–M9: restano gate, implementazione e verifiche elencate sotto.

## M6 — Atlas e Chronos

### Implementato

- Aggiunta la UI `artifacts/worldweave/src/pages/AtlasChronos.tsx` e collegata alla pagina universo con nuove schede **Atlas** e **Chronos** in `UniverseDetail.tsx`.
- Atlas ora offre selezione/creazione mappe, upload di sfondi, visualizzazione dei marker e delle regioni, creazione marker sul canvas, modifica del nome e drag per spostare marker, eliminazione, disegno di poligoni, zoom e pan. Le coordinate persistite sono normalizzate nell’intervallo `[0,1]`, indipendenti dalla dimensione della viewport.
- Chronos ora offre selezione/creazione calendari con mesi personalizzati, regola bisestile configurabile, creazione ere, registrazione e filtro di eventi, visualizzazione grafica della timeline e precisioni data giorno/mese/anno/intervallo/approssimata.
- Aggiunte le API di update e delete delle regioni cartografiche con controllo versione ottimistico e registrazione audit/activity.
- Aggiunte regole bisestili al modello calendario e all’engine: giorni intercalari per anno/mese, date esatte, intervalli e finestre di incertezza.
- Portati a `BigInteger`/`BIGINT` gli indici temporali di ere ed eventi, con adeguamento della migrazione `0005_atlas_chronos_m6.py`, per evitare overflow nei calendari di lungo periodo.
- Riparato il contratto OpenAPI M6: erano referenziati schemi e parametri Atlas/Chronos non definiti; dopo la correzione il codegen Orval genera i client React Query e gli schemi Zod.
- Risolti due problemi del codegen emersi con le nuove definizioni: supporto DOM (`Blob`/`File`) nella compilazione Zod e collisione degli export dei parametri generati.
- File principali: `backend/modules/atlas/{schemas.py,service.py,router.py}`, `backend/modules/chronos/{schemas.py,calendar_engine.py}`, `backend/core/models.py`, `backend/migrations/versions/0005_atlas_chronos_m6.py`, `lib/api-spec/openapi.yaml`, client generati, `artifacts/worldweave/src/pages/AtlasChronos.tsx` e `UniverseDetail.tsx`.

### Test M6 aggiunti

`backend/tests/test_atlas_chronos.py` contiene test per mappe, marker e regioni; coordinate fuori limite; aggiornamento concorrente; asset PNG, checksum e download con isolamento; regole bisestili, date e range; immutabilità delle regole dopo la creazione di eventi; indici temporali oltre int32 e contratto OpenAPI.

### Verifiche M6 svolte

- Suite backend completa: **70 passed** (`uv run --locked python -m pytest -q`).
- Typecheck pnpm: **passato** (`pnpm run typecheck`).
- Build web produzione: **passata** (`PORT=24452 BASE_PATH=/ pnpm --filter @workspace/worldweave run build`).
- Codegen API/Zod Orval: **passato**, seguito da typecheck librerie.
- I test usano SQLite in memoria. **Non è stata verificata l’applicazione della migrazione M6 a PostgreSQL**, né è stata eseguita la prova operativa end-to-end contro Docker.

## M7 — Full-text Search (lavoro parziale)

### Implementato finora

- Creato il modulo backend `backend/modules/search/` con endpoint `GET /api/v1/universes/{universe_id}/search`.
- La query aggrega risultati Codex (entità), Chronicle (documenti) e Chronos (eventi), con filtri per tipo, paginazione, ordinamento per pertinenza/timestamp, snippet e offset di evidenziazione.
- Applicati i controlli membership e le regole di visibilità per entità e documenti; query limitata ai record del solo universo richiesto. Validati lunghezza query, tipi ammessi e caratteri jolly SQL.
- Implementato un percorso PostgreSQL con `to_tsvector('simple')`/`plainto_tsquery` e fallback `ILIKE` per SQLite.
- Registrato il router in `backend/main.py`.
- Aggiunti `backend/tests/test_search.py` per i tre tipi di risorsa, filtro/paginazione, isolamento/visibilità e validazione.

### Cosa manca per completare M7

- Indici `tsvector` PostgreSQL persistenti e loro migrazione: al momento il percorso Postgres calcola `to_tsvector` nella query e **non** usa ancora colonne/indici full-text dedicati.
- Contratto OpenAPI, rigenerazione client e tipi Zod per la ricerca.
- UI ricerca: command palette Ctrl/Cmd+K, pagina/overlay risultati, filtri, navigazione dai risultati e test frontend/E2E.
- Verifica PostgreSQL reale della query FTS, explain/performance e suite completa dopo la migrazione.
- I tre test M7 passano ora assieme ai test Atlas/Chronos.

## Verifiche aggiornate

Eseguite dopo la correzione della regressione SQLite dovuta a un tentativo intermedio di aggiungere colonne full-text generate nel modello ORM:

- `uv run --locked python -m pytest -q`: **70 passed, 4 warning**. I warning riguardano deprecazione Starlette/httpx e nomi `schema_json` nei modelli Pydantic Codex.
- `pnpm run typecheck`: **passato** per librerie e workspace frontend.
- `PORT=24452 BASE_PATH=/ pnpm --filter @workspace/worldweave run build`: **passato**. Vite mostra warning non bloccanti sul `base`, sourcemap di alcuni componenti UI e chunk JS maggiore di 500 kB.
- Codegen Orval: eseguito e passato per i contratti presenti nel file OpenAPI. L’endpoint M7 non è ancora inserito in OpenAPI, quindi il client generato non contiene ancora le sue operazioni.

## Stato dei gate non eseguiti

- **Docker Desktop / PostgreSQL:** il comando `docker version` non riesce a collegarsi al motore `dockerDesktopLinuxEngine`; pertanto non sono state applicate né verificate le migrazioni sul database PostgreSQL.
- **Backup/restore e clean deployment:** drill non eseguito, quindi il gate operativo di release è ancora aperto.
- **E2E browser/accessibilità e test UI interattivi:** non eseguiti; la build non equivale a una prova E2E.
- **M8 Import/Export:** non implementata in questo lavoro.
- **M9 Release hardening:** non completata: mancano M7 e M8, regression E2E completa, audit finale, prova backup/restore, documentazione aggiornata e sign-off.

`uv sync --locked` è stato eseguito durante il lavoro e ha installato la dipendenza `python-multipart` già prevista dal lockfile; i test successivi sono riusciti. Quindi il blocco dei test Python descritto nel primo aggiornamento è stato rimosso.

## Stato del repository

Le modifiche restano non committate nel working tree. Il contenuto non tracciato preesistente `attached_assets/` è stato lasciato intatto e non è incluso in questo resoconto come deliverable.

## Passi consigliati per riprendere

1. Avviare Docker Desktop e applicare tutte le migrazioni a PostgreSQL pulito e a uno stato precedente rappresentativo.
2. Aggiungere migrazione e indici FTS PostgreSQL, testandoli sul database reale.
3. Completare OpenAPI/client e UI M7; eseguire typecheck, build, backend e E2E.
4. Implementare e testare M8 (bundle export/import, validazione dry-run, riferimenti e asset).
5. Eseguire i gate M9: security regression cross-universe, E2E, backup/restore drill, clean deployment, aggiornamento guide e sign-off.
6. Aggiornare `WORLDWEAVE_ROADMAP.md`, `WORLDWEAVE_TASKS.md`, `docs/IMPLEMENTATION_STATUS.md` e `docs/MILESTONE_ACCEPTANCE.md` solo con esiti osservati dei gate.
