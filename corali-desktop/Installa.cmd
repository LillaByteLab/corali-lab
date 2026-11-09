@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Installa.ps1"
if errorlevel 1 echo Installazione interrotta. Leggi il messaggio qui sopra.
pause
