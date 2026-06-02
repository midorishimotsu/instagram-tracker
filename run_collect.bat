@echo off
cd /d "C:\Users\美鳳下津\US\02_Marketing\SNS\Instagram\Instagram tracking"
if not exist logs mkdir logs
"C:\Users\美鳳下津\AppData\Local\Python\pythoncore-3.14-64\python.exe" collect.py >> logs\collect.log 2>&1
