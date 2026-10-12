# update-win-audio.ps1 - Deploy/update win_audio_receiver.py on Windows
# Run on Windows (PowerShell):  irm http://T1_IP:8000/update-win-audio.ps1 | iex
# What it does:
#   [1/6] locate existing audio receiver (or decide target dir)
#   [2/6] check python + ensure deps (numpy, sounddevice)
#   [3/6] download win_audio_receiver.py
#   [4/6] stop old instance (if any)
#   [5/6] install file + start hidden
#   [6/6] PING self-check on :8789
# Notes:
#   - Idempotent: safe to run for first-time deploy AND for later updates.
#   - VB-Audio Virtual Cable must be installed BEFORE the audio path can work;
#     without it the receiver exits with "output device not found" in the log.
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "Stop"
$BASE = "http://T1_IP:8000"

Write-Host "[1/6] Locating existing audio receiver / target dir ..."
$procs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'win_audio_receiver\.py' }
$dir = $null
$p = $null
if ($procs) {
  $p = $procs | Select-Object -First 1
  if ($p.CommandLine -match '"?([A-Za-z]:\\[^"]*?win_audio_receiver\.py)"?') { $dir = Split-Path $matches[1] }
  Write-Host "  running instance found: pid=$($p.ProcessId) dir=$dir"
} else {
  Write-Host "  no running instance (first-time deploy)"
  $rp = Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'win_receiver\.py' }
  if ($rp) {
    $rc = ($rp | Select-Object -First 1).CommandLine
    if ($rc -match '"?([A-Za-z]:\\[^"]*?win_receiver\.py)"?') { $dir = Split-Path $matches[1] }
  }
  if (-not $dir) { $dir = "$env:USERPROFILE\remotehub-win" }
}
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
Write-Host "  target dir = $dir"

Write-Host "[2/6] Checking python and dependencies ..."
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) {
  Write-Host "ERROR: python not found in PATH. Install Python 3 first (see TASK doc)."
  $ErrorActionPreference = $oldEAP
  return
}
& $py --version
& $py -c "import numpy, sounddevice" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "  deps missing -> installing numpy + sounddevice ..."
  & $py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple numpy sounddevice
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  mirror failed, retrying with default index ..."
    & $py -m pip install numpy sounddevice
  }
  & $py -c "import numpy, sounddevice" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: dependency install failed. Check network / pip."
    $ErrorActionPreference = $oldEAP
    return
  }
}
Write-Host "  deps OK"

Write-Host "[3/6] Downloading win_audio_receiver.py ..."
Invoke-WebRequest -Uri "$BASE/win_audio_receiver.py" -OutFile "$dir\win_audio_receiver.new" -UseBasicParsing

Write-Host "[4/6] Stopping old instance (if any) ..."
if ($p) {
  Stop-Process -Id $p.ProcessId -Force
  Start-Sleep -Milliseconds 800
}

Write-Host "[5/6] Installing and starting (hidden) ..."
Move-Item -Force "$dir\win_audio_receiver.new" "$dir\win_audio_receiver.py"
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pyw) { $pyw = $py }
Start-Process -FilePath $pyw -ArgumentList "`"$dir\win_audio_receiver.py`"" -WorkingDirectory $dir -WindowStyle Hidden
Start-Sleep -Seconds 3

Write-Host "[6/6] Self-check PING :8789 ..."
$code = "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(3);s.sendto(b'PING',('127.0.0.1',8789));print(s.recvfrom(64))"
& $py -c $code
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "PING timeout - the receiver may have failed to start. Check:"
  Write-Host "  1) VB-Cable NOT installed yet? Install it first (https://vb-audio.com/Cable/),"
  Write-Host "     reboot if the installer asks, then run this script again."
  Write-Host "  2) See the log: $dir\audio_receiver.log"
  $ErrorActionPreference = $oldEAP
  return
}
$ErrorActionPreference = $oldEAP
Write-Host ""
Write-Host "DONE. Reminder: set the WeChat IME microphone to 'CABLE Output' if not done yet."
Write-Host "Then hold the remote voice key and speak - text should appear."
