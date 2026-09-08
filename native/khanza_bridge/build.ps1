param([string]$OutputPath = '')
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'KhanzaBridge.cs'
$overlaySource = Join-Path $PSScriptRoot 'OverlayGeometry.cs'
if (-not $OutputPath) {
    $OutputPath = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'src\emss\integrations\khanza\KhanzaBridge.exe'
}
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compiler .NET Framework x86 tidak ditemukan.' }
$outputDirectory = Split-Path $OutputPath -Parent
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
& $compiler /nologo /target:exe /platform:x86 /optimize+ /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll "/out:$OutputPath" $source $overlaySource
if ($LASTEXITCODE -ne 0) { throw "Kompilasi KhanzaBridge gagal ($LASTEXITCODE)." }
Get-Item -LiteralPath $OutputPath | Select-Object FullName,Length,LastWriteTime
