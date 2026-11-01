$ErrorActionPreference = 'Stop'
$petEntry = Join-Path $PSScriptRoot 'app\main.py'
$petPython = 'E:\minconda\envs\py13\pythonw.exe'
if (-not (Test-Path -LiteralPath $petPython)) {
    $petPython = (Get-Command pythonw.exe -ErrorAction Stop).Source
}
Start-Process -FilePath $petPython -ArgumentList @(('"' + $petEntry + '"')) -WorkingDirectory $PSScriptRoot -WindowStyle Normal
