@echo off
rem AAW desktop - browser dev runtime, double-click launcher.
rem ASCII-only on purpose: cmd parses batch files by byte offset and
rem non-ASCII text breaks when the console codepage changes.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
node scripts/dev-web.mjs
if errorlevel 1 pause
