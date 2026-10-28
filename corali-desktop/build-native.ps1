param(
 [Parameter(Mandatory=$true)][ValidateSet('arm64','x64')][string]$Architecture,
 [string]$Python='python',
 [Parameter(Mandatory=$true)][string]$Compiler,
 [Parameter(Mandatory=$true)][string]$WebViewLib
)
$ErrorActionPreference='Stop'
$coraliSource=$PSScriptRoot
$coraliEngine=if($Architecture -eq 'arm64'){'engine'}else{'engine-x64'}
$coraliMachine=& $Python -c 'import platform; print(platform.machine().lower())'
if(($Architecture -eq 'arm64' -and $coraliMachine -notin @('arm64','aarch64')) -or ($Architecture -eq 'x64' -and $coraliMachine -notin @('amd64','x86_64'))){throw 'Usare Python della stessa architettura del pacchetto.'}
if(!(Test-Path -LiteralPath (Join-Path $coraliSource "$coraliEngine/cedro.exe"))){throw 'Preparare prima il motore Cedro della corretta architettura, con licenze e metadati.'}
& $Compiler /nologo /target:exe ("/platform:$Architecture") ("/out:"+(Join-Path $coraliSource "$coraliEngine/CoraliEngineHostSilent.exe")) (Join-Path $coraliSource 'EngineHost.cs')
if($LASTEXITCODE){throw 'Compilazione collegamento Cedro fallita'}
$coraliDist=Join-Path $coraliSource "dist-$Architecture"
& $Python -m PyInstaller --noconfirm --distpath $coraliDist --workpath (Join-Path $coraliSource "build/$Architecture") (Join-Path $coraliSource "CoraliLab-$Architecture.spec")
if($LASTEXITCODE){throw 'Compilazione servizio fallita'}
$coraliOutput=Join-Path $coraliDist 'CoraliLab'
& $Compiler /nologo /target:winexe ("/platform:$Architecture") /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll ("/r:"+(Join-Path $WebViewLib 'Microsoft.Web.WebView2.Core.dll')) ("/r:"+(Join-Path $WebViewLib 'Microsoft.Web.WebView2.WinForms.dll')) ("/win32icon:"+(Join-Path $coraliSource 'corali.ico')) ("/out:"+(Join-Path $coraliOutput 'CoraliLab.exe')) (Join-Path $coraliSource 'NativeHost.cs')
if($LASTEXITCODE){throw 'Compilazione finestra fallita'}
Copy-Item -LiteralPath (Join-Path $WebViewLib 'Microsoft.Web.WebView2.Core.dll') -Destination $coraliOutput
Copy-Item -LiteralPath (Join-Path $WebViewLib 'Microsoft.Web.WebView2.WinForms.dll') -Destination $coraliOutput
Copy-Item -LiteralPath (Join-Path $WebViewLib "runtimes/win-$Architecture/native/WebView2Loader.dll") -Destination $coraliOutput
Copy-Item -LiteralPath (Join-Path $coraliSource 'README.md') -Destination (Join-Path $coraliOutput 'LEGGIMI.md')
Copy-Item -LiteralPath (Join-Path $coraliSource 'licenses') -Destination $coraliOutput -Recurse -Force
Write-Output "Pacchetto preparato in $coraliOutput. Eseguire i collaudi prima della distribuzione."
