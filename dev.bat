@echo off
chcp 65001 >nul 2>&1
title SheetGo Electron Dev Launcher

echo ============================================
echo   SheetGo Electron Dev Launcher
echo ============================================
echo.

echo [1/1] Starting Electron renderer and desktop shell...
echo.

cd /d %~dp0frontend
npm run electron:dev

echo.
echo Electron dev session finished.
pause
