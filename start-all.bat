@echo off
REM =============================================================================
REM Kubernetes Serverless FaaS Platform - Windows Double-Click Launcher
REM =============================================================================
powershell -ExecutionPolicy Bypass -File "%~dp0start-all.ps1" -Tunnel
pause
