@echo off
chcp 65001 >nul
title Research Idea Lab - Mock Demo
cd /d "%~dp0"
echo ==============================================
echo   Research Idea Lab -- Mock Demo
echo   Offline demo: NO API key, NO network needed.
echo   Results are saved under the runs\ folder.
echo ==============================================
echo.
set "TOPIC="
set /p TOPIC=Type your research topic (press Enter for default):
if "%TOPIC%"=="" set "TOPIC=low-resource efficient fine-tuning of LLMs"
echo.
echo Running mock pipeline, topic: %TOPIC%
echo.
python main.py --topic "%TOPIC%" --mock
echo.
echo Done. Open the NEWEST folder under runs\, then read:
echo   final\report.md
echo.
pause
