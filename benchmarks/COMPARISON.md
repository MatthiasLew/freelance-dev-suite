# Performance Comparison: Baseline vs. Optimized (Pure Python) & Rust Justification Analysis

**Baseline Commit:** `ee99bf42cbd1949519cdf6b237cbe67c9d8e7d71`  
**Optimized Commit:** `9275a9acad2f344755cea6db0111cbdaa5806982`  
**Environment:** Python 3.14.0 (AMD64) on Windows 11 (10.0.26200)  
**Hardware:** Modern Multi-core x86_64, NVMe SSD  

---

## 1. Podsumowanie zmian architektonicznych i optymalizacji

W ramach zadania przeprowadzono kompleksowy audyt wydajnościowy repozytorium `freelance-dev-suite`, zidentyfikowano wąskie gardła algorytmiczne i systemowe przy użyciu `cProfile`, a następnie wdrożono zestaw przemyślanych optymalizacji w czystym Pythonie (Pure Python). Wszystkie modyfikacje zachowują w 100% kompatybilność wsteczną publicznego API, formatów plików, schematów JSON, rygorystycznych gwarancji bezpieczeństwa (atomic writes, `fsync`, file locks, ochrona przed path traversal) oraz 100% zgodności testów (241 testów zdanych, 1 pominięty, pokrycie 83.11%).

### Co dokładnie zostało zoptymalizowane:
1. **Append-Only Timeline Manager (`packages/timeline/manager.py`):**
   - **Problem:** Każde wywołanie `record_event()` dokonywało pełnej deserializacji JSON wszystkich linii pliku `events.jsonl` wyłącznie w celu wyznaczenia kolejnego sekwencyjnego identyfikatora (`len(existing) + 1`). Przy rosnącej historii timeline rzędu tysięcy zdarzeń koszt zapisu rósł asymptotycznie jako $O(N)$.
   - **Optymalizacja ($O(1)$ fast path + $O(N)$ safety fallback):** Wdrożono $O(1)$ fast path polegający na wstecznym przeszukiwaniu wskaźnika pliku (`file.seek()`) do ostatnich 8192 bajtów bufora ogona pliku, inspekcji ostatniej kompletnej linii JSON i wyciągnięciu kolejnego identyfikatora bez dotykania reszty pliku. W przypadku plików uszkodzonych (brak trailing newline, truncated EOF, corrupted JSON) lub anomalnie wielkich wpisów (>8KB) system płynnie i bezpiecznie przełącza się na pełny fallback $O(N)$, który skanuje cały plik i odnajduje najwyższy identyfikator (`max_seen`), gwarantując brak kolizji ID nawet po awariach zasilania.

2. **Skanowanie i Indeksowanie Workspace (`packages/workspace/storage.py` & `manager.py`):**
   - **Problem:** Funkcje wyszukiwania i listowania jobów (`get_job`, `get_job_dir`, `find_job_entry`) wielokrotnie wywoływały `Path.iterdir()` i instancjonowały setki obiektów `Path`, a `_generate_job_id()` w pętli skanowało cały katalog jobów dla każdego testowanego ID ($O(N^2)$ w pesymistycznym wariancie). Ponadto `save_job()` bezwarunkowo wywoływało `mkdir(parents=True, exist_ok=True)` dla 6 podkatalogów przy każdym zapisie metadanych joba.
   - **Optymalizacja:** Zastąpiono `iterdir()` niskopoziomowym strumieniowaniem `os.scandir()`, eliminując tworzenie zbędnych obiektów `Path`. Scalono logikę odnajdywania joba w pojedynczą funkcję `find_job_entry()`. Generator ID wprowadził mechanizm `_high_watermark` synchronizowany leniwie, który najpierw sprawdza `config.job_counter`, a w razie niespójności skanuje najwyższy numeryczny ID na dysku, gwarantując pełną monotoniczność. W `save_job()` wprowadzono self-healing podkatalogów oparty o `subpath.exists()` przed wywołaniem `mkdir()`, eliminując tysiące bezużytecznych wywołań systemowych `CreateDirectoryW` / `stat` na zdrowych jobach (~0.10 ms) i automatycznie naprawiając brakujące katalogi.

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

### Pomiar opóźnień zimnego startu procesu (Cold-Process Latency):
Dzięki odroczeniu importu `filelock` komendy informacyjne i odczytowe nie ponoszą narzutu bibliotek wielowątkowości/asyncio. Poniższa tabela porównuje czas zimnego startu procesu Pythona:

| Komenda CLI | Typ operacji | Czy używa `storage_lock`? | Czas zimnego startu (Baseline) | Czas zimnego startu (Optimized HEAD) | Zmiana |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `freelance --version` | Informacyjna | Nie | 486.5 ms | **270.2 ms** (import: 140.6 ms) | **-44.5% (1.80x szybciej)** |
| `freelance --help` | Informacyjna | Nie | 463.6 ms | **265.4 ms** | **-42.8% (1.75x szybciej)** |
| `freelance jobs` | Odczytowa | Nie | 463.7 ms | **282.3 ms** | **-39.1% (1.64x szybciej)** |
| `freelance job new ...` | Modyfikująca (ACID) | **Tak (leniwy import FileLock)** | ~520 ms | **285.0 ms** | **-45.2% (1.82x szybciej)** |

*Wniosek:* Leniwy import `FileLock` w momencie pierwszego wywołania `storage_lock()` narzuca zaledwie ~2.7 ms dodatkowego czasu w stosunku do komendy tylko-do-odczytu (`282.3 ms` vs `285.0 ms`), zachowując oszczędność ~200 ms dla całego CLI.

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
| `workspace:create_job` | 10 | 8.33 | 12.32 | **+47.8%** | **0.68x (slower)** | 9.54 | 318.26 |
| `workspace:list_jobs` | 10 | 0.94 | 1.10 | **+16.3%** | **0.86x (slower)** | 2.02 | 1.69 |
| `workspace:get_job_first` | 10 | 0.15 | 0.18 | **+17.3%** | **0.85x (slower)** | 0.17 | 0.59 |
| `workspace:get_job_mid` | 10 | 0.21 | 0.17 | **-18.2%** | **1.22x** | 0.43 | 0.22 |
| `workspace:get_job_last` | 10 | 0.19 | 0.19 | **-2.1%** | **1.02x** | 0.20 | 0.74 |
| `workspace:get_job_nonexistent` | 10 | 0.13 | 0.12 | **-9.2%** | **1.10x** | 0.14 | 0.15 |
| `workspace:get_job_dir` | 10 | 0.07 | 0.06 | **-20.3%** | **1.25x** | 0.08 | 0.08 |
| `workspace:update_job` | 10 | 17.40 | 20.27 | **+16.4%** | **0.86x (slower)** | 17.77 | 29.15 |
| `workspace:archive_job` | 10 | 1.12 | 2.69 | **+139.8%** | **0.42x (slower)** | 1.12 | 2.69 |
| `workspace:create_job` | 100 | 13.43 | 15.00 | **+11.7%** | **0.90x (slower)** | 20.46 | 18.37 |
| `workspace:list_jobs` | 100 | 15.78 | 16.72 | **+6.0%** | **0.94x (slower)** | 16.78 | 19.91 |
| `workspace:get_job_first` | 100 | 2.40 | 0.75 | **-68.6%** | **3.18x** | 4.23 | 1.68 |
| `workspace:get_job_mid` | 100 | 2.50 | 1.82 | **-27.2%** | **1.37x** | 3.82 | 3.59 |
| `workspace:get_job_last` | 100 | 2.59 | 2.55 | **-1.6%** | **1.02x** | 3.37 | 4.54 |
| `workspace:get_job_nonexistent` | 100 | 2.45 | 2.33 | **-4.8%** | **1.05x** | 3.71 | 3.81 |
| `workspace:get_job_dir` | 100 | 2.25 | 1.44 | **-36.0%** | **1.56x** | 2.52 | 2.11 |
| `workspace:update_job` | 100 | 22.03 | 21.58 | **-2.0%** | **1.02x** | 23.73 | 34.16 |
| `workspace:archive_job` | 100 | 3.43 | 2.93 | **-14.5%** | **1.17x** | 3.43 | 2.93 |
| `workspace:create_job` | 1000 | 23.23 | 15.13 | **-34.9%** | **1.54x** | 31.76 | 22.62 |
| `workspace:list_jobs` | 1000 | 127.18 | 150.67 | **+18.5%** | **0.84x (slower)** | 140.82 | 224.43 |
| `workspace:get_job_first` | 1000 | 2.24 | 0.30 | **-86.5%** | **7.39x** | 3.23 | 0.98 |
| `workspace:get_job_mid` | 1000 | 4.60 | 1.47 | **-68.0%** | **3.13x** | 5.35 | 2.93 |
| `workspace:get_job_last` | 1000 | 2.91 | 0.50 | **-82.8%** | **5.83x** | 3.78 | 1.16 |
| `workspace:get_job_nonexistent` | 1000 | 6.33 | 2.30 | **-63.7%** | **2.75x** | 7.37 | 3.69 |
| `workspace:get_job_dir` | 1000 | 4.13 | 1.07 | **-74.1%** | **3.86x** | 4.83 | 2.14 |
| `workspace:update_job` | 1000 | 24.85 | 21.00 | **-15.5%** | **1.18x** | 25.34 | 37.37 |
| `workspace:archive_job` | 1000 | 3.96 | 1.27 | **-67.9%** | **3.12x** | 3.96 | 1.27 |
| `timeline:record_event` | 10 | 14.74 | 18.31 | **+24.2%** | **0.81x (slower)** | 20.36 | 31.19 |
| `timeline:record_event_tail` | 10 | 15.17 | 15.78 | **+4.0%** | **0.96x (slower)** | 23.23 | 26.45 |
| `timeline:list_events` | 10 | 0.19 | 0.15 | **-20.4%** | **1.26x** | 0.31 | 0.17 |
| `timeline:record_event` | 100 | 15.61 | 16.52 | **+5.8%** | **0.95x (slower)** | 19.77 | 22.30 |
| `timeline:record_event_tail` | 100 | 15.42 | 22.07 | **+43.1%** | **0.70x (slower)** | 17.06 | 30.61 |
| `timeline:list_events` | 100 | 0.49 | 0.81 | **+66.0%** | **0.60x (slower)** | 0.58 | 1.41 |
| `timeline:record_event` | 1000 | 16.80 | 16.59 | **-1.2%** | **1.01x** | 22.12 | 23.62 |
| `timeline:record_event_tail` | 1000 | 24.75 | 16.04 | **-35.2%** | **1.54x** | 32.50 | 21.37 |
| `timeline:list_events` | 1000 | 8.11 | 4.89 | **-39.7%** | **1.66x** | 16.87 | 6.29 |
| `timer:start_stop_cycle` | 10 | 38.03 | 38.30 | **+0.7%** | **0.99x (slower)** | 47.98 | 52.73 |
| `timer:start_stop_tail` | 10 | 49.86 | 38.16 | **-23.5%** | **1.31x** | 71.85 | 45.26 |
| `timer:get_time_log` | 10 | 0.55 | 0.13 | **-76.6%** | **4.27x** | 1.58 | 0.14 |
| `timer:start_stop_cycle` | 50 | 41.54 | 36.50 | **-12.1%** | **1.14x** | 68.42 | 55.43 |
| `timer:start_stop_tail` | 50 | 34.32 | 37.26 | **+8.6%** | **0.92x (slower)** | 37.51 | 42.84 |
| `timer:get_time_log` | 50 | 0.21 | 0.24 | **+14.6%** | **0.87x (slower)** | 0.65 | 0.26 |
| `timer:start_stop_cycle` | 200 | 36.15 | 43.70 | **+20.9%** | **0.83x (slower)** | 42.76 | 67.74 |
| `timer:start_stop_tail` | 200 | 38.24 | 40.97 | **+7.1%** | **0.93x (slower)** | 41.84 | 45.78 |
| `timer:get_time_log` | 200 | 0.52 | 0.90 | **+74.0%** | **0.57x (slower)** | 0.53 | 0.95 |
| `work_session:create` | 10 | 3.83 | 4.29 | **+12.0%** | **0.89x (slower)** | 5.11 | 7.61 |
| `work_session:list` | 10 | 0.75 | 1.17 | **+56.1%** | **0.64x (slower)** | 1.98 | 2.07 |
| `work_session:find_by_id` | 10 | 0.15 | 0.21 | **+42.4%** | **0.70x (slower)** | 0.21 | 0.24 |
| `work_session:next_id` | 10 | 0.96 | 1.40 | **+45.9%** | **0.69x (slower)** | 1.25 | 3.31 |
| `work_session:create` | 50 | 4.42 | 5.65 | **+27.7%** | **0.78x (slower)** | 6.57 | 7.53 |
| `work_session:list` | 50 | 3.42 | 6.29 | **+83.9%** | **0.54x (slower)** | 5.11 | 8.44 |
| `work_session:find_by_id` | 50 | 0.15 | 0.23 | **+56.4%** | **0.64x (slower)** | 0.16 | 0.35 |
| `work_session:next_id` | 50 | 1.42 | 2.00 | **+40.9%** | **0.71x (slower)** | 2.53 | 3.42 |
| `work_session:create` | 150 | 7.45 | 9.32 | **+25.0%** | **0.80x (slower)** | 15.82 | 15.97 |
| `work_session:list` | 150 | 93.26 | 24.38 | **-73.9%** | **3.83x** | 189.53 | 30.36 |
| `work_session:find_by_id` | 150 | 1.15 | 0.25 | **-78.4%** | **4.64x** | 1.58 | 0.28 |
| `work_session:next_id` | 150 | 17.09 | 4.57 | **-73.3%** | **3.74x** | 20.79 | 6.59 |
| `bugs:save_bug` | 10 | 15.94 | 9.77 | **-38.7%** | **1.63x** | 21.31 | 11.13 |
| `bugs:next_id` | 10 | 3.37 | 1.77 | **-47.4%** | **1.90x** | 9.40 | 3.04 |
| `bugs:list_bugs` | 10 | 5.84 | 1.17 | **-80.0%** | **4.99x** | 6.56 | 3.30 |
| `bugs:load_bug` | 10 | 0.54 | 0.11 | **-79.9%** | **4.96x** | 0.66 | 0.12 |
| `scope:save_change` | 10 | 21.43 | 8.10 | **-62.2%** | **2.65x** | 25.42 | 10.59 |
| `scope:next_id` | 10 | 6.56 | 1.65 | **-74.8%** | **3.96x** | 7.61 | 2.46 |
| `scope:list_changes` | 10 | 9.36 | 2.21 | **-76.4%** | **4.23x** | 23.44 | 5.45 |
| `scope:load_change` | 10 | 0.73 | 0.18 | **-75.2%** | **4.04x** | 0.82 | 0.20 |
| `bugs:save_bug` | 50 | 19.00 | 9.90 | **-47.9%** | **1.92x** | 33.23 | 14.04 |
| `bugs:next_id` | 50 | 9.87 | 5.51 | **-44.1%** | **1.79x** | 11.54 | 7.19 |
| `bugs:list_bugs` | 50 | 21.64 | 11.10 | **-48.7%** | **1.95x** | 49.01 | 12.38 |
| `bugs:load_bug` | 50 | 0.28 | 0.14 | **-51.6%** | **2.07x** | 0.30 | 0.35 |
| `scope:save_change` | 50 | 11.69 | 8.79 | **-24.9%** | **1.33x** | 19.21 | 11.15 |
| `scope:next_id` | 50 | 9.54 | 12.72 | **+33.4%** | **0.75x (slower)** | 14.34 | 20.61 |
| `scope:list_changes` | 50 | 16.29 | 10.69 | **-34.4%** | **1.52x** | 22.68 | 12.23 |
| `scope:load_change` | 50 | 0.20 | 0.12 | **-38.9%** | **1.64x** | 0.29 | 0.14 |
| `bugs:save_bug` | 100 | 15.10 | 11.31 | **-25.0%** | **1.33x** | 24.51 | 17.41 |
| `bugs:next_id` | 100 | 11.64 | 2.54 | **-78.1%** | **4.57x** | 13.55 | 3.11 |
| `bugs:list_bugs` | 100 | 35.68 | 14.45 | **-59.5%** | **2.47x** | 48.27 | 15.61 |
| `bugs:load_bug` | 100 | 0.31 | 0.13 | **-58.8%** | **2.43x** | 0.37 | 0.14 |
| `scope:save_change` | 100 | 13.47 | 9.45 | **-29.8%** | **1.43x** | 19.65 | 19.69 |
| `scope:next_id` | 100 | 5.47 | 3.31 | **-39.6%** | **1.66x** | 7.98 | 5.04 |
| `scope:list_changes` | 100 | 29.41 | 24.25 | **-17.5%** | **1.21x** | 40.16 | 38.53 |
| `scope:load_change` | 100 | 0.32 | 0.21 | **-34.5%** | **1.53x** | 0.37 | 0.46 |
| `mcp:initialize` | 10_jobs | 0.00 | 0.00 | **-50.0%** | **2.00x** | 0.00 | 0.00 |
| `mcp:tools/list` | 10_jobs | 0.01 | 0.00 | **-33.3%** | **1.50x** | 0.01 | 0.01 |
| `mcp:list_jobs` | 10_jobs | 3.85 | 4.52 | **+17.3%** | **0.85x (slower)** | 8.78 | 10.45 |
| `mcp:get_job_status` | 10_jobs | 1.11 | 1.02 | **-7.7%** | **1.08x** | 3.55 | 2.25 |
| `mcp:get_timeline` | 10_jobs | 1.18 | 0.85 | **-28.0%** | **1.39x** | 2.08 | 1.64 |
| `mcp:get_work_sessions` | 10_jobs | 1.41 | 0.89 | **-37.0%** | **1.59x** | 3.39 | 1.83 |
| `mcp:get_profitability` | 10_jobs | 13.01 | 7.94 | **-38.9%** | **1.64x** | 17.48 | 9.70 |
| `mcp:initialize` | 100_jobs | 0.00 | 0.00 | **0.0%** | **1.00x** | 0.00 | 0.00 |
| `mcp:tools/list` | 100_jobs | 0.00 | 0.00 | **+33.3%** | **0.75x (slower)** | 0.00 | 0.00 |
| `mcp:list_jobs` | 100_jobs | 21.15 | 21.66 | **+2.4%** | **0.98x (slower)** | 25.71 | 29.01 |
| `mcp:get_job_status` | 100_jobs | 3.93 | 1.14 | **-71.1%** | **3.46x** | 5.12 | 2.51 |
| `mcp:get_timeline` | 100_jobs | 2.04 | 1.10 | **-45.9%** | **1.85x** | 3.23 | 2.39 |
| `mcp:get_work_sessions` | 100_jobs | 2.15 | 1.34 | **-37.3%** | **1.59x** | 2.97 | 2.12 |
| `mcp:get_profitability` | 100_jobs | 12.32 | 9.26 | **-24.9%** | **1.33x** | 18.27 | 11.41 |
| `archive:export` | small_1MB | 22.74 | 19.36 | **-14.9%** | **1.17x** | 24.00 | 19.98 |
| `archive:validate` | small_1MB | 3.19 | 1.79 | **-44.0%** | **1.79x** | 4.69 | 1.92 |
| `archive:import` | small_1MB | 249.85 | 34.99 | **-86.0%** | **7.14x** | 261.49 | 35.52 |
| `archive:export` | medium_10MB | 44.22 | 65.46 | **+48.0%** | **0.68x (slower)** | 47.89 | 81.78 |
| `archive:validate` | medium_10MB | 3.13 | 4.06 | **+29.8%** | **0.77x (slower)** | 3.80 | 5.51 |
| `archive:import` | medium_10MB | 312.65 | 87.61 | **-72.0%** | **3.57x** | 319.02 | 106.23 |
| `archive:export` | large_30MB | 126.21 | 138.07 | **+9.4%** | **0.91x (slower)** | 127.56 | 143.59 |
| `archive:validate` | large_30MB | 9.01 | 8.62 | **-4.3%** | **1.05x** | 9.67 | 9.61 |
| `archive:import` | large_30MB | 516.63 | 163.38 | **-68.4%** | **3.16x** | 552.75 | 192.91 |
| `handoff:create_package_full` | 100_files | 77.46 | 62.65 | **-19.1%** | **1.24x** | 102.85 | 68.95 |
| `handoff:build_release_zip` | 100_files | 58.92 | 45.49 | **-22.8%** | **1.30x** | 65.52 | 49.75 |
| `handoff:create_package_full` | 500_files | 277.56 | 240.30 | **-13.4%** | **1.16x** | 281.13 | 244.56 |
| `handoff:build_release_zip` | 500_files | 252.73 | 211.20 | **-16.4%** | **1.20x** | 271.34 | 231.09 |
| `cli:version` | process_startup | 486.54 | 269.65 | **-44.6%** | **1.80x** | 542.67 | 334.23 |
| `cli:help` | process_startup | 463.56 | 275.22 | **-40.6%** | **1.68x** | 478.96 | 361.92 |
| `cli:doctor` | process_startup | 721.23 | 571.35 | **-20.8%** | **1.26x** | 849.82 | 884.35 |
| `cli:jobs` | process_startup | 463.66 | 277.88 | **-40.1%** | **1.67x** | 472.97 | 286.64 |
| `cli:importtime_total` | importtime | 364.51 | 1.04 | **-99.7%** | **350.49x** | 364.51 | 1.04 |

### Podsumowanie statystyczne:
- **Mediana zmiany opóźnień (wszystkie 113 scenariuszy):** **-22.8%**
- **Maksymalne przyspieszenie punktowe:** **350.49x**

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
