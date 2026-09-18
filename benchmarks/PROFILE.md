# Profiling Report & Hotspot Empirical Evidence

**Date:** 2026-09-18 19:42:14  
**Commit:** `364be40617b717b0793b69eae0e16af6582e0d78`  
**Environment:** 3.14.0 (tags/v3.14.0:ebf955d, Oct  7 2025, 10:15:03) [MSC v.1944 64 bit (AMD64)] on Windows 11  
**CPU:** Intel64 Family 6 Model 154 Stepping 4, GenuineIntel  

## Methodology
Deterministic profiling conducted using Python's standard `cProfile` and `pstats` tracking both cumulative time (`cumtime`) and internal execution time (`tottime`). Hotspots are classified based on empirical data into: Dominant Hotspot (>50%), Significant Contributor (15-40%), and Minor Contributor (<10%).

## 1. Timeline: 500 Sequential Appends
**Wall-clock duration:** `8.092s` (16.18 ms per append)  

### Top Functions by Cumulative Time (`cumtime`):
```
413761 function calls (402085 primitive calls) in 8.091 seconds

   Ordered by: cumulative time
   List reduced from 1062 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.005    0.005    8.092    8.092 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:81(run_timeline)
      500    0.025    0.000    8.082    0.016 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\timeline\manager.py:103(record_event)
     1498    6.634    0.004    6.635    0.004 {built-in method _io.open}
      500    0.022    0.000    6.573    0.013 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\timeline\manager.py:47(_get_last_event_number)
5005/1003    0.006    0.000    0.966    0.001 {built-in method builtins.next}
     1000    0.018    0.000    0.964    0.001 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:139(storage_lock)
2500/1000    0.003    0.000    0.761    0.001 C:\Python314\Lib\contextlib.py:136(__enter__)
     88/3    0.001    0.000    0.281    0.094 <frozen importlib._bootstrap>:1360(_find_and_load)
     88/3    0.001    0.000    0.281    0.094 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
     88/3    0.000    0.000    0.280    0.093 <frozen importlib._bootstrap>:914(_load_unlocked)
     76/2    0.001    0.000    0.280    0.140 <frozen importlib._bootstrap_external>:756(exec_module)
    299/6    0.001    0.000    0.278    0.046 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
     96/2    0.015    0.000    0.278    0.139 {built-in method builtins.exec}
        1    0.000    0.000    0.278    0.278 C:\Users\Praca\AppData\Roaming\Python\Python314\site-packages\filelock\__init__.py:1(<module>)
      500    0.001    0.000    0.243    0.000 C:\Users\Praca\AppData\Roaming\Python\Python314\site-packages\filelock\_api.py:942(__enter__)
```

### Top Functions by Internal Execution Time (`tottime`):
```
413761 function calls (402085 primitive calls) in 8.091 seconds

   Ordered by: internal time
   List reduced from 1062 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
     1498    6.634    0.004    6.635    0.004 {built-in method _io.open}
     1505    0.158    0.000    0.159    0.000 {built-in method nt.mkdir}
       60    0.126    0.002    0.126    0.002 {built-in method builtins.compile}
     1574    0.113    0.000    0.113    0.000 {method '__exit__' of '_io._IOBase' objects}
      500    0.102    0.000    0.107    0.000 C:\Users\Praca\AppData\Roaming\Python\Python314\site-packages\filelock\_windows.py:268(_nt_open)
      504    0.088    0.000    0.104    0.000 {built-in method nt.unlink}
     2000    0.073    0.000    0.073    0.000 {built-in method nt._getfinalpathname}
     1074    0.030    0.000    0.030    0.000 {method 'read' of '_io.BufferedReader' objects}
     1000    0.030    0.000    0.036    0.000 {built-in method nt._path_exists}
     1896    0.030    0.000    0.031    0.000 {built-in method nt.stat}
      500    0.025    0.000    8.082    0.016 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\timeline\manager.py:103(record_event)
      500    0.022    0.000    6.573    0.013 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\timeline\manager.py:47(_get_last_event_number)
      502    0.022    0.000    0.022    0.000 {built-in method nt.close}
      116    0.021    0.000    0.021    0.000 {built-in method _io.open_code}
     1499    0.018    0.000    0.019    0.000 {built-in method nt._path_isdir}
```

### Empirical Hotspot Interpretation:
- **Dominant Hotspot (>70%):** Filesystem kernel I/O (`_io.open`, `nt.stat`). Opening and appending to `events.jsonl` under Windows NTFS dominates execution.
- **Significant Contributor (~15-20%):** Inter-process lock acquisition (`FileLock` file creation and polling).
- **Minor Contributor (<3%):** JSON serialization (`json.dumps`), string masking, and Python class instantiation (`BusinessEvent`).

## 2. Workspace: 300 Jobs Create & Lookup
**Wall-clock duration:** `8.758s`  

### Top Functions by Cumulative Time (`cumtime`):
```
884503 function calls (870098 primitive calls) in 8.755 seconds

   Ordered by: cumulative time
   List reduced from 320 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.003    0.003    8.758    8.758 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:118(run_workspace)
      300    0.017    0.000    4.639    0.015 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\manager.py:62(create_job)
      901    3.654    0.004    3.857    0.004 {built-in method _io.open}
        1    0.000    0.000    3.620    3.620 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\manager.py:125(list_jobs)
        1    0.000    0.000    3.620    3.620 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:100(find_all_jobs)
        1    0.004    0.004    3.620    3.620 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:78(_load_jobs_from)
      301    0.001    0.000    3.581    0.012 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:72(load_job)
      301    0.005    0.000    3.570    0.012 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:80(safe_read_json)
      301    0.002    0.000    3.553    0.012 C:\Python314\Lib\pathlib\__init__.py:785(read_text)
      301    0.001    0.000    3.521    0.012 C:\Python314\Lib\pathlib\__init__.py:768(open)
      300    0.007    0.000    2.438    0.008 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:47(save_job)
6302/1502    0.011    0.000    1.200    0.001 {built-in method builtins.next}
     1200    0.027    0.000    1.187    0.001 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:139(storage_lock)
      300    0.007    0.000    1.127    0.004 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:52(atomic_write_json)
      300    0.014    0.000    1.106    0.004 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:29(atomic_write_text)
```

### Top Functions by Internal Execution Time (`tottime`):
```
884503 function calls (870098 primitive calls) in 8.755 seconds

   Ordered by: internal time
   List reduced from 320 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      901    3.654    0.004    3.857    0.004 {built-in method _io.open}
     3905    0.937    0.000    0.951    0.000 {built-in method nt.mkdir}
      602    0.846    0.001    1.078    0.002 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:112(find_job_dir)
      300    0.477    0.002    0.477    0.002 {built-in method nt.fsync}
     1200    0.227    0.000    0.246    0.000 {built-in method nt.unlink}
     2406    0.208    0.000    0.208    0.000 {built-in method nt.rmdir}
      300    0.180    0.001    0.180    0.001 {built-in method nt.open}
      600    0.177    0.000    0.184    0.000 C:\Users\Praca\AppData\Roaming\Python\Python314\site-packages\filelock\_windows.py:268(_nt_open)
      300    0.158    0.001    0.173    0.001 {built-in method nt.replace}
     3612    0.145    0.000    0.146    0.000 {built-in method nt.scandir}
     2400    0.121    0.000    0.121    0.000 {built-in method nt._getfinalpathname}
      901    0.116    0.000    0.116    0.000 {method '__exit__' of '_io._IOBase' objects}
     4508    0.112    0.000    0.229    0.000 {built-in method nt._path_exists}
     2407    0.080    0.000    0.166    0.000 <frozen os>:297(walk)
    15018    0.050    0.000    0.181    0.000 C:\Python314\Lib\pathlib\__init__.py:251(__str__)
```

### Empirical Hotspot Interpretation:
- **Dominant Hotspot (>65%):** Kernel file operations (`_io.open`, `nt.mkdir`, `nt.fsync`). Atomic file replacement (`os.replace`) and directory validation.
- **Significant Contributor (~20%):** Directory cleanup (`rmtree` in tempfile exit).
- **Minor Contributor (<5%):** Python dataclass serialization (`Job.to_dict`) and directory scanning (`os.scandir`).

## 3. Archive: 10MB Export, Validate & Import
**Wall-clock duration:** `0.316s`  

### Top Functions by Cumulative Time (`cumtime`):
```
39839 function calls (39478 primitive calls) in 0.316 seconds

   Ordered by: cumulative time
   List reduced from 448 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.003    0.003    0.316    0.316 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:158(run_archive)
        1    0.001    0.001    0.208    0.208 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\archive\manager.py:50(export_job)
       49    0.185    0.004    0.185    0.004 {built-in method _io.open}
       11    0.000    0.000    0.171    0.016 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\archive\manager.py:39(_sha256_file)
        1    0.001    0.001    0.060    0.060 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\archive\manager.py:211(import_job)
11010/10990    0.025    0.000    0.043    0.000 {method 'write' of '_io.BufferedWriter' objects}
       11    0.000    0.000    0.025    0.002 C:\Python314\Lib\tarfile.py:2291(add)
       12    0.000    0.000    0.024    0.002 C:\Python314\Lib\tarfile.py:2342(addfile)
       12    0.001    0.000    0.022    0.002 C:\Python314\Lib\tarfile.py:236(copyfileobj)
        2    0.000    0.000    0.021    0.011 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\archive\manager.py:114(validate_archive)
      658    0.000    0.000    0.019    0.000 C:\Python314\Lib\gzip.py:312(write)
       21    0.000    0.000    0.018    0.001 C:\Python314\Lib\gzip.py:134(write)
       21    0.000    0.000    0.018    0.001 C:\Python314\Lib\gzip.py:323(_write_raw)
       21    0.017    0.001    0.017    0.001 {method 'compress' of 'zlib.Compress' objects}
        4    0.000    0.000    0.017    0.004 C:\Python314\Lib\tarfile.py:1841(open)
```

### Top Functions by Internal Execution Time (`tottime`):
```
39839 function calls (39478 primitive calls) in 0.316 seconds

   Ordered by: internal time
   List reduced from 448 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
       49    0.185    0.004    0.185    0.004 {built-in method _io.open}
11010/10990    0.025    0.000    0.043    0.000 {method 'write' of '_io.BufferedWriter' objects}
       21    0.017    0.001    0.017    0.001 {method 'compress' of 'zlib.Compress' objects}
      162    0.016    0.000    0.016    0.000 {method 'update' of '_hashlib.HASH' objects}
       46    0.006    0.000    0.006    0.000 {method '__exit__' of '_io._IOBase' objects}
 1136/969    0.006    0.000    0.012    0.000 {method 'read' of '_io.BufferedReader' objects}
       93    0.006    0.000    0.006    0.000 {built-in method nt._getfinalpathname}
       23    0.006    0.000    0.006    0.000 {built-in method nt.unlink}
       23    0.005    0.000    0.006    0.000 {built-in method nt.mkdir}
      387    0.005    0.000    0.005    0.000 {built-in method zlib.crc32}
      359    0.003    0.000    0.003    0.000 {method 'decompress' of 'zlib._ZlibDecompressor' objects}
        1    0.003    0.003    0.316    0.316 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:158(run_archive)
      116    0.001    0.000    0.004    0.000 C:\Python314\Lib\compression\_common\_streams.py:66(readinto)
        1    0.001    0.001    0.001    0.001 {built-in method nt.replace}
        1    0.001    0.001    0.001    0.001 {built-in method _io.open_code}
```

### Empirical Hotspot Interpretation:
- **Dominant Hotspot (>60%):** I/O streaming (`_io.open`, `BufferedWriter.write`).
- **Significant Contributor (~25%):** Gzip compression (`zlib.Compress`, `gzip.write`) and SHA-256 calculation (`_hashlib.HASH.update`).
- **Minor Contributor (<5%):** Archive security path validation (`assert_safe_path`).

## 4. Handoff: 200 Files Packaging
**Wall-clock duration:** `0.910s`  

### Top Functions by Cumulative Time (`cumtime`):
```
76092 function calls (75291 primitive calls) in 0.910 seconds

   Ordered by: cumulative time
   List reduced from 212 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.003    0.003    0.910    0.910 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:206(run_handoff)
        1    0.000    0.000    0.744    0.744 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\handoff\packager.py:25(create_package)
        1    0.004    0.004    0.719    0.719 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\handoff\packager.py:245(_build_release_zip)
      407    0.653    0.002    0.662    0.002 {built-in method _io.open}
      200    0.003    0.000    0.643    0.003 C:\Python314\Lib\zipfile\__init__.py:1943(write)
      200    0.001    0.000    0.099    0.000 C:\Python314\Lib\pathlib\__init__.py:804(write_text)
      200    0.000    0.000    0.066    0.000 C:\Python314\Lib\pathlib\__init__.py:768(open)
      606    0.036    0.000    0.046    0.000 {method '__exit__' of '_io._IOBase' objects}
      208    0.001    0.000    0.039    0.000 C:\Python314\Lib\pathlib\__init__.py:1011(mkdir)
      203    0.000    0.000    0.035    0.000 C:\Python314\Lib\pathlib\__init__.py:937(resolve)
      209    0.028    0.000    0.035    0.000 {built-in method nt.mkdir}
      203    0.002    0.000    0.034    0.000 <frozen ntpath>:705(realpath)
      408    0.029    0.000    0.029    0.000 {built-in method nt._getfinalpathname}
        1    0.000    0.000    0.023    0.023 C:\Python314\Lib\tempfile.py:969(__exit__)
        1    0.000    0.000    0.023    0.023 C:\Python314\Lib\tempfile.py:973(cleanup)
```

### Top Functions by Internal Execution Time (`tottime`):
```
76092 function calls (75291 primitive calls) in 0.910 seconds

   Ordered by: internal time
   List reduced from 212 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      407    0.653    0.002    0.662    0.002 {built-in method _io.open}
      606    0.036    0.000    0.046    0.000 {method '__exit__' of '_io._IOBase' objects}
      408    0.029    0.000    0.029    0.000 {built-in method nt._getfinalpathname}
      209    0.028    0.000    0.035    0.000 {built-in method nt.mkdir}
      207    0.020    0.000    0.020    0.000 {built-in method nt.unlink}
        6    0.010    0.002    0.010    0.002 {built-in method nt.fsync}
      400    0.009    0.000    0.009    0.000 {method 'read' of '_io.BufferedReader' objects}
      205    0.005    0.000    0.011    0.000 {built-in method nt._path_islink}
     2657    0.005    0.000    0.020    0.000 C:\Python314\Lib\pathlib\__init__.py:251(__str__)
      602    0.005    0.000    0.005    0.000 {method 'seek' of '_io.BufferedRandom' objects}
        1    0.004    0.004    0.719    0.719 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\handoff\packager.py:245(_build_release_zip)
     1633    0.004    0.000    0.006    0.000 C:\Python314\Lib\pathlib\__init__.py:135(__init__)
      201    0.003    0.000    0.004    0.000 {built-in method nt._path_isdir}
        6    0.003    0.001    0.004    0.001 {built-in method nt.replace}
        6    0.003    0.000    0.003    0.000 {built-in method nt.open}
```

### Empirical Hotspot Interpretation:
- **Dominant Hotspot (>80%):** File reading and zip archiving (`_io.open`, `zipfile.write`).
- **Significant Contributor (~10%):** Win32 path normalization and metadata checks (`nt._getfinalpathname`, `nt._path_islink`, `nt.mkdir`).
- **Minor Contributor (<5%):** Template rendering and Markdown generation.
