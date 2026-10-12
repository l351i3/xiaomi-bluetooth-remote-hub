# update-win-receiver.ps1 - Upgrade Windows receiver to v1.6 + win_actions v1.10 + audio_switch v1.2
#   (picker v2: icon grid + crash fix (resident Tk thread) + high-DPI; v2.1: clean app
#    names (FileDescription) + UWP real icons; v2.2: optical size normalization + fixed
#    icon-frame/cell size; v2.3: long-name marquee; v2.4: grid-direction navigation
#    (UP/DOWN = vertical move) + UWP real icons via shell:AppsFolder; v2.5: palette aligned
#    with Mac AppPicker (light-gray frosted + system-blue selection + near-black text);
#    v2.6: selected-cell icon fused (dual-backdrop tiles); URL:/RUN: actions;
#    v1.10: APP:CLOSE - long-press power key closes the current foreground app (WM_CLOSE))
# Recommended (double-click; avoids irm|iex policy block):
#   download update-win-receiver.bat once (browser: http://T1_IP:8000/update-win-receiver.bat)
#   then double-click it - it always fetches the latest ps1 and runs it locally.
# Run on Windows (PowerShell):  irm http://T1_IP:8000/update-win-receiver.ps1 | iex
#   (if irm|iex is blocked by local policy, use the equivalent steps in TASK-mic-switch.md section 1B)
# What it does:
#   [1/6] locate receiver dir (running process -> scheduled task -> default dir; cold update supported)
#   [2/6] check python + tkinter + uiautomation (tuna mirror first; install failure = WARN)
#   [3/6] download win_receiver.py v1.6 + win_actions.py v1.10 + win_audio_switch.py v1.2 to temp files
#   [4/6] backup old files (.bak-TS) + stop old process (skipped in cold mode)
#   [5/6] replace + clear __pycache__ + restart (scheduled task in cold mode, else same exe as before)
#   [6/6] PING self-check (prints receiver.log tail on failure) + selftest
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "Stop"
$BASE = "http://T1_IP:8000"

# ---- [1/6] locate receiver dir -------------------------------------------
Write-Host "[1/6] Locating receiver ..."
$procs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'win_receiver\.py' }
$p = $procs | Select-Object -First 1
$exe = $null; $dir = $null; $cold = $false
if ($p) {
  $exe = $p.ExecutablePath
  if ($p.CommandLine -match '"?([A-Za-z]:\\[^"]*?win_receiver\.py)"?') { $dir = Split-Path $matches[1] }
  Write-Host "  running: pid=$($p.ProcessId) exe=$exe dir=$dir"
} else {
  $cold = $true
  Write-Host "  receiver NOT running (cold update mode; will start it after update)"
}
if (-not $dir) {
  $t = Get-ScheduledTask -TaskName 'remotehub-win-receiver' -ErrorAction SilentlyContinue
  if ($t -and $t.Actions.Count -gt 0) {
    $arg = "$($t.Actions[0].Arguments)"
    if ($arg -match '"?([A-Za-z]:\\[^"]*?win_receiver\.py)"?') {
      $dir = Split-Path $matches[1]
      Write-Host "  dir from scheduled task: $dir"
    }
  }
}
if (-not $dir) {
  $def = Join-Path $env:USERPROFILE 'remotehub-win'
  if (Test-Path (Join-Path $def 'win_receiver.py')) {
    $dir = $def
    Write-Host "  dir from default location: $dir"
  }
}
if (-not $dir) {
  Write-Host "ERROR: cannot locate win_receiver.py install dir (no process, no scheduled task, no default dir)."
  Write-Host "If this machine never had it, run the full deploy first (TASK-windows-deploy.md)."
  $ErrorActionPreference = $oldEAP
  return
}

# ---- [2/6] python + tkinter + uiautomation --------------------------------
Write-Host "[2/6] Checking python + tkinter + uiautomation ..."
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py -and $exe) { $py = $exe }
if (-not $py) {
  $hit = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Programs\Python') -Recurse -Filter python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($hit) { $py = $hit.FullName }
}
if (-not $py) {
  Write-Host "ERROR: python not found (PATH / old process / LOCALAPPDATA\Programs\Python)."
  Write-Host "Install Python 3 (python.org, tick Add to PATH) and retry."
  $ErrorActionPreference = $oldEAP
  return
}
& $py --version
& $py -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "  WARN: tkinter missing -> APP:PICK picker cannot open (needs CPython with tcl/tk)."
} else {
  Write-Host "  tkinter OK (picker ready)"
}
& $py -c "import uiautomation" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "  uiautomation missing -> installing (tuna mirror first) ..."
  & $py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple uiautomation
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  mirror failed, retrying with default index ..."
    & $py -m pip install uiautomation
  }
  & $py -c "import uiautomation" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  WARN: uiautomation install failed. CLICK/FOCUS_INPUT will report 'unavailable';"
    Write-Host "        APP:* (cycle/toggle/next/pick/activate) still work without it;"
    Write-Host "        mic auto-switch needs comtypes (receiver will log 'win_audio_switch NOT loaded')."
  } else {
    Write-Host "  uiautomation OK"
  }
} else {
  Write-Host "  uiautomation OK"
}

# ---- [3/6] download --------------------------------------------------------
Write-Host "[3/6] Downloading receiver v1.6 + actions v1.9 + audio_switch v1.2 ..."
try {
  Invoke-WebRequest -Uri "$BASE/win_receiver.py"     -OutFile "$dir\win_receiver.new"     -UseBasicParsing
  Invoke-WebRequest -Uri "$BASE/win_actions.py"      -OutFile "$dir\win_actions.new"      -UseBasicParsing
  Invoke-WebRequest -Uri "$BASE/win_audio_switch.py" -OutFile "$dir\win_audio_switch.new" -UseBasicParsing
} catch {
  Write-Host "ERROR: download failed: $($_.Exception.Message)"
  Write-Host "  Is the T1 dist server running? Open http://T1_IP:8000/ in a browser to check."
  $ErrorActionPreference = $oldEAP
  return
}

# ---- [4/6] backup + stop ---------------------------------------------------
Write-Host "[4/6] Backup + stopping old receiver ..."
$TS = Get-Date -Format "yyyyMMdd-HHmmss"
if (Test-Path "$dir\win_receiver.py")     { Copy-Item "$dir\win_receiver.py"     "$dir\win_receiver.py.bak-$TS"     -Force }
if (Test-Path "$dir\win_actions.py")      { Copy-Item "$dir\win_actions.py"      "$dir\win_actions.py.bak-$TS"      -Force }
if (Test-Path "$dir\win_audio_switch.py") { Copy-Item "$dir\win_audio_switch.py" "$dir\win_audio_switch.py.bak-$TS" -Force }
if ($p) {
  Stop-Process -Id $p.ProcessId -Force
  Start-Sleep -Milliseconds 800
} else {
  Write-Host "  (cold update: nothing to stop)"
}

# ---- [5/6] replace + restart ----------------------------------------------
Write-Host "[5/6] Replacing files and restarting ..."
Move-Item -Force "$dir\win_receiver.new"     "$dir\win_receiver.py"
Move-Item -Force "$dir\win_actions.new"      "$dir\win_actions.py"
Move-Item -Force "$dir\win_audio_switch.new" "$dir\win_audio_switch.py"
Remove-Item -Force -Recurse "$dir\__pycache__" -ErrorAction SilentlyContinue
if ($cold) {
  $task = Get-ScheduledTask -TaskName 'remotehub-win-receiver' -ErrorAction SilentlyContinue
  $ok = $false
  if ($task) {
    try {
      Start-ScheduledTask -TaskName 'remotehub-win-receiver' -ErrorAction Stop
      Write-Host "  started via scheduled task remotehub-win-receiver"
      $ok = $true
    } catch { $ok = $false }
  }
  if (-not $ok) {
    Start-Process -FilePath $py -ArgumentList "`"$dir\win_receiver.py`"" -WorkingDirectory $dir -WindowStyle Hidden
    Write-Host "  started via direct process: $py"
  }
} else {
  Start-Process -FilePath $exe -ArgumentList "`"$dir\win_receiver.py`"" -WorkingDirectory $dir -WindowStyle Hidden
  Write-Host "  restarted via: $exe"
}
Start-Sleep -Seconds 3

# ---- [6/6] PING + selftest -------------------------------------------------
Write-Host "[6/6] Self-check PING :8788 ..."
$code = "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(3);s.sendto(b'PING',('127.0.0.1',8788));print(s.recvfrom(64))"
$pong = & $py -c $code 2>&1
Write-Host "  $pong"
if ("$pong" -notmatch 'PONG') {
  Write-Host "  WARN: no PONG. Last 15 lines of receiver.log:"
  if (Test-Path "$dir\receiver.log") {
    Get-Content "$dir\receiver.log" -Tail 15 | ForEach-Object { Write-Host "    $_" }
  } else {
    Write-Host "    (no receiver.log)"
  }
}

Write-Host ""
Write-Host "--- selftest (platform / UIA / windows / focused / audio) ---"
& $py "$dir\win_receiver.py" --selftest

$ErrorActionPreference = $oldEAP
Write-Host ""
Write-Host "DONE (receiver v1.6 + win_actions v1.10 + audio_switch v1.2)."
Write-Host "Backups: *.bak-$TS in $dir"
Write-Host "Rollback: stop receiver, restore .bak files, start receiver again."
Write-Host ""
Write-Host "APP:PICK picker v2.6: icon grid; light-gray frosted palette aligned with Mac (system-blue selection + near-black text); selected-cell icon fused (dual-backdrop tiles); grid-direction navigation; UWP real icons; long-name marquee; clean names."
Write-Host "  arrows move, OK open, BACK/ESC cancel, 10 s auto-cancel (crash fix retained)."
Write-Host "Remote key binding: open http://T1_IP:8765/keymap (tab: Windows)."
Write-Host "  Actions: CLICK / FOCUS_INPUT / APP:CYCLE / APP:PICK / APP:<exe name> / URL:<url> / RUN:<cmd>."
Write-Host "Mic note: WeChat IME microphone must be set to 'Default Device' ONCE (see TASK-mic-switch.md)."
