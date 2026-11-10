@echo off
rem Pytajnik na Windows: zatrzymaj (dwuklik). Logika w windows\zatrzymaj.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\zatrzymaj.ps1" %*
if errorlevel 1 pause
