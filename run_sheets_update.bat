@echo off
cd /d "%~dp0"

:: Step 1: Generate fresh CSV exports from the database
"C:\Users\美鳳下津\AppData\Local\Python\pythoncore-3.14-64\python.exe" "%~dp0update_sheets.py" >> "%~dp0logs\sheets_update.log" 2>&1

:: Step 2: Ask Claude to upload CSVs to Google Sheets
powershell -Command "$prompt = Get-Content '%~dp0sheets_prompt.txt' -Raw; & 'C:\Users\美鳳下津\.local\bin\claude.exe' -p $prompt" >> "%~dp0logs\sheets_update.log" 2>&1
