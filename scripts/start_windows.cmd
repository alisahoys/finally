@echo off
rem Run FinAlly through WSL, where Docker lives. Takes the same flags as start_mac.sh.
wsl.exe --cd "%~dp0.." bash scripts/start_mac.sh %*
