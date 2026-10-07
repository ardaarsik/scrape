@echo off
REM Install dependencies (first run only) and scrape the page.
py -m pip install --quiet -r "%~dp0requirements.txt"
py "%~dp0scrape_teaching.py" %*
pause
