param(
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+$')]
    [string]$Version = "0.5.0",
    [string]$PythonExe,
    [string]$InnoCompiler
)

$ErrorActionPreference = "Stop"
$pipelineDir = Split-Path -Parent $PSScriptRoot
$portableScript = Join-Path $PSScriptRoot "build_portable.ps1"
$app = Join-Path $pipelineDir "dist\v$Version\AIHuMo Data Studio"
$release = Join-Path $pipelineDir "release"
$setup = Join-Path $release "AIHuMo-Data-Studio-Windows-x64-Setup-v$Version.exe"

if (-not (Test-Path -LiteralPath $app)) {
    if ($PythonExe) { & $portableScript -Version $Version -PythonExe $PythonExe }
    else { & $portableScript -Version $Version }
    if (-not (Test-Path -LiteralPath $app)) { throw "Portable build did not create $app" }
}

if (-not $InnoCompiler) {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    $InnoCompiler = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $InnoCompiler -or -not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "Inno Setup 6 was not found. Install it or pass -InnoCompiler to build the Setup EXE."
}
if (Test-Path -LiteralPath $setup) {
    throw "Installer v$Version already exists: $setup"
}

& $InnoCompiler "/DMyAppVersion=$Version" (Join-Path $PSScriptRoot "AIHuMoDataStudio.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
if (-not (Test-Path -LiteralPath $setup)) { throw "Installer was not created: $setup" }

$sha256 = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$setup.sha256" -Value "$sha256  $(Split-Path -Leaf $setup)" -Encoding ascii
Write-Host "Created $setup"
