@echo off
rem Stop FinAlly through WSL. The data volume is kept.
wsl.exe --cd "%~dp0.." bash scripts/stop_mac.sh
