<# Run a portable zip's native self-test without source or developer runtimes. #>
param(
    [Parameter(Mandatory = $true)][string]$Archive,
    [string]$ExtractDir = (Join-Path $env:TEMP ('pet-portable-' + [guid]::NewGuid().ToString('N')))
)

$ErrorActionPreference = 'Stop'
$archivePath = [System.IO.Path]::GetFullPath($Archive)
$extractPath = [System.IO.Path]::GetFullPath($ExtractDir)
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) { throw "Archive missing: $archivePath" }
if (Test-Path -LiteralPath $extractPath) { throw "Extraction target already exists: $extractPath" }

Expand-Archive -LiteralPath $archivePath -DestinationPath $extractPath
$executables = @(Get-ChildItem -LiteralPath $extractPath -File -Recurse -Filter 'dsh-pet-standalone-*.exe' |
    Where-Object { $_.Name -notmatch '-setup\.exe$' })
if ($executables.Count -ne 1) { throw "Expected one desktop-pet executable, found $($executables.Count)" }
$exe = $executables[0].FullName
$bundleDll = Join-Path $executables[0].DirectoryName '_internal\pet\native\_bin\pet_core.dll'
if (-not (Test-Path -LiteralPath $bundleDll -PathType Leaf)) { throw "Bundled native DLL missing: $bundleDll" }

$probe = Join-Path $extractPath '_probe'
New-Item -ItemType Directory -Path $probe -Force | Out-Null
foreach ($folder in @('AppData', 'LocalAppData', 'Temp')) {
    New-Item -ItemType Directory -Path (Join-Path $probe $folder) -Force | Out-Null
}
$saved = @{}
foreach ($key in @('PATH','APPDATA','LOCALAPPDATA','TEMP','TMP','PET_CORE_DLL','PYTHONPATH')) {
    $saved[$key] = [Environment]::GetEnvironmentVariable($key)
}

function Invoke-Probe([string]$Name, [string]$Mode, [string]$Override = '') {
    $resultPath = Join-Path $probe "$Name.json"
    if ($Override) { $env:PET_CORE_DLL = $Override } else { Remove-Item Env:PET_CORE_DLL -ErrorAction SilentlyContinue }
    $arguments = "--native-self-test `"$resultPath`" --native-self-test-mode $Mode"
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $probe -WindowStyle Hidden -PassThru
    try {
        $process | Wait-Process -Timeout 60 -ErrorAction Stop
        $process.Refresh()
    } finally {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
    if (-not (Test-Path -LiteralPath $resultPath)) { throw "$Name did not write JSON; exit=$($process.ExitCode)" }
    return @{ exit = $process.ExitCode; result = (Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json) }
}

try {
    $windows = $env:SystemRoot
    $env:PATH = "$(Join-Path $windows 'System32');$windows"
    $env:APPDATA = Join-Path $probe 'AppData'
    $env:LOCALAPPDATA = Join-Path $probe 'LocalAppData'
    $env:TEMP = Join-Path $probe 'Temp'
    $env:TMP = $env:TEMP
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

    $native = Invoke-Probe 'native' 'native'
    if ($native.exit -ne 0 -or -not $native.result.ok -or
        $native.result.actual_backend -ne 'native' -or $native.result.native_calls -ne 1 -or
        $native.result.abi_version -ne 2 -or -not $native.result.build_id -or
        $native.result.dll_path -ine $bundleDll) {
        throw "Native frozen self-test failed: $($native.result | ConvertTo-Json -Compress)"
    }
    $missing = Join-Path $probe 'missing.dll'
    $forced = Invoke-Probe 'forced-missing' 'native' $missing
    if ($forced.exit -eq 0 -or $forced.result.ok -or $forced.result.native_calls -ne 0) {
        throw "Forced missing DLL did not fail: $($forced.result | ConvertTo-Json -Compress)"
    }
    $fallback = Invoke-Probe 'auto-fallback' 'auto' $missing
    if ($fallback.exit -ne 0 -or -not $fallback.result.ok -or
        $fallback.result.actual_backend -ne 'python' -or $fallback.result.native_calls -ne 0) {
        throw "Auto fallback failed: $($fallback.result | ConvertTo-Json -Compress)"
    }
    $wrong = Invoke-Probe 'wrong-abi' 'native' (Join-Path $windows 'System32\kernel32.dll')
    if ($wrong.exit -eq 0 -or $wrong.result.ok -or $wrong.result.native_calls -ne 0) {
        throw "Wrong ABI DLL did not fail: $($wrong.result | ConvertTo-Json -Compress)"
    }
    Write-Host "PORTABLE_NATIVE_OK archive=$archivePath exe=$exe abi=$($native.result.abi_version) build=$($native.result.build_id)"
} finally {
    foreach ($key in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($key, $saved[$key])
    }
}
