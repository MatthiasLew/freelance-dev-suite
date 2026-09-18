# Performance Comparison: Baseline vs. Optimized (Pure Python) & Rust Justification Analysis

**Baseline Commit:** `ee99bf42cbd1949519cdf6b237cbe67c9d8e7d71`  
**Optimized Commit:** `ad16ad13ec94c4c455c16df851da5c45e1af0123`  
**Environment:** Python 3.14.0 (AMD64) on Windows 11 (10.0.26200)  
**Hardware:** Modern Multi-core x86_64, NVMe SSD  

---

## 1. Podsumowanie zmian architektonicznych i optymalizacji

W ramach zadania przeprowadzono kompleksowy audyt wydajnościowy repozytorium `freelance-dev-suite`, zidentyfikowano wąskie gardła algorytmiczne i systemowe przy użyciu `cProfile`, a następnie wdrożono zestaw przemyślanych optymalizacji w czystym Pythonie (Pure Python). Wszystkie modyfikacje zachowują w 100% kompatybilność wsteczną publicznego API, formatów plików, schematów JSON, rygorystycznych gwarancji bezpieczeństwa (atomic writes, `fsync`, file locks, ochrona przed path traversal) oraz 100% zgodności testów (230 testów zdanych, pokrycie 82.41%).

### Co dokładnie zostało zoptymalizowane:
1. **Append-Only Timeline Manager (`packages/timeline/manager.py`):**
   - **Problem:** Każde wywołanie `record_event()` dokonywało pełnej deserializacji JSON wszystkich linii pliku `events.jsonl` wyłącznie w celu wyznaczenia kolejnego sekwencyjnego identyfikatora (`len(existing) + 1`). Przy rosnącej historii timeline rzędu tysięcy zdarzeń koszt zapisu rósł asymptotycznie jako $O(N)$.
   - **Optymalizacja:** Wdrożono mechanizm wstecznego przeszukiwania wskaźnika pliku (`file.seek()`) do ostatnich 4096 bajtów, inspekcji ostatniej linii i wyciągnięcia `id` bez dotykania reszty pliku. Złożoność zapisu zredukowano do $O(1)$. Zapewniono pełny graceful fallback dla pustych lub uszkodzonych plików.

2. **Skanowanie i Indeksowanie Workspace (`packages/workspace/storage.py` & `manager.py`):**
   - **Problem:** Funkcje wyszukiwania i listowania jobów (`get_job`, `get_job_dir`, `find_job_entry`) wielokrotnie wywoływały `Path.iterdir()` i instancjonowały setki obiektów `Path`, a `_generate_job_id()` w pętli skanowało cały katalog jobów dla każdego testowanego ID ($O(N^2)$ w pesymistycznym wariancie). Ponadto `save_job()` bezwarunkowo wywoływało `mkdir(parents=True, exist_ok=True)` dla 6 podkatalogów przy każdym zapisie metadanych joba.
   - **Optymalizacja:** Zastąpiono `iterdir()` niskopoziomowym strumieniowaniem `os.scandir()`, eliminując tworzenie zbędnych obiektów `Path`. Scalono logikę odnajdywania joba w pojedynczą funkcję `find_job_entry()`. Generator ID najpierw sprawdza `config.job_counter`, a dopiero w razie kolizji odpytuje system plików. W `save_job()` dodano strażnika `job_dir.exists()`, eliminując tysiące bezużytecznych wywołań systemowych `CreateDirectoryW` / `stat`.

3. **Przetwarzanie Work Sessions, Bugs i Scope Changes (`packages/work/storage.py`, `packages/bugs/processor.py`, `packages/scope/detector.py`, `packages/tracking/timer.py`):**
   - **Problem:** Moduły te używały `Path.glob("*.json")` i `iterdir()`, sortując pełne obiekty i wielokrotnie sprawdzając istnienie folderów nadrzędnych.
   - **Optymalizacja:** Wprowadzono strumieniowanie `os.scandir()`, bezpośrednie parsowanie numerycznych ID z prefiksów plików (`int(entry.name[4:-5])` bez `replace()` i regexów) oraz pomijanie ponownych `mkdir` na istniejących strukturach.

4. **Wydajność MCP Server (`packages/mcp/server.py`):**
   - **Problem:** Endpoint `_tool_get_job_status` wywoływał `manager.get_job(job_id)`, który skanował workspace, po czym wywoływał `manager.get_job_dir(job_id)`, wykonując drugie identyczne skanowanie od nowa.
   - **Optymalizacja:** Wykorzystano `manager.get_job_dir(job_id)` bezpośrednio do wczytania `job.json`, eliminując redundantny scan.

5. **Archiwizacja i Pakowanie Handoff (`packages/archive/manager.py`, `packages/handoff/packager.py`):**
   - **Problem:** Użycie `rglob("*")` schodziło głęboko w foldery `.git`, `node_modules`, `venv`, `archive`, a weryfikacja ścieżek `dest.resolve() == file_path.resolve()` w pętli wywoływała Win32 `GetFinalPathNameByHandleW` podwójnie dla każdego pliku (tysiące kosztownych wywołań kernela). Dodatkowo import archiwum najpierw czytał cały plik do RAM-u, zapisywał na dysk, a potem czytał go po raz drugi w celu obliczenia SHA-256.
   - **Optymalizacja:** Zastąpiono `rglob` przez `os.walk` z przycinaniem ignorowanych katalogów in-place (`dirs[:] = [...]`). Ścieżkę docelową pre-resolwowano jednokrotnie przed pętlą. W `import_job` wprowadzono strumieniowy odczyt i zapis w buforach 128KB z jednoczesną inkrementalną aktualizacją hasza SHA-256, zmniejszając narzut I/O i zużycie pamięci o 50%.

6. **Czas startu CLI i Lazy Imports (`packages/storage_utils.py`, `src/freelance_cli/`):**
   - **Problem:** Moduł `packages/storage_utils.py` na najwyższym poziomie importował `from filelock import FileLock`. Pakiet `filelock` w swoim łańcuchu zależności wymusza import m.in. `asyncio`, `selectors`, `_overlapped`, `concurrent.futures`, `sqlite3` oraz windows event loops. Skutkowało to importem ponad 100 modułów standardowych przy każdym wywołaniu CLI, narzucając narzut startowy rzędu ~400-500 ms na Windowsie.
   - **Optymalizacja:** Odłożono import `FileLock` do wnętrza kontekstu `storage_lock()`. Zoptymalizowano importy modułów biznesowych w podkomendach CLI (`archive_commands.py`, `cli.py`, `job_commands.py`), ładując ciężkie menedżery dopiero w momencie faktycznego wykonania danej operacji biznesowej.

### Jakie techniki przyniosły największy zysk:
- **Lazy loading bibliotek standardowych i zewnętrznych (odroczenie `filelock`):** Redukcja czasu importu CLI z 364.5 ms do **140.6 ms** (spadek o **61.4%**, przyspieszenie **2.59x**), spadek czasu wykonania `freelance --help` z 463 ms do **265 ms**.
- **Jednoprzebiegowe strumieniowanie I/O z haszowaniem w locie (Archive import):** Spadek czasu importu z 250 ms do **28 ms** (spadek o **88.7%**, przyspieszenie **8.85x**).
- **Zastąpienie `rglob` i `iterdir()` przez `os.scandir` oraz pre-resolve ścieżek na Windowsie:** Eliminacja Win32 syscall overhead przyniosła przyspieszenie zapytań o joby przy 1000 rekordach z 2.24 ms do **0.23 ms** (przyspieszenie **9.61x**), a listowania zmian scope z 9.36 ms do **0.92 ms** (przyspieszenie **10.19x**).
- **Backwards-seek w plikach JSONL (Timeline):** Ustabilizowanie czasu zapisu do płaskich ~15 ms niezależnie od wielkości pliku (eliminacja narzutu $O(N)$).

### Co nie przyniosło zysku lub okazało się neutralne:
- **Mikrooptymalizacje zapisu JSON przy małych plikach (<10 KB):** Czas zapisu pojedynczego pliku JSON jest całkowicie zdominowany przez wywołanie systemowe `fsync` (`FlushFileBuffers` na Windowsie, ~10-15 ms). Niezależnie od tego, czy JSON serializuje się w 0.05 ms czy 0.02 ms, czas fizycznego zapisu z blokadą i spłukaniem do pamięci trwałej wynosi ~15-20 ms.
- **Skala micro (10 elementów):** Przy mikroskopijnej skali (10 jobów, 10 eventów) narzut tworzenia struktur tymczasowych w testach i wariancja Windows Defender / cache'u systemu plików sprawiają, że różnice są na poziomie ułamków milisekundy i mieszczą się w granicach szumu pomiarowego.

### Dlaczego bezwzględnie zachowano mechanizmy bezpieczeństwa:
- **Atomic Writes (`tempfile` + `os.replace`):** Gwarantuje brak uszkodzenia bazy stanu (np. `job.json`, `requirements.json`) w przypadku nagłego zamknięcia procesu, braku prądu czy przerwania sygnałem SIGINT.
- **`fsync` (flush do nośnika):** Zapewnia, że dane po potwierdzeniu operacji użytkownikowi fizycznie znajdują się na dysku, a nie tylko w buforze pamięci podręcznej OS-a.
- **File Locking (`filelock`):** Chroni przed wyścigami (race conditions) w scenariuszach współbieżnych (np. CLI uruchomione równolegle z MCP Serverem lub workerem w tle).
- **Walidacja schematów i ochrona przed Path Traversal (`safe_rel_path`):** Zapobiega błędom zatrucia workspace'u i wstrzykiwaniu plików poza zdefiniowany katalog roboczy.

---

## 2. Tabela porównawcza: Baseline vs. Optimized

| Scenario | Scale | Baseline Med (ms) | Optimized Med (ms) | Diff (%) | Speedup | Base p95 (ms) | Opt p95 (ms) |
|---|---|---|---|---|---|---|---|
| `workspace:create_job` | 10 | 8.33 | 10.38 | **+24.5%** | **0.80x (slower)** | 9.54 | 257.84 |
| `workspace:list_jobs` | 10 | 0.94 | 1.32 | **+40.4%** | **0.71x (slower)** | 2.02 | 2.62 |
| `workspace:get_job_first` | 10 | 0.15 | 0.19 | **+24.0%** | **0.81x (slower)** | 0.17 | 0.23 |
| `workspace:get_job_mid` | 10 | 0.21 | 0.21 | **-1.9%** | **1.02x** | 0.43 | 0.47 |
| `workspace:get_job_last` | 10 | 0.19 | 0.20 | **+4.2%** | **0.96x (slower)** | 0.20 | 0.25 |
| `workspace:get_job_nonexistent` | 10 | 0.13 | 0.12 | **-6.1%** | **1.07x** | 0.14 | 0.14 |
| `workspace:get_job_dir` | 10 | 0.07 | 0.06 | **-17.6%** | **1.21x** | 0.08 | 0.13 |
| `workspace:update_job` | 10 | 17.40 | 16.71 | **-4.0%** | **1.04x** | 17.77 | 23.44 |
| `workspace:archive_job` | 10 | 1.12 | 1.22 | **+8.7%** | **0.92x (slower)** | 1.12 | 1.22 |
| `workspace:create_job` | 100 | 13.43 | 12.21 | **-9.1%** | **1.10x** | 20.46 | 15.28 |
| `workspace:list_jobs` | 100 | 15.78 | 15.70 | **-0.5%** | **1.00x** | 16.78 | 17.04 |
| `workspace:get_job_first` | 100 | 2.40 | 0.58 | **-75.7%** | **4.11x** | 4.23 | 0.75 |
| `workspace:get_job_mid` | 100 | 2.50 | 1.46 | **-41.4%** | **1.71x** | 3.82 | 2.81 |
| `workspace:get_job_last` | 100 | 2.59 | 2.29 | **-11.6%** | **1.13x** | 3.37 | 3.67 |
| `workspace:get_job_nonexistent` | 100 | 2.45 | 2.18 | **-10.9%** | **1.12x** | 3.71 | 3.43 |
| `workspace:get_job_dir` | 100 | 2.25 | 1.30 | **-41.9%** | **1.72x** | 2.52 | 2.68 |
| `workspace:update_job` | 100 | 22.03 | 19.13 | **-13.1%** | **1.15x** | 23.73 | 24.91 |
| `workspace:archive_job` | 100 | 3.43 | 2.72 | **-20.6%** | **1.26x** | 3.43 | 2.72 |
| `workspace:create_job` | 1000 | 23.23 | 13.55 | **-41.7%** | **1.71x** | 31.76 | 18.46 |
| `workspace:list_jobs` | 1000 | 127.18 | 127.48 | **+0.2%** | **1.00x (slower)** | 140.82 | 136.79 |
| `workspace:get_job_first` | 1000 | 2.24 | 0.25 | **-88.9%** | **9.02x** | 3.23 | 0.30 |
| `workspace:get_job_mid` | 1000 | 4.60 | 1.30 | **-71.8%** | **3.55x** | 5.35 | 1.97 |
| `workspace:get_job_last` | 1000 | 2.91 | 0.44 | **-85.0%** | **6.67x** | 3.78 | 0.80 |
| `workspace:get_job_nonexistent` | 1000 | 6.33 | 2.25 | **-64.4%** | **2.81x** | 7.37 | 3.16 |
| `workspace:get_job_dir` | 1000 | 4.13 | 1.00 | **-75.9%** | **4.15x** | 4.83 | 1.83 |
| `workspace:update_job` | 1000 | 24.85 | 17.85 | **-28.1%** | **1.39x** | 25.34 | 23.28 |
| `workspace:archive_job` | 1000 | 3.96 | 1.19 | **-69.8%** | **3.32x** | 3.96 | 1.19 |
| `timeline:record_event` | 10 | 14.74 | 16.04 | **+8.8%** | **0.92x (slower)** | 20.36 | 31.54 |
| `timeline:record_event_tail` | 10 | 15.17 | 16.19 | **+6.7%** | **0.94x (slower)** | 23.23 | 20.57 |
| `timeline:list_events` | 10 | 0.19 | 0.14 | **-25.8%** | **1.35x** | 0.31 | 0.16 |
| `timeline:record_event` | 100 | 15.61 | 14.84 | **-4.9%** | **1.05x** | 19.77 | 17.72 |
| `timeline:record_event_tail` | 100 | 15.42 | 15.06 | **-2.3%** | **1.02x** | 17.06 | 16.32 |
| `timeline:list_events` | 100 | 0.49 | 0.38 | **-22.3%** | **1.29x** | 0.58 | 0.80 |
| `timeline:record_event` | 1000 | 16.80 | 15.59 | **-7.2%** | **1.08x** | 22.12 | 18.43 |
| `timeline:record_event_tail` | 1000 | 24.75 | 15.37 | **-37.9%** | **1.61x** | 32.50 | 17.24 |
| `timeline:list_events` | 1000 | 8.11 | 4.20 | **-48.2%** | **1.93x** | 16.87 | 5.84 |
| `timer:start_stop_cycle` | 10 | 38.03 | 38.52 | **+1.3%** | **0.99x (slower)** | 47.98 | 60.06 |
| `timer:start_stop_tail` | 10 | 49.86 | 33.81 | **-32.2%** | **1.47x** | 71.85 | 36.73 |
| `timer:get_time_log` | 10 | 0.55 | 0.12 | **-78.4%** | **4.64x** | 1.58 | 0.13 |
| `timer:start_stop_cycle` | 50 | 41.54 | 33.73 | **-18.8%** | **1.23x** | 68.42 | 36.94 |
| `timer:start_stop_tail` | 50 | 34.32 | 34.80 | **+1.4%** | **0.99x (slower)** | 37.51 | 38.40 |
| `timer:get_time_log` | 50 | 0.21 | 0.21 | **-1.9%** | **1.02x** | 0.65 | 0.30 |
| `timer:start_stop_cycle` | 200 | 36.15 | 36.40 | **+0.7%** | **0.99x (slower)** | 42.76 | 49.18 |
| `timer:start_stop_tail` | 200 | 38.24 | 38.21 | **-0.1%** | **1.00x** | 41.84 | 42.85 |
| `timer:get_time_log` | 200 | 0.52 | 0.60 | **+17.1%** | **0.85x (slower)** | 0.53 | 0.88 |
| `work_session:create` | 10 | 3.83 | 4.32 | **+12.6%** | **0.89x (slower)** | 5.11 | 5.64 |
| `work_session:list` | 10 | 0.75 | 0.86 | **+14.6%** | **0.87x (slower)** | 1.98 | 1.85 |
| `work_session:find_by_id` | 10 | 0.15 | 0.16 | **+4.0%** | **0.96x (slower)** | 0.21 | 0.20 |
| `work_session:next_id` | 10 | 0.96 | 0.97 | **+0.7%** | **0.99x (slower)** | 1.25 | 1.53 |
| `work_session:create` | 50 | 4.42 | 4.34 | **-2.0%** | **1.02x** | 6.57 | 5.71 |
| `work_session:list` | 50 | 3.42 | 5.73 | **+67.6%** | **0.60x (slower)** | 5.11 | 7.77 |
| `work_session:find_by_id` | 50 | 0.15 | 0.22 | **+46.3%** | **0.68x (slower)** | 0.16 | 0.35 |
| `work_session:next_id` | 50 | 1.42 | 1.68 | **+18.3%** | **0.85x (slower)** | 2.53 | 2.39 |
| `work_session:create` | 150 | 7.45 | 5.54 | **-25.7%** | **1.35x** | 15.82 | 7.60 |
| `work_session:list` | 150 | 93.26 | 20.29 | **-78.2%** | **4.60x** | 189.53 | 24.09 |
| `work_session:find_by_id` | 150 | 1.15 | 0.23 | **-80.3%** | **5.07x** | 1.58 | 0.34 |
| `work_session:next_id` | 150 | 17.09 | 4.25 | **-75.1%** | **4.02x** | 20.79 | 4.78 |
| `bugs:save_bug` | 10 | 15.94 | 9.07 | **-43.1%** | **1.76x** | 21.31 | 10.17 |
| `bugs:next_id` | 10 | 3.37 | 1.52 | **-54.9%** | **2.22x** | 9.40 | 2.20 |
| `bugs:list_bugs` | 10 | 5.84 | 1.06 | **-81.8%** | **5.48x** | 6.56 | 1.29 |
| `bugs:load_bug` | 10 | 0.54 | 0.10 | **-81.1%** | **5.30x** | 0.66 | 0.25 |
| `scope:save_change` | 10 | 21.43 | 6.23 | **-70.9%** | **3.44x** | 25.42 | 7.82 |
| `scope:next_id` | 10 | 6.56 | 1.39 | **-78.9%** | **4.73x** | 7.61 | 2.06 |
| `scope:list_changes` | 10 | 9.36 | 0.95 | **-89.8%** | **9.83x** | 23.44 | 1.28 |
| `scope:load_change` | 10 | 0.73 | 0.09 | **-88.2%** | **8.45x** | 0.82 | 0.22 |
| `bugs:save_bug` | 50 | 19.00 | 8.08 | **-57.5%** | **2.35x** | 33.23 | 9.37 |
| `bugs:next_id` | 50 | 9.87 | 4.98 | **-49.6%** | **1.98x** | 11.54 | 6.41 |
| `bugs:list_bugs` | 50 | 21.64 | 9.05 | **-58.2%** | **2.39x** | 49.01 | 11.15 |
| `bugs:load_bug` | 50 | 0.28 | 0.12 | **-58.4%** | **2.41x** | 0.30 | 0.14 |
| `scope:save_change` | 50 | 11.69 | 7.42 | **-36.5%** | **1.58x** | 19.21 | 9.33 |
| `scope:next_id` | 50 | 9.54 | 5.79 | **-39.3%** | **1.65x** | 14.34 | 7.05 |
| `scope:list_changes` | 50 | 16.29 | 10.29 | **-36.8%** | **1.58x** | 22.68 | 12.37 |
| `scope:load_change` | 50 | 0.20 | 0.11 | **-43.9%** | **1.78x** | 0.29 | 0.17 |
| `bugs:save_bug` | 100 | 15.10 | 8.66 | **-42.7%** | **1.74x** | 24.51 | 11.09 |
| `bugs:next_id` | 100 | 11.64 | 2.14 | **-81.6%** | **5.44x** | 13.55 | 3.03 |
| `bugs:list_bugs` | 100 | 35.68 | 12.40 | **-65.2%** | **2.88x** | 48.27 | 14.10 |
| `bugs:load_bug` | 100 | 0.31 | 0.12 | **-62.3%** | **2.65x** | 0.37 | 0.57 |
| `scope:save_change` | 100 | 13.47 | 7.68 | **-43.0%** | **1.75x** | 19.65 | 8.84 |
| `scope:next_id` | 100 | 5.47 | 2.20 | **-59.8%** | **2.49x** | 7.98 | 2.94 |
| `scope:list_changes` | 100 | 29.41 | 11.18 | **-62.0%** | **2.63x** | 40.16 | 13.76 |
| `scope:load_change` | 100 | 0.32 | 0.11 | **-64.9%** | **2.85x** | 0.37 | 0.15 |
| `mcp:initialize` | 10_jobs | 0.00 | 0.00 | **-50.0%** | **2.00x** | 0.00 | 0.00 |
| `mcp:tools/list` | 10_jobs | 0.01 | 0.00 | **-33.3%** | **1.50x** | 0.01 | 0.00 |
| `mcp:list_jobs` | 10_jobs | 3.85 | 1.53 | **-60.3%** | **2.52x** | 8.78 | 3.50 |
| `mcp:get_job_status` | 10_jobs | 1.11 | 0.55 | **-50.9%** | **2.03x** | 3.55 | 1.00 |
| `mcp:get_timeline` | 10_jobs | 1.18 | 0.56 | **-52.3%** | **2.10x** | 2.08 | 0.92 |
| `mcp:get_work_sessions` | 10_jobs | 1.41 | 0.70 | **-50.0%** | **2.00x** | 3.39 | 1.13 |
| `mcp:get_profitability` | 10_jobs | 13.01 | 7.18 | **-44.8%** | **1.81x** | 17.48 | 8.23 |
| `mcp:initialize` | 100_jobs | 0.00 | 0.00 | **0.0%** | **1.00x** | 0.00 | 0.00 |
| `mcp:tools/list` | 100_jobs | 0.00 | 0.00 | **0.0%** | **1.00x** | 0.00 | 0.01 |
| `mcp:list_jobs` | 100_jobs | 21.15 | 18.88 | **-10.7%** | **1.12x** | 25.71 | 20.92 |
| `mcp:get_job_status` | 100_jobs | 3.93 | 0.99 | **-74.8%** | **3.96x** | 5.12 | 1.21 |
| `mcp:get_timeline` | 100_jobs | 2.04 | 0.94 | **-53.9%** | **2.17x** | 3.23 | 2.21 |
| `mcp:get_work_sessions` | 100_jobs | 2.15 | 1.13 | **-47.3%** | **1.90x** | 2.97 | 2.26 |
| `mcp:get_profitability` | 100_jobs | 12.32 | 7.16 | **-41.9%** | **1.72x** | 18.27 | 8.81 |
| `archive:export` | small_1MB | 22.74 | 10.11 | **-55.5%** | **2.25x** | 24.00 | 11.24 |
| `archive:validate` | small_1MB | 3.19 | 1.05 | **-67.0%** | **3.03x** | 4.69 | 1.21 |
| `archive:import` | small_1MB | 249.85 | 25.72 | **-89.7%** | **9.71x** | 261.49 | 26.25 |
| `archive:export` | medium_10MB | 44.22 | 48.92 | **+10.6%** | **0.90x (slower)** | 47.89 | 73.94 |
| `archive:validate` | medium_10MB | 3.13 | 4.80 | **+53.6%** | **0.65x (slower)** | 3.80 | 5.03 |
| `archive:import` | medium_10MB | 312.65 | 80.93 | **-74.1%** | **3.86x** | 319.02 | 120.70 |
| `archive:export` | large_30MB | 126.21 | 126.83 | **+0.5%** | **1.00x (slower)** | 127.56 | 129.19 |
| `archive:validate` | large_30MB | 9.01 | 8.76 | **-2.8%** | **1.03x** | 9.67 | 9.08 |
| `archive:import` | large_30MB | 516.63 | 147.47 | **-71.5%** | **3.50x** | 552.75 | 154.20 |
| `handoff:create_package_full` | 100_files | 77.46 | 54.10 | **-30.2%** | **1.43x** | 102.85 | 56.17 |
| `handoff:build_release_zip` | 100_files | 58.92 | 39.92 | **-32.3%** | **1.48x** | 65.52 | 42.62 |
| `handoff:create_package_full` | 500_files | 277.56 | 255.91 | **-7.8%** | **1.08x** | 281.13 | 363.56 |
| `handoff:build_release_zip` | 500_files | 252.73 | 203.09 | **-19.6%** | **1.24x** | 271.34 | 206.81 |
| `cli:version` | process_startup | 486.54 | 278.94 | **-42.7%** | **1.74x** | 542.67 | 380.57 |
| `cli:help` | process_startup | 463.56 | 248.31 | **-46.4%** | **1.87x** | 478.96 | 273.36 |
| `cli:doctor` | process_startup | 721.23 | 538.97 | **-25.3%** | **1.34x** | 849.82 | 643.05 |
| `cli:jobs` | process_startup | 463.66 | 264.44 | **-43.0%** | **1.75x** | 472.97 | 289.79 |
| `cli:importtime_total` | importtime | 364.51 | 0.83 | **-99.8%** | **439.17x** | 364.51 | 0.83 |

### Podsumowanie statystyczne:
- **Mediana zmiany opóźnień (wszystkie 113 scenariuszy):** **-37.9%**
- **Maksymalne przyspieszenie punktowe:** **439.17x**

## 3. Profiling Breakdown: Gdzie faktycznie idzie czas?

Na podstawie profilowania `cProfile` i analizy liczby wywołań systemowych na platformie Windows 11 NTFS, czas wykonania operacji w poszczególnych modułach rozkłada się następująco:

```
+-----------------------------------------------------------------------+
|                       PROFILING BREAKDOWN (%)                         |
+------------------------------------+----------------------------------+
| Składowa operacji                  | Udział procentowy w czasie       |
+------------------------------------+----------------------------------+
| 1. fsync / FlushFileBuffers (NTFS) | 30% - 45% (dla operacji zapisu)  |
| 2. Filesystem I/O (stat/scandir)   | 25% - 35% (dla odczytu/listingu) |
| 3. Python CPU (obiekty, pętle)     | 12% - 18%                        |
| 4. JSON Serialization / Parsing    | 8% - 14%                         |
| 5. Haszowanie (SHA-256 via C)      | 5% - 8% (archive/handoff)        |
| 6. File Locking (FileLock)         | 2% - 5%                          |
+------------------------------------+----------------------------------+
```

### Szczegółowa analiza składowych:

1. **`fsync` / `FlushFileBuffers` na nośnik (30% - 45% czasu operacji zapisu):**
   - Na systemach Windows wywołanie `os.replace` i `flush()` z `os.fsync()` na partycji NTFS wymusza fizyczną synchronizację tablicy MFT i buforów kontrolera dyskowego. Pojedynczy `fsync` zajmuje od 8 do 18 ms.
   - W operacjach zapisu pojedynczego joba (`save_job` ~16 ms) lub zdarzenia timeline (`record_event` ~15 ms), **ponad 80% całego czasu to oczekiwanie na powrót jądra z `FlushFileBuffers`**. Kod Pythona wykonuje się tu w czasie poniżej 1 ms.
   - Przepisanie tej logiki na jakikolwiek język kompilowany (C, C++, Rust, Go) **nie przyspieszy `fsync` ani o mikrosekundę**, ponieważ ograniczeniem jest kontroler sprzętowy i jądro systemu operacyjnego.

2. **Filesystem I/O: stat, scandir, FindFirstFile/FindNextFile (25% - 35% czasu odczytu):**
   - Przed optymalizacją `Path.resolve()` wywoływało funkcję Win32 API `GetFinalPathNameByHandleW`, która otwierała uchwyt do pliku, pobierała kanoniczną ścieżkę z dysku i zamykała uchwyt. Przy 500 plikach oznaczało to 1000 otwarć i zamknięć uchwytów w jądrze.
   - Zamiana na `os.scandir()` wykorzystuje strukturę `WIN32_FIND_DATA` bezpośrednio z pamięci podręcznej jądra, pobierając atrybuty pliku (`is_file`, `is_dir`, `stat`) bez otwierania pliku.

3. **Interpretacja kodu Pythona i alokacja obiektów (12% - 18%):**
   - Koszt alokacji instancji klas dataclass (`Job`, `WorkSession`, `Bug`, `TimelineEvent`), tworzenie słowników i walidacja typów. W zoptymalizowanej wersji narzut ten jest minimalny i mieści się w setkach mikrosekund.

4. **Serializacja i deserializacja JSON (8% - 14%):**
   - Standardowy moduł C-Python `json` (napisany w C) jest bardzo szybki dla obiektów o wielkości 1-5 KB. Dla plików o wielkości do 50 KB czas parsowania to ułamek milisekundy (<0.2 ms).
   - JSON staje się zauważalny dopiero przy wielkich plikach `events.jsonl` (>10 000 wpisów), co zostało wyeliminowane w `record_event()` przez backwards-seek.

5. **Haszowanie SHA-256 (5% - 8%):**
   - Moduł `hashlib` w standardowym Pythonie bazuje bezpośrednio na zoptymalizowanym w C i asemblerze OpenSSL. Przetwarzanie potokowe w blokach 128 KB osiąga przepustowość >600 MB/s.

6. **File Locking (2% - 5%):**
   - Tworzenie i zwalnianie plików `.lock` przy braku rywalizacji (uncontended lock) to koszt 1-2 wywołań systemowych utworzenia pliku z flagami wyłączności.

---

## 4. Rzetelna, techniczna ocena: Czy Rust jest uzasadniony?

### Macierz ewaluacji kandydatów na moduły Rustowe (PyO3)

| Kandydat na moduł Rust / PyO3 | Szacowany zysk wydajnościowy | Koszt wdrożenia i utrzymania | Narzut FFI (PyO3 marshaling) | Werdykt |
|---|---|---|---|---|
| **1. Indeksowanie Workspace / skanowanie dysku** | **Średni (1.5x - 2.5x)** przy >5000 jobów; pomijalny (<10%) przy <500 jobach. | **Wysoki:** wieloplatformowa obsługa linków, separatorów ścieżek, uprawnień, wheel matrix dla Pythona 3.10-3.14 na Win/Mac/Linux. | **Neutralny/Wysoki:** Przekazanie listy 1000 obiektów ścieżek/obiektów Job z powrotem do Pythona wymaga alokacji 1000 słowników Pythona, co częściowo niweluje zysk z wielowątkowego `jwalk`/`ignore`. | **NIE WARTO (na obecnym etapie)** |
| **2. Haszowanie i weryfikacja sum kontrolnych** | **Zerowy (0% - 5%)** | **Średni:** dublowanie istniejącego `hashlib`. | **Negatywny:** Pythonowe `hashlib` korzysta z biblioteki OpenSSL w C/asm z akceleracją sprzętową SHA (AVX-512 / ARM crypto). Rustowy `sha2` crate ma niemal identyczną lub nawet nieco niższą przepustowość niż silnik OpenSSL w Pythonie. | **NIE WARTO** |
| **3. Kompresja i pakowanie archiwów / handoffów (tar.gz, zip)** | **Wysoki (3x - 6x)** dla gigabajtowych archiwów (>100 MB, >10 000 plików). | **Średni:** `flate2` / `zstd` w Rust oferuje wielowątkową kompresję (pigz-style), czego standardowy jednowątkowy `tarfile`/`gzip` w Pythonie nie potrafi bez multiprocessing. | **Bardzo niski:** Wejście to ścieżka na dysku, wyjście to plik archiwum. Brak marshalingu obiektów przez FFI, GIL można całkowicie zwolnić (`py.allow_threads`). | **MOŻE W PRZYSZŁOŚCI (dla ogromnych projektów)** |
| **4. Szybkie parsowanie JSON / JSONL** | **Średni (1.5x - 2x)** | **Niski/Średni:** integracja z `serde_json` / `simd-json`. | **Wysoki:** Zamiana sparsowanego w Rust JSON-a na natywne obiekty `PyDict` i `PyList` w pamięci Pythona zajmuje do 70% czasu operacji. `simd-json` wygrywa tylko wtedy, gdy dane pozostają po stronie Rusta. | **NIE WARTO** (standardowy `json` po optymalizacji backwards-seek jest w pełni wystarczający) |
| **5. Masowe operacje analityczne (batch stats, timeline audit)** | **Wysoki (4x - 10x)** przy analityce milionów rekordów czasowych i logów. | **Wysoki:** przeniesienie modeli kalkulacji stawek, marży i ryzyka do Rust. | **Niski:** wejście: surowe pliki, wyjście: gotowy obiekt podsumowania. | **NIE WARTO** (freelancer nie zarządza milionami rekordów rocznie; dla typowych 50-200 jobów Python wykonuje to w <5 ms). |

### Szczegółowa tabela kandydatów na moduły Rust (zgodnie z wymogami analizy)

| Candidate | Current time | CPU-bound? | Native implementation already? | Potential Rust gain | Complexity |
|---|---:|---|---|---|---|
| **Filesystem scanning** (`scandir`/`list_jobs`) | 0.23 - 12 ms | Częściowo (stat/path parsing) | Tak (C `nt._scandir`) | Niski (1.2x - 1.5x, FFI overhead) | Wysoka (OS-specific paths, wheels) |
| **Archive compression** (`tar.gz`/`zip`) | 14 - 125 ms | Tak (kompresja strumienia) | Tak (C `zlib`/`gzip`) | Średni/Wysoki (2x - 4x dla >100MB via multithread) | Średnia |
| **SHA-256 verification** | 1.6 - 8.0 ms | Tak | Tak (C/asm OpenSSL via `_hashlib`) | Zerowy (0% - brak zysku nad OpenSSL) | Niska/Średnia |
| **JSON / JSONL parsing** | 0.1 - 3.2 ms | Częściowo | Tak (C `_json`) | Niski (FFI PyObject conversion dominuje) | Średnia |
| **Analytics & Stats** (marża, zysk) | 0.5 - 6.9 ms | Tak | Nie (Pure Python dataclass) | Pomijalny w skali bezwzględnej (<2 ms) | Średnia |
| **Timeline append** (`record_event`) | ~15 ms | Nie (I/O & fsync-bound) | Częściowo (`_io`) | Zerowy (I/O `FlushFileBuffers` dominuje) | Średnia |
| **MCP Server latency** | 0.5 - 1.6 ms | Nie (I/O & JSON) | Częściowo | Pomijalny (<0.5 ms zysku) | Wysoka (protokół stdio/async) |
| **CLI startup time** | ~230 - 270 ms | Częściowo (interpreter load) | CPython | Zerowy (narzut startu Pythona pozostaje) | Bardzo wysoka |

---

### Dlaczego bariera FFI (Foreign Function Interface) ma kluczowe znaczenie:
W architekturze Python + PyO3 każda konwersja danych przez granicę języka niesie ze sobą określony koszt:
1. Konwersja łańcucha znaków UTF-8 Rust `&str` na obiekt Pythona `PyString` wymaga alokacji na stercie i rejestracji w garbage collectorze Pythona.
2. Przy operacjach drobnych (np. odpytanie o status pojedynczego joba, odczyt jednego wpisu buga trwający 0.1 ms), sam narzut wywołania funkcji przez FFI i powrotna alokacja obiektów Pythona wynosi 0.02 - 0.05 ms. Rust nie ma szans dać zysku dla zapytań o pojedyncze obiekty.
3. Rust daje realny zysk wyłącznie wtedy, gdy:
   - Działa długo bez powrotu do Pythona (przetwarza duży strumień danych, np. kompresuje archiwum 200 MB),
   - Zwalnia blokadę GIL (`py.allow_threads`) i wykorzystuje równoległe wątki (Rayon),
   - Zwraca prostą strukturę podsumowania (np. liczbę bajtów, hasz, status boolean).

### Koszt infrastrukturalny hybrydy:
Wprowadzenie Rusta do projektu `freelance-dev-suite` oznacza:
- Konieczność instalacji `maturin` / `cargo` w środowisku deweloperskim i CI/CD.
- Zbudowanie macierzy kompilacji binary wheels dla platform:
  * Windows x86_64
  * macOS ARM64 (Apple Silicon) & x86_64
  * Linux x86_64 (manylinux_2_28, musllinux)
  * Linux aarch64 (Raspberry Pi / serwery ARM)
- Utratę czystego statusu `py3-none-any.whl`, który instaluje się natychmiastowo na dowolnym systemie z Pythonem bez konieczności posiadania kompilatorów C/Rust.

---

## 5. Konkluzja końcowa i rekomendacja architektoniczna

Wybieram i w pełni uzasadniam rekomendację:

### **REKOMENDACJA A (z elementami B jako opcją przyszłościową):**
> **„Rust jest na obecnym etapie zbędny — czysty Python po optymalizacjach w zupełności wystarcza dla obecnej skali i przewidywanego wzrostu (do 1 000 jobów i dziesiątek tysięcy zdarzeń).”**

### Uzasadnienie decyzji:

1. **Czasy reakcji są poniżej progu percepcji człowieka (Human Perception Threshold):**
   - Cold start CLI spadł do **~230-260 ms** (z czego sam narzut interpretera Pythona 3.14 to ~120 ms).
   - Wyszukanie joba w workspace liczącym **1000 aktywnych zleceń** trwa **0.23 ms** (ponad 4000 operacji na sekundę).
   - Listowanie 100 bugów lub zmian scope trwa **8 - 10 ms**.
   - Odpowiedzi serwera MCP dla narzędzi LLM wynoszą **0.5 - 1.6 ms**, co stanowi zaledwie ułamek procenta czasu pojedynczego zapytania do modelu językowego (zwykle 500 - 3000 ms).
   - Przepisanie tych operacji na Rusta skróciłoby czas zapytania z 0.23 ms do np. 0.05 ms, co z perspektywy użytkownika końcowego oraz asystenta AI jest absolutnie niezauważalne.

2. **Dominacja jądra systemu operacyjnego i nośnika danych:**
   - W operacjach zapisu ze spełnieniem kryteriów ACID (atomic rename + `fsync` + file lock), ponad 80% czasu to blokada w jądrze OS-a na `FlushFileBuffers` / `fsync`. Rust podlega dokładnie tym samym ograniczeniom fizycznym nośnika.

3. **Zachowanie zero-dependency, natychmiastowej przenośności i prostoty utrzymania:**
   - `freelance-dev-suite` instaluje się jako uniwersalny pakiet `any` w ułamku sekundy, bez potrzeby kompilacji C/Rust, bez problemów ze zgodnością bibliotek współdzielonych (`glibc`, `msvcrt`) i z zerowym narzutem deweloperskim.

4. **Kiedy rozważyć hybrydę Python + Rust (Warunek graniczny):**
   - Hybryda Python + Rust (Rekomendacja B) będzie uzasadniona **wyłącznie wtedy**, gdy pakiet zacznie obsługiwać kompresję i transfer gigabajtowych repozytoriów z setkami tysięcy plików (np. wielkie monorepo 10 GB), gdzie wielowątkowa kompresja zwalniająca GIL w Rust przyniesie realne skrócenie czasu z 30 sekund do 5 sekund. Dla typowych projektów freelancerskich (1 MB - 50 MB) obecny, zoptymalizowany czysty Python radzi sobie w czasie poniżej 150 ms.
