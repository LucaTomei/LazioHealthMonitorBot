@echo off
setlocal enabledelayedexpansion

REM Creiamo il file se non esiste o lo cancelliamo se esiste già
if exist mergedFile.txt del mergedFile.txt

REM Lista di file da escludere (separati da spazi)
set "EXCLUDED_FILES=package-lock.json package.json rmNodeModules.bat angular.json tsconfig.app.json tsconfig.json tsconfig.spec.json"

REM Lista di cartelle da escludere (separati da spazi)
set "EXCLUDED_FOLDERS=.git temp .vscode public __pycache__"

for /r %%f in (*.json *.py) do (
    REM Ottiene solo il nome del file senza percorso
    set "filename=%%~nxf"
    
    REM Ottiene il percorso completo
    set "fullpath=%%f"
    
    REM Flag per verificare se il file deve essere escluso
    set "exclude_file=0"
    
    REM Controlla se il file è nella lista dei file esclusi
    for %%e in (%EXCLUDED_FILES%) do (
        if "!filename!"=="%%e" (
            set "exclude_file=1"
        )
    )
    
    REM Controlla se il file è in una cartella esclusa
    for %%d in (%EXCLUDED_FOLDERS%) do (
        echo !fullpath! | findstr /i /c:"\\%%d\\" > nul
        if !errorlevel! equ 0 (
            set "exclude_file=1"
        )
    )
    
    REM Se il file non deve essere escluso, lo aggiungiamo al file finale
    if !exclude_file! equ 0 (
        echo ---- File: %%f ---- >> mergedFile.txt
        type "%%f" >> mergedFile.txt
        echo. >> mergedFile.txt
    )
)

echo Completato! File mergedFile.txt creato con successo.
endlocal