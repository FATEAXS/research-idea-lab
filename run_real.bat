@echo off
chcp 65001 >nul
title Research Idea Lab - Real Run
cd /d "%~dp0"
if not exist config.yaml (
  echo [X] config.yaml not found.
  echo     Please copy config.example.yaml to config.yaml first,
  echo     then fill in your API base_url / api_key / models.
  echo     ^(API key can also be set via environment variable IDEA_LAB_API_KEY.^)
  echo.
  pause
  exit /b 1
)
echo ==============================================
echo   Research Idea Lab -- REAL RUN
echo   This WILL call the LLM API and search the web.
echo   Cost estimate: ~100-200 LLM calls with defaults.
echo ==============================================
echo.
set "TOPIC="
set /p TOPIC=Type your research topic:
if "%TOPIC%"=="" (
  echo [X] Topic cannot be empty.
  pause
  exit /b 1
)
set "ROUNDS=2"
set /p ROUNDS=Review rounds [Enter = 2]:
set "IDEAS=4"
set /p IDEAS=Number of initial ideas [Enter = 4]:
echo.
echo Running REAL pipeline, topic: %TOPIC%
echo.
python main.py --topic "%TOPIC%" --rounds %ROUNDS% --ideas %IDEAS%
echo.
echo Done. Open the NEWEST folder under runs\, then read:
echo   final\report.md
echo.
pause
