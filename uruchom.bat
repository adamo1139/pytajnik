@echo off
rem Pytajnik na Windows: uruchom (dwuklik). Logika w windows\uruchom.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\uruchom.ps1" %*
if errorlevel 1 pause
