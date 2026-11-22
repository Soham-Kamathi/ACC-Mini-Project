@echo off
setlocal
cd /d "%~dp0"
title MicroFaaS Autoscaling & Observability Live Demo

echo =========================================================================
echo   MicroFaaS Live Autoscaling & Observability Demonstration
echo   Function: fibonacci-calc (Key: fk_L9Lv7eXosU6sg33Byg373M5iJfLHgAd301EBWPcOaiI)
echo =========================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" demo_autoscale_fibonacci.py %*
) else (
    python demo_autoscale_fibonacci.py %*
)

echo.
pause
