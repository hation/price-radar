@echo off
rem price-radar launcher: thin bootstrap, all logic lives in start_price_radar.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_price_radar.ps1"
