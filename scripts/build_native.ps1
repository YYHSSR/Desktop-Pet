<# Build, test and stage the UCRT64 C++ collision DLL and its audited imports. #>
param(
    [string]$UcrtBin = 'E:\msys2\ucrt64\bin',
    [string]$BuildDir = 'build-native\ucrt64-release',
    [string]$StageDir = 'pet\native\_bin',
    [string]$DependencyBin
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cmake = Join-Path $UcrtBin 'cmake.exe'
$ninja = Join-Path $UcrtBin 'ninja.exe'
$ctest = Join-Path $UcrtBin 'ctest.exe'
$objdump = Join-Path $UcrtBin 'objdump.exe'
$msysRoot = Split-Path -Parent (Split-Path -Parent $UcrtBin)
$cygpath = Join-Path $msysRoot 'usr\bin\cygpath.exe'
$pacman = Join-Path $msysRoot 'usr\bin\pacman.exe'
foreach ($tool in @($cmake, $ninja, $ctest, $objdump)) {
    if (-not (Test-Path -LiteralPath $tool)) { throw "Missing UCRT64 tool: $tool" }
}
$source = Join-Path $root 'C++-Python'
$build = Join-Path $root $BuildDir
$stage = [System.IO.Path]::GetFullPath((Join-Path $root $StageDir))
$allowedStageParents = @(
    [System.IO.Path]::GetFullPath((Join-Path $root 'pet\native')),
    [System.IO.Path]::GetFullPath((Join-Path $root 'build-native'))
)
if (-not @($allowedStageParents | Where-Object {
    $stage.StartsWith($_ + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}).Count) { throw "StageDir must be inside pet/native or build-native: $stage" }
# A lexical prefix is insufficient when an ancestor is a junction/symlink:
# the later recursive cleanup must never be redirected outside this checkout.
$cursor = [System.IO.Path]::GetFullPath($root)
if ((Get-Item -LiteralPath $cursor).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
    throw "Workspace root is a reparse point: $cursor"
}
$relativeStage = $stage.Substring($cursor.Length).TrimStart([char[]]@('\','/'))
foreach ($component in ($relativeStage -split '[\\/]')) {
    $cursor = Join-Path $cursor $component
    if (Test-Path -LiteralPath $cursor) {
        if ((Get-Item -LiteralPath $cursor).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "StageDir traverses a reparse point: $cursor"
        }
    }
}
if (-not $DependencyBin) { $DependencyBin = $UcrtBin }
$DependencyBin = [System.IO.Path]::GetFullPath($DependencyBin)
$originalPath = $env:PATH
try {
$env:PATH = "$UcrtBin;$env:PATH"

& $cmake -S $source -B $build -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_CXX_COMPILER=$(Join-Path $UcrtBin 'g++.exe')" "-DCMAKE_MAKE_PROGRAM=$ninja"
if ($LASTEXITCODE -ne 0) { throw 'pet_core configure failed' }
& $cmake --build $build --parallel
if ($LASTEXITCODE -ne 0) { throw 'pet_core build failed' }
& $ctest --test-dir $build --output-on-failure --no-tests=error
if ($LASTEXITCODE -ne 0) { throw 'pet_core native tests failed' }

$dll = Join-Path $build 'pet_core.dll'
if (-not (Test-Path -LiteralPath $dll)) { throw "Built DLL missing: $dll" }
$stageParent = Split-Path -Parent $stage
New-Item -ItemType Directory -Path $stageParent -Force | Out-Null
$candidate = Join-Path $stageParent ('.native-next-' + [guid]::NewGuid().ToString('N'))
$backup = Join-Path $stageParent ('.native-previous-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $candidate -Force | Out-Null
$system = '^(?i:KERNEL32|USER32|ADVAPI32|SHELL32|OLE32|OLEAUT32|WS2_32|NTDLL|GDI32|COMDLG32|CRYPT32|BCRYPT|RPCRT4|SHLWAPI|VERSION|MSVCRT|UCRTBASE|api-ms-win-.*|ext-ms-.*)\.dll$'
$queue = [System.Collections.Generic.Queue[string]]::new()
$queue.Enqueue($dll)
$seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$records = [System.Collections.Generic.List[object]]::new()
try {
while ($queue.Count -gt 0) {
    $current = $queue.Dequeue()
    $name = Split-Path -Leaf $current
    if (-not $seen.Add($name)) { continue }
    $target = Join-Path $candidate $name
    Copy-Item -LiteralPath $current -Destination $target -Force
    $imports = & $objdump -p $current | Select-String 'DLL Name:\s*(\S+)'
    if ($LASTEXITCODE -ne 0) { throw "objdump failed: $current" }
    $directImports = @($imports | ForEach-Object { $_.Matches[0].Groups[1].Value })
    $fileFormat = & $objdump -f $current | Select-String 'file format\s+(\S+)'
    if ($LASTEXITCODE -ne 0 -or -not $fileFormat) { throw "objdump architecture failed: $current" }
    $owner = 'project'
    if ($current -ne $dll -and (Test-Path -LiteralPath $cygpath) -and (Test-Path -LiteralPath $pacman)) {
        $unixPath = & $cygpath -u $current
        if ($LASTEXITCODE -ne 0) { throw "cygpath failed: $current" }
        $ownerLine = & $pacman -Qo $unixPath
        if ($LASTEXITCODE -ne 0) { throw "pacman ownership failed: $current" }
        $owner = ($ownerLine -replace '^.* is owned by ', '')
    }
    $records.Add([ordered]@{
        name = $name
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
        architecture = $fileFormat.Matches[0].Groups[1].Value
        direct_imports = $directImports
        source = $current
        source_package = $owner
    })
    foreach ($line in $imports) {
        $dependency = $line.Matches[0].Groups[1].Value
        if ($dependency -match $system) { continue }
        $dependencyPath = Join-Path $DependencyBin $dependency
        if (-not (Test-Path -LiteralPath $dependencyPath)) {
            throw "Unresolved native dependency $dependency imported by $name"
        }
        $queue.Enqueue($dependencyPath)
    }
}
$manifest = [ordered]@{
    schema = 1
    compiler = ((& (Join-Path $UcrtBin 'g++.exe') --version | Select-Object -First 1) -join '')
    build_type = 'Release'
    files = @($records | Sort-Object { $_.name })
}
$manifestPath = Join-Path $candidate 'manifest.json'
[System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
if (Test-Path -LiteralPath $stage) {
    $stageItem = Get-Item -LiteralPath $stage
    if ($stageItem.LinkType) { throw "Refusing to replace linked stage directory: $stage" }
    Move-Item -LiteralPath $stage -Destination $backup
}
try {
    Move-Item -LiteralPath $candidate -Destination $stage
} catch {
    if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $stage }
    throw
}
if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
Write-Host "pet_core staged at $stage with: $($seen -join ', ')"
} finally {
    if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate -Recurse -Force }
}
} finally {
    $env:PATH = $originalPath
}
