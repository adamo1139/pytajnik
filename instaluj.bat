@echo off
rem Pytajnik na Windows: instaluj (dwuklik). Logika w windows\instaluj.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\instaluj.ps1" %*
pause
