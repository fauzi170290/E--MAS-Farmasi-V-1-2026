param([string]$OutputDirectory = '')
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'KhanzaBridge.cs'
$overlaySource = Join-Path $PSScriptRoot 'OverlayGeometry.cs'
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'src\emss\integrations\khanza'
}
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compiler .NET Framework x86 tidak ditemukan.' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$x86 = Join-Path $OutputDirectory 'KhanzaBridge-x86.exe'
$x64 = Join-Path $OutputDirectory 'KhanzaBridge-x64.exe'
$compatibility = Join-Path $OutputDirectory 'KhanzaBridge.exe'
$references = @('/reference:System.Windows.Forms.dll', '/reference:System.Web.Extensions.dll', '/reference:System.Management.dll')

& $compiler /nologo /target:exe /platform:x86 /optimize+ @references "/out:$x86" $source $overlaySource
if ($LASTEXITCODE -ne 0) { throw "Kompilasi KhanzaBridge x86 gagal ($LASTEXITCODE)." }
& $compiler /nologo /target:exe /platform:x64 /define:BRIDGE_X64 /optimize+ @references "/out:$x64" $source $overlaySource
if ($LASTEXITCODE -ne 0) { throw "Kompilasi KhanzaBridge x64 gagal ($LASTEXITCODE)." }
Copy-Item -LiteralPath $x86 -Destination $compatibility -Force
Get-Item -LiteralPath $compatibility,$x86,$x64 | Select-Object FullName,Length,LastWriteTime
