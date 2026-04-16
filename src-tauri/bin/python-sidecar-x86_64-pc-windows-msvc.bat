@echo off
REM Tauri sidecar wrapper: launches Python sidecar via stdin/stdout JSON-RPC
REM Installed as src-tauri/bin/python-sidecar-x86_64-pc-windows-msvc.exe
REM (compiled from this .bat using bat2exe or renamed as .exe workaround)

REM Use Python to run the sidecar
python -c "import sys; sys.path.insert(0, r'%~dp0..\..\..\python'); from python.main import main; main()"
