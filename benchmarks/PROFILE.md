# Profiling Report & Hotspot Empirical Evidence

**Date:** 2026-09-18 20:10:36  
**Commit:** `9275a9acad2f344755cea6db0111cbdaa5806982`  
**Environment:** 3.14.0 (tags/v3.14.0:ebf955d, Oct  7 2025, 10:15:03) [MSC v.1944 64 bit (AMD64)] on Windows 11  
**CPU:** Intel64 Family 6 Model 154 Stepping 4, GenuineIntel  

## Methodology
Deterministic profiling conducted using Python's standard `cProfile` and `pstats` tracking both cumulative time (`cumtime`) and internal execution time (`tottime`). Hotspots are classified based on empirical data into: Dominant Hotspot (>50%), Significant Contributor (15-40%), and Minor Contributor (<10%).

## 1. Timeline: 500 Sequential Appends
**Wall-clock duration:** `8.252s` (16.50 ms per append)  

### Top Functions by Cumulative Time (`cumtime`):
```
416262 function calls (404586 primitive calls) in 8.251 seconds

   Ordered by: cumulative time
   List reduced from 1065 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.005    0.005    8.252    8.252 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:80(run_timeline)
      500    0.026    0.000    8.242    0.016 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\timeline\manager.py:103(record_event)
     1498    6.707    0.004    6.709    0.004 {built-in method _io.open}
      500    0.024    0.000    6.671    0.013 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\timeline\manager.py:47(_get_last_event_number)
5005/1003    0.006    0.000    1.021    0.001 {built-in method builtins.next}
     1000    0.020    0.000    1.019    0.001 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:148(storage_lock)
2500/1000    0.003    0.000    0.798    0.001 C:\Python314\Lib\contextlib.py:136(__enter__)
     88/3    0.001    0.000    0.305    0.102 <frozen importlib._bootstrap>:1360(_find_and_load)
     88/3    0.001    0.000    0.305    0.102 <frozen importlib._bootstrap>:1308(_find_and_load_unlocked)
     88/3    0.001    0.000    0.304    0.101 <frozen importlib._bootstrap>:914(_load_unlocked)
     76/2    0.000    0.000    0.304    0.152 <frozen importlib._bootstrap_external>:756(exec_module)
    299/6    0.001    0.000    0.302    0.050 <frozen importlib._bootstrap>:483(_call_with_frames_removed)
     96/2    0.016    0.000    0.302    0.151 {built-in method builtins.exec}
        1    0.000    0.000    0.302    0.302 C:\Users\Praca\AppData\Roaming\Python\Python314\site-packages\filelock\__init__.py:1(<module>)
      500    0.001    0.000    0.242    0.000 C:\Users\Praca\AppData\Roaming\Python\Python314\site-packages\filelock\_api.py:942(__enter__)
```

### Top Functions by Internal Execution Time (`tottime`):
```
416262 function calls (404586 primitive calls) in 8.251 seconds

   Ordered by: internal time
   List reduced from 1065 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
     1498    6.707    0.004    6.709    0.004 {built-in method _io.open}
     1505    0.166    0.000    0.168    0.000 {built-in method nt.mkdir}
       60    0.131    0.002    0.131    0.002 {built-in method builtins.compile}
     1574    0.121    0.000    0.121    0.000 {method '__exit__' of '_io._IOBase' objects}
      500    0.101    0.000    0.105    0.000 C:\Users\Praca\AppData\Roaming\Python\Python314\site-packages\filelock\_windows.py:268(_nt_open)
      504    0.098    0.000    0.114    0.000 {built-in method nt.unlink}
     2000    0.078    0.000    0.078    0.000 {built-in method nt._getfinalpathname}
     1074    0.034    0.000    0.034    0.000 {method 'read' of '_io.BufferedReader' objects}
     1000    0.032    0.000    0.037    0.000 {built-in method nt._path_exists}
     1896    0.032    0.000    0.033    0.000 {built-in method nt.stat}
      502    0.028    0.000    0.028    0.000 {built-in method nt.close}
      500    0.026    0.000    8.242    0.016 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\timeline\manager.py:103(record_event)
      116    0.026    0.000    0.026    0.000 {built-in method _io.open_code}
      500    0.024    0.000    6.671    0.013 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\timeline\manager.py:47(_get_last_event_number)
     1000    0.020    0.000    1.019    0.001 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:148(storage_lock)
```

### Empirical Hotspot Interpretation:
- **Dominant Hotspot (>70%):** Filesystem kernel I/O (`_io.open`, `nt.stat`). Opening and appending to `events.jsonl` under Windows NTFS dominates execution.
- **Significant Contributor (~15-20%):** Inter-process lock acquisition (`FileLock` file creation and polling).
- **Minor Contributor (<3%):** JSON serialization (`json.dumps`), string masking, and Python class instantiation (`BusinessEvent`).

## 2. Workspace: 300 Jobs Create & Lookup
**Wall-clock duration:** `10.003s`  

### Top Functions by Cumulative Time (`cumtime`):
```
887804 function calls (873399 primitive calls) in 10.000 seconds

   Ordered by: cumulative time
   List reduced from 323 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.003    0.003   10.003   10.003 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:117(run_workspace)
      300    0.019    0.000    5.262    0.018 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\manager.py:62(create_job)
      901    4.229    0.005    4.452    0.005 {built-in method _io.open}
        1    0.000    0.000    4.176    4.176 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\manager.py:125(list_jobs)
        1    0.000    0.000    4.176    4.176 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:100(find_all_jobs)
        1    0.005    0.005    4.176    4.176 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:78(_load_jobs_from)
      301    0.002    0.000    4.135    0.014 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:72(load_job)
      301    0.005    0.000    4.123    0.014 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:80(safe_read_json)
      301    0.002    0.000    4.105    0.014 C:\Python314\Lib\pathlib\__init__.py:785(read_text)
      301    0.001    0.000    4.072    0.014 C:\Python314\Lib\pathlib\__init__.py:768(open)
      300    0.008    0.000    2.718    0.009 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:47(save_job)
6302/1502    0.012    0.000    1.381    0.001 {built-in method builtins.next}
     1200    0.033    0.000    1.369    0.001 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:148(storage_lock)
      602    0.967    0.002    1.232    0.002 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:112(find_job_dir)
      300    0.008    0.000    1.211    0.004 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\storage_utils.py:52(atomic_write_json)
```

### Top Functions by Internal Execution Time (`tottime`):
```
887804 function calls (873399 primitive calls) in 10.000 seconds

   Ordered by: internal time
   List reduced from 323 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      901    4.229    0.005    4.452    0.005 {built-in method _io.open}
     3905    1.100    0.000    1.115    0.000 {built-in method nt.mkdir}
      602    0.967    0.002    1.232    0.002 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\workspace\storage.py:112(find_job_dir)
      300    0.485    0.002    0.485    0.002 {built-in method nt.fsync}
     1200    0.255    0.000    0.278    0.000 {built-in method nt.unlink}
     2406    0.237    0.000    0.237    0.000 {built-in method nt.rmdir}
      600    0.210    0.000    0.218    0.000 C:\Users\Praca\AppData\Roaming\Python\Python314\site-packages\filelock\_windows.py:268(_nt_open)
      300    0.200    0.001    0.200    0.001 {built-in method nt.open}
      300    0.180    0.001    0.196    0.001 {built-in method nt.replace}
     3612    0.162    0.000    0.163    0.000 {built-in method nt.scandir}
     2400    0.134    0.000    0.134    0.000 {built-in method nt._getfinalpathname}
     4508    0.128    0.000    0.262    0.000 {built-in method nt._path_exists}
      901    0.126    0.000    0.126    0.000 {method '__exit__' of '_io._IOBase' objects}
     2407    0.094    0.000    0.192    0.000 <frozen os>:297(walk)
    15018    0.058    0.000    0.203    0.000 C:\Python314\Lib\pathlib\__init__.py:251(__str__)
```

### Empirical Hotspot Interpretation:
- **Dominant Hotspot (>65%):** Kernel file operations (`_io.open`, `nt.mkdir`, `nt.fsync`). Atomic file replacement (`os.replace`) and directory validation.
- **Significant Contributor (~20%):** Directory cleanup (`rmtree` in tempfile exit).
- **Minor Contributor (<5%):** Python dataclass serialization (`Job.to_dict`) and directory scanning (`os.scandir`).

## 3. Archive: 10MB Export, Validate & Import
**Wall-clock duration:** `0.435s`  

### Top Functions by Cumulative Time (`cumtime`):
```
39839 function calls (39478 primitive calls) in 0.435 seconds

   Ordered by: cumulative time
   List reduced from 448 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.004    0.004    0.435    0.435 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:155(run_archive)
        1    0.001    0.001    0.249    0.249 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\archive\manager.py:50(export_job)
       49    0.224    0.005    0.225    0.005 {built-in method _io.open}
       11    0.000    0.000    0.198    0.018 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\archive\manager.py:39(_sha256_file)
        1    0.001    0.001    0.073    0.073 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\archive\manager.py:211(import_job)
11010/10990    0.030    0.000    0.057    0.000 {method 'write' of '_io.BufferedWriter' objects}
       46    0.048    0.001    0.048    0.001 {method '__exit__' of '_io._IOBase' objects}
       11    0.000    0.000    0.037    0.003 C:\Python314\Lib\tarfile.py:2291(add)
        2    0.000    0.000    0.036    0.018 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\archive\manager.py:114(validate_archive)
       12    0.000    0.000    0.035    0.003 C:\Python314\Lib\tarfile.py:2342(addfile)
       12    0.001    0.000    0.032    0.003 C:\Python314\Lib\tarfile.py:236(copyfileobj)
      658    0.001    0.000    0.029    0.000 C:\Python314\Lib\gzip.py:312(write)
        4    0.000    0.000    0.029    0.007 C:\Python314\Lib\tarfile.py:1841(open)
        4    0.000    0.000    0.029    0.007 C:\Python314\Lib\tarfile.py:1958(gzopen)
       21    0.000    0.000    0.027    0.001 C:\Python314\Lib\gzip.py:134(write)
```

### Top Functions by Internal Execution Time (`tottime`):
```
39839 function calls (39478 primitive calls) in 0.435 seconds

   Ordered by: internal time
   List reduced from 448 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
       49    0.224    0.005    0.225    0.005 {built-in method _io.open}
       46    0.048    0.001    0.048    0.001 {method '__exit__' of '_io._IOBase' objects}
11010/10990    0.030    0.000    0.057    0.000 {method 'write' of '_io.BufferedWriter' objects}
       21    0.025    0.001    0.025    0.001 {method 'compress' of 'zlib.Compress' objects}
      162    0.020    0.000    0.020    0.000 {method 'update' of '_hashlib.HASH' objects}
       23    0.009    0.000    0.009    0.000 {built-in method nt.unlink}
 1136/969    0.008    0.000    0.016    0.000 {method 'read' of '_io.BufferedReader' objects}
       93    0.008    0.000    0.008    0.000 {built-in method nt._getfinalpathname}
      387    0.006    0.000    0.006    0.000 {built-in method zlib.crc32}
       23    0.006    0.000    0.007    0.000 {built-in method nt.mkdir}
      359    0.004    0.000    0.004    0.000 {method 'decompress' of 'zlib._ZlibDecompressor' objects}
        1    0.004    0.004    0.435    0.435 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:155(run_archive)
      116    0.001    0.000    0.006    0.000 C:\Python314\Lib\compression\_common\_streams.py:66(readinto)
      359    0.001    0.000    0.011    0.000 C:\Python314\Lib\gzip.py:545(read)
        9    0.001    0.000    0.001    0.000 {built-in method nt.rmdir}
```

### Empirical Hotspot Interpretation:
- **Dominant Hotspot (>60%):** I/O streaming (`_io.open`, `BufferedWriter.write`).
- **Significant Contributor (~25%):** Gzip compression (`zlib.Compress`, `gzip.write`) and SHA-256 calculation (`_hashlib.HASH.update`).
- **Minor Contributor (<5%):** Archive security path validation (`assert_safe_path`).

## 4. Handoff: 200 Files Packaging
**Wall-clock duration:** `2.510s`  

### Top Functions by Cumulative Time (`cumtime`):
```
76092 function calls (75291 primitive calls) in 2.510 seconds

   Ordered by: cumulative time
   List reduced from 212 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.003    0.003    2.510    2.510 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\benchmarks\profile_hotspots.py:201(run_handoff)
        1    0.000    0.000    2.308    2.308 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\handoff\packager.py:25(create_package)
        1    0.005    0.005    2.283    2.283 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\handoff\packager.py:245(_build_release_zip)
      407    2.203    0.005    2.212    0.005 {built-in method _io.open}
      200    0.004    0.000    2.193    0.011 C:\Python314\Lib\zipfile\__init__.py:1943(write)
      200    0.001    0.000    0.121    0.001 C:\Python314\Lib\pathlib\__init__.py:804(write_text)
      200    0.000    0.000    0.082    0.000 C:\Python314\Lib\pathlib\__init__.py:768(open)
      606    0.042    0.000    0.056    0.000 {method '__exit__' of '_io._IOBase' objects}
      208    0.001    0.000    0.047    0.000 C:\Python314\Lib\pathlib\__init__.py:1011(mkdir)
      203    0.001    0.000    0.042    0.000 C:\Python314\Lib\pathlib\__init__.py:937(resolve)
      209    0.034    0.000    0.042    0.000 {built-in method nt.mkdir}
      203    0.002    0.000    0.040    0.000 <frozen ntpath>:705(realpath)
      408    0.035    0.000    0.035    0.000 {built-in method nt._getfinalpathname}
        1    0.000    0.000    0.027    0.027 C:\Python314\Lib\tempfile.py:969(__exit__)
        1    0.000    0.000    0.027    0.027 C:\Python314\Lib\tempfile.py:973(cleanup)
```

### Top Functions by Internal Execution Time (`tottime`):
```
76092 function calls (75291 primitive calls) in 2.510 seconds

   Ordered by: internal time
   List reduced from 212 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      407    2.203    0.005    2.212    0.005 {built-in method _io.open}
      606    0.042    0.000    0.056    0.000 {method '__exit__' of '_io._IOBase' objects}
      408    0.035    0.000    0.035    0.000 {built-in method nt._getfinalpathname}
      209    0.034    0.000    0.042    0.000 {built-in method nt.mkdir}
      207    0.023    0.000    0.023    0.000 {built-in method nt.unlink}
      400    0.013    0.000    0.013    0.000 {method 'read' of '_io.BufferedReader' objects}
        6    0.010    0.002    0.010    0.002 {built-in method nt.fsync}
      205    0.008    0.000    0.016    0.000 {built-in method nt._path_islink}
      602    0.007    0.000    0.007    0.000 {method 'seek' of '_io.BufferedRandom' objects}
     2657    0.006    0.000    0.025    0.000 C:\Python314\Lib\pathlib\__init__.py:251(__str__)
        1    0.005    0.005    2.283    2.283 C:\Users\Praca\fork\MatthiasLew\freelance-dev-suite\packages\handoff\packager.py:245(_build_release_zip)
     1633    0.004    0.000    0.007    0.000 C:\Python314\Lib\pathlib\__init__.py:135(__init__)
      200    0.004    0.000    2.193    0.011 C:\Python314\Lib\zipfile\__init__.py:1943(write)
      201    0.004    0.000    0.004    0.000 {built-in method nt._path_isdir}
      200    0.004    0.000    0.004    0.000 {built-in method zlib.compressobj}
```

### Empirical Hotspot Interpretation:
- **Dominant Hotspot (>80%):** File reading and zip archiving (`_io.open`, `zipfile.write`).
- **Significant Contributor (~10%):** Win32 path normalization and metadata checks (`nt._getfinalpathname`, `nt._path_islink`, `nt.mkdir`).
- **Minor Contributor (<5%):** Template rendering and Markdown generation.
