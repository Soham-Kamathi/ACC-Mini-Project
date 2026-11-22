@echo off
REM =============================================================================
REM Kubernetes Serverless FaaS Platform - Windows Double-Click Launcher
REM =============================================================================
echo Launching FaaS Platform Stack with configuration from .env...
powershell -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" -Tunnel
pause
