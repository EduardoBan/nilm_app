param(
    [string]$OutputDir = (Join-Path (Split-Path -Parent $PSScriptRoot) 'install')
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path
$output = [IO.Path]::GetFullPath($OutputDir)
$portable = Join-Path $output 'NILM_Energy_Platform_Portable'
$zipPath = Join-Path $output 'NILM_Energy_Platform.zip'
$setupPath = Join-Path $output 'NILM_Energy_Platform_Setup.exe'

function Copy-Tree($from, $to) {
    if (-not (Test-Path -LiteralPath $from)) { return }
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    robocopy $from $to /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "No se pudo copiar $from -> $to" }
}

function Require-Path($path) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Falta: $path" }
}

function Assert-FrontendAssets($frontendRoot) {
    $index = Join-Path $frontendRoot 'index.html'
    $html = Get-Content -LiteralPath $index -Raw
    $references = [regex]::Matches(
        $html,
        '(?:src|href)\s*=\s*["'']([^"'']+)["'']',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    foreach ($match in $references) {
        $reference = ($match.Groups[1].Value -split '[?#]', 2)[0]
        if (-not $reference -or $reference.StartsWith('/') -or
            $reference -match '^(?:[a-z]+:)?//') {
            continue
        }
        $localPath = $reference.Replace('/', [IO.Path]::DirectorySeparatorChar)
        $asset = Join-Path $frontendRoot $localPath
        if (-not (Test-Path -LiteralPath $asset)) {
            throw "El frontend referencia un recurso que no se incluira: $reference"
        }
    }
}

Require-Path (Join-Path $root 'start_server.py')
Require-Path (Join-Path $root 'backend')
Require-Path (Join-Path $root 'frontend\index.html')
Require-Path (Join-Path $root 'frontend\css')
Require-Path (Join-Path $root 'frontend\dist')
Require-Path (Join-Path $root 'Data')

New-Item -ItemType Directory -Force -Path $output | Out-Null
if (Test-Path $portable) { Remove-Item -Recurse -Force $portable }
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
if (Test-Path $setupPath) { Remove-Item -Force $setupPath }
New-Item -ItemType Directory -Force -Path $portable | Out-Null

# Código y datos editables de la aplicación.
Copy-Tree (Join-Path $root 'backend') (Join-Path $portable 'backend')
New-Item -ItemType Directory -Force -Path (Join-Path $portable 'frontend') | Out-Null
Copy-Item (Join-Path $root 'frontend\index.html') (Join-Path $portable 'frontend\index.html') -Force
Copy-Tree (Join-Path $root 'frontend\css') (Join-Path $portable 'frontend\css')
Copy-Tree (Join-Path $root 'frontend\dist') (Join-Path $portable 'frontend\dist')
Assert-FrontendAssets (Join-Path $portable 'frontend')
Copy-Tree (Join-Path $root 'Data') (Join-Path $portable 'Data')
Copy-Item (Join-Path $root 'start_server.py') $portable -Force
if (Test-Path (Join-Path $root 'Informe_NILM_Inti.pdf')) {
    Copy-Item (Join-Path $root 'Informe_NILM_Inti.pdf') $portable -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $portable 'cache') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portable 'reports') | Out-Null
if (-not (Test-Path (Join-Path $portable 'backend\load_labels.json'))) {
    '{}' | Set-Content -Encoding UTF8 (Join-Path $portable 'backend\load_labels.json')
}

# Runtime Python autocontenido y selectivo. No copiar sys.prefix completo:
# en este equipo contiene herramientas y paquetes ajenos que producían un
# payload de varios GB. El helper copia la stdlib, el intérprete/DLLs y las
# distribuciones requeridas (incluidas dependencias transitivas declaradas).
$pythonExe = (Get-Command python -ErrorAction Stop).Source
$pythonPrefix = (& $pythonExe -c "import sys; print(sys.prefix)").Trim()
$runtime = Join-Path $portable 'runtime\python'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtime 'Lib') | Out-Null
foreach ($file in @('python.exe', 'pythonw.exe', 'python312.dll', 'python3.dll', 'vcruntime140.dll')) {
    $source = Join-Path $pythonPrefix $file
    if (Test-Path $source) { Copy-Item $source $runtime -Force }
}
if (Test-Path (Join-Path $pythonPrefix 'DLLs')) {
    Copy-Tree (Join-Path $pythonPrefix 'DLLs') (Join-Path $runtime 'DLLs')
}
$stdlib = Join-Path $pythonPrefix 'Lib'
Get-ChildItem $stdlib -Force | Where-Object { $_.Name -ne 'site-packages' } | ForEach-Object {
    if ($_.PSIsContainer) {
        Copy-Tree $_.FullName (Join-Path $runtime ('Lib\' + $_.Name))
    } else {
        Copy-Item $_.FullName (Join-Path $runtime 'Lib') -Force
    }
}
$siteDest = Join-Path $runtime 'Lib\site-packages'
New-Item -ItemType Directory -Force -Path $siteDest | Out-Null
# El helper externo evita que PowerShell altere el código Python al pasarlo
# como argumento multilínea y normaliza especificadores de dependencias.
& $pythonExe (Join-Path $root 'scripts\copy_runtime_packages.py') $siteDest
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron copiar las distribuciones Python requeridas' }

# python.exe detecta la stdlib copiada mediante rutas relativas. Este archivo
# evita depender del registro de instalaciones Python del equipo destino.
@'
.
Lib
DLLs
Lib\site-packages
'@ | Set-Content -Encoding ASCII (Join-Path $runtime 'python312._pth')

$smoke = 'import sys, numpy, pandas, scipy, sklearn, tornado, openpyxl, matplotlib, PIL, requests, psutil; print(sys.version); print(12345)'
& (Join-Path $runtime 'python.exe') -c $smoke
if ($LASTEXITCODE -ne 0) { throw 'El runtime Python portable no supera la prueba de imports' }

# El launcher espera el runtime en esta distribución.
$launcher = Join-Path $portable 'NILM_Platform.cmd'
@'
@echo off
setlocal EnableExtensions
set "APP_HOME=%~dp0"
set "NILM_APP_HOME=%APP_HOME%"
set "PYTHONPATH=%APP_HOME%;%APP_HOME%runtime\python\Lib\site-packages;%APP_HOME%runtime\user-site"
set "NILM_PORT=8000"
cd /d "%APP_HOME%"
"%APP_HOME%runtime\python\python.exe" "%APP_HOME%start_server.py"
endlocal
'@ | Set-Content -Encoding ASCII $launcher

# Compresión del payload con la API ZIP de .NET. No depender de tar.exe ni
# Compress-Archive: ambos han quedado bloqueados o muy lentos al procesar los
# miles de archivos binarios de NumPy/SciPy en equipos Windows.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory(
    $portable,
    $zipPath,
    [IO.Compression.CompressionLevel]::Optimal,
    $false
)

# El instalador final es un ejecutable .NET con el ZIP integrado como recurso.
# El equipo destino no necesita Python, Node, IExpress ni el ZIP hermano.
$setupPath = Join-Path $output 'NILM_Energy_Platform_Setup.exe'
if (Test-Path $setupPath) { Remove-Item -Force $setupPath }
$cscCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$csc = $cscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $csc) { throw 'No se encontro el compilador C# de .NET Framework' }
$installerSource = Join-Path $root 'scripts\NILM_Installer.cs'
Require-Path $installerSource
& $csc /nologo /target:winexe /optimize+ /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll "/resource:$zipPath,$([System.IO.Path]::GetFileName($zipPath))" /out:$setupPath $installerSource
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $setupPath)) {
    throw 'No se pudo compilar NILM_Energy_Platform_Setup.exe'
}

Write-Output "PORTABLE=$portable"
Write-Output "ZIP=$zipPath"
Write-Output "SETUP=$setupPath"
