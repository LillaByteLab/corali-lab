$ErrorActionPreference='Stop'
$sourceDir=$PSScriptRoot
$arch=Get-Content -LiteralPath (Join-Path $sourceDir 'ARCHITECTURE.txt') -Raw
$arch=$arch.Trim()
if($arch -notin @('arm64','x64')){throw 'Pacchetto con architettura non valida.'}
$baseDir=Join-Path $env:LOCALAPPDATA 'Programs/CoraliLab'
$targetDir=Join-Path $baseDir ('0.5.2-beta-'+$arch)
if([IO.Path]::GetFullPath($sourceDir) -eq [IO.Path]::GetFullPath($targetDir)){Write-Output 'Questa copia e gia installata.'}
elseif(Test-Path -LiteralPath $targetDir){throw 'Questa versione esiste gia. Avvia la copia installata; nessun file e stato sovrascritto.'}
else{
 New-Item -ItemType Directory -Path $targetDir | Out-Null
 Get-ChildItem -LiteralPath $sourceDir | Copy-Item -Destination $targetDir -Recurse
}
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) ('Coral'+[char]0xEC+' Lab.lnk')))
$shortcut.TargetPath=Join-Path $targetDir 'CoraliLab.exe'
$shortcut.WorkingDirectory=$targetDir
$shortcut.IconLocation=$shortcut.TargetPath
$shortcut.Save()
Write-Output ('Installazione completata in '+$targetDir+'. Apri Corali Lab dal Desktop.')
