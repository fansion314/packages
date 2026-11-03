$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Native Windows x64 required' }
$packagesRoot = Get-Location
$source = Join-Path $packagesRoot '.work/windows-source'
$downloads = Join-Path $packagesRoot '.work/windows-candidate/.git/windows-downloads'
$installDir = Join-Path $env:RUNNER_TEMP 'Clash Momo mirror install'
$dataDir = Join-Path $env:APPDATA 'clash-momo'
if (Test-Path $installDir) { throw 'Reserved mirror test installation already exists' }
Push-Location $source
try {
  npm install --global pnpm@11.8.0
  pnpm install --frozen-lockfile --ignore-scripts
  New-Item -ItemType Directory -Path 'dist/release' -Force | Out-Null
  Get-ChildItem -LiteralPath $downloads -File | Copy-Item -Destination 'dist/release'
  node packaging/windows/smoke.mjs
  if ($LASTEXITCODE) { throw 'Mirrored portable client and core smoke failed' }
  $installer = Get-ChildItem -LiteralPath 'dist/release' -Filter '*-windows-x64-setup.exe' | Select-Object -First 1
  if (!$installer) { throw 'Verified mirrored installer missing' }
  $process = Start-Process -FilePath $installer.FullName -ArgumentList "/S /D=$installDir" -Wait -PassThru
  if ($process.ExitCode) { throw 'Mirrored NSIS installation failed' }
  node packaging/windows/smoke.mjs --installed $installDir
  if ($LASTEXITCODE) { throw 'Mirrored installed client and core smoke failed' }
  $marker = Join-Path $dataDir 'mirror-preserve.txt'
  Set-Content -LiteralPath $marker -Value 'retain on reinstall and uninstall'
  $process = Start-Process -FilePath $installer.FullName -ArgumentList "/S /D=$installDir" -Wait -PassThru
  if ($process.ExitCode -or !(Test-Path $marker)) { throw 'Mirrored reinstall lost application data' }
  $uninstaller = Get-ChildItem -LiteralPath $installDir -Filter 'Uninstall*.exe' | Select-Object -First 1
  if (!$uninstaller) { throw 'Mirrored NSIS uninstaller missing' }
  $process = Start-Process -FilePath $uninstaller.FullName -ArgumentList '/S' -Wait -PassThru
  if ($process.ExitCode -or !(Test-Path $marker)) { throw 'Mirrored uninstall lost application data' }
  $deadline = (Get-Date).AddSeconds(30)
  while ((Test-Path (Join-Path $installDir 'Clash Momo.exe')) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250 }
  if (Test-Path (Join-Path $installDir 'Clash Momo.exe')) { throw 'Mirrored application did not uninstall' }
} finally {
  Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($installDir, [System.StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Remove-Item -LiteralPath $installDir -Recurse -Force -ErrorAction SilentlyContinue
  Pop-Location
}
Write-Host 'Verified anonymously downloaded CNB portable/installed client, core, proxy, history and retained data.'
Write-Host 'This elevated CI runner does not validate interactive UAC authorization/cancellation.'
