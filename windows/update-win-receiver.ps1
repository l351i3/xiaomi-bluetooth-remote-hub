# update-win-receiver.ps1 - Upgrade Windows receiver to v1.11 + win_actions v1.14 + audio_switch v1.2 + presence_beat v1.0
#   (v1.10 + v1.14: power-key multi-tap device switch HUD - T1 power key taps 1/2/3 switch the
#    remote target to ATV/Mac/Windows; a KEY TARGET:SWITCH:<name> DOWN packet makes this machine
#    pop a "🎯 已切到 X" Tk overlay (same route as MOUSE:*, single DOWN, no debounce; invalid
#    target / UP ignored). Also retained from v1.9 + v1.13: ★ cross-module SendInput
#    type-unification fix (single shared INPUT class + exception logging - "OK key does
#    nothing" root cause); v1.8 + v1.12: glide speed event-driven reset, mode-switch HUD
#    (MOUSE:MODE:ON|OFF), MOUSE:REPORT forensics (with input_class_module fingerprint);
#    retained: picker v2.6 icon grid, MOUSE mode (long-press LIVE; OK=click L/R;
#    vol +/- = scroll; BACK exits; keepalive 0.4s / stale 1.2s))
# Recommended (double-click; avoids irm|iex policy block):
#   download update-win-receiver.bat once (browser: http://T1_IP:8000/update-win-receiver.bat)
#   then double-click it - it always fetches the latest ps1 and runs it locally.
# Run on Windows (PowerShell):  irm http://T1_IP:8000/update-win-receiver.ps1 | iex
#   (if irm|iex is blocked by local policy, use the equivalent steps in TASK-mic-switch.md section 1B)
# What it does:
#   [1/7] locate receiver dir (running process -> scheduled task -> default dir; cold update supported)
#   [2/7] pre-upgrade forensics upload -> T1 :8001 (receiver.log + file fingerprints/versions)
#   [3/7] check python + tkinter + uiautomation (tuna mirror first; install failure = WARN)
#   [4/7] download win_receiver.py v1.11 + win_actions.py v1.14 + win_audio_switch.py v1.2 + presence_beat.py v1.0 to temp files
#   [5/7] backup old files (.bak-TS) + stop old process (skipped in cold mode)
#   [6/7] replace + clear __pycache__ + restart (scheduled task in cold mode, else same exe as before)
#   [7/7] PING self-check (prints receiver.log tail on failure) + selftest + post-upgrade upload
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = "Stop"
$BASE = "http://T1_IP:8000"
$UP   = "http://T1_IP:8001"

function Send-ToT1([string]$Path, [string]$Name) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "$UP/upload/$Name" -Method POST -InFile $Path -TimeoutSec 30
    Write-Host ("  upload OK  {0} -> {1}" -f $Name, ($r.Content -replace '\s+$',''))
  } catch {
    Write-Host ("  upload FAIL {0}: {1}" -f $Name, $_.Exception.Message)
  }
}

function Write-Fingerprint([string]$Dir, [string]$OutFile) {
  $rep = New-Object System.Collections.ArrayList
  [void]$rep.Add("dir=$Dir")
  [void]$rep.Add("time=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
  foreach ($f in @('win_receiver.py','win_actions.py','win_audio_switch.py','presence_beat.py','receiver.log')) {
    $p = Join-Path $Dir $f
    if (Test-Path $p) {
      try {
        $h = (Get-FileHash $p -Algorithm SHA256).Hash
        $i = Get-Item $p
        [void]$rep.Add(("{0} sha256={1} size={2} mtime={3}" -f $f, $h, $i.Length, $i.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')))
      } catch { [void]$rep.Add("$f HASH-ERROR") }
    } else { [void]$rep.Add("$f MISSING") }
  }
  try {
    $v = (Select-String -Path (Join-Path $Dir 'win_actions.py') -Pattern '^VERSION' -ErrorAction SilentlyContinue | Select-Object -First 1).Line
    [void]$rep.Add("win_actions VERSION line: $v")
    $v2 = (Select-String -Path (Join-Path $Dir 'win_receiver.py') -Pattern 'remotehub-win receiver v' -ErrorAction SilentlyContinue | Select-Object -First 1).Line
    [void]$rep.Add("win_receiver header: $v2")
  } catch {}
  try {
    $t = Get-ScheduledTask -TaskName 'remotehub-win-receiver' -ErrorAction SilentlyContinue
    [void]$rep.Add("scheduled-task state: $(if ($t) { $t.State } else { 'MISSING' })")
  } catch {}
  try {
    [void]$rep.Add("--- processes (python/cmd) ---")
    $pl = Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='pythonw.exe' or Name='cmd.exe'" -ErrorAction SilentlyContinue
    foreach ($pr in $pl) { [void]$rep.Add(("pid={0} {1} | {2}" -f $pr.ProcessId, $pr.Name, $pr.CommandLine)) }
  } catch {}
  try {
    if (Test-Path (Join-Path $Dir 'receiver.log')) {
      [void]$rep.Add("--- receiver.log tail 120 ---")
      $tail = Get-Content (Join-Path $Dir 'receiver.log') -Tail 120 -ErrorAction SilentlyContinue
      foreach ($ln in $tail) { [void]$rep.Add($ln) }
    }
  } catch {}
  $rep | Out-File -Encoding utf8 $OutFile
}

# ---- [1/7] locate receiver dir -------------------------------------------
Write-Host "[1/7] Locating receiver ..."
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

# ---- [2/7] pre-upgrade forensics upload ----------------------------------
# 升级前先取证上传（现行版本指纹 + receiver.log 全文 + 现行 py 源码）—— 任何后续步骤
# 失败都不影响取证已到手; 全部失败仅告警不中断。
Write-Host "[2/7] Pre-upgrade forensics upload to :8001 ..."
$fpPre = Join-Path $env:TEMP "receiver-fingerprint-pre.txt"
Write-Fingerprint $dir $fpPre
Send-ToT1 $fpPre "windows-fingerprint-pre.txt"
if (Test-Path (Join-Path $dir "receiver.log")) {
  Send-ToT1 (Join-Path $dir "receiver.log") "windows-receiver-log-pre.txt"
}
foreach ($f in @('win_receiver.py', 'win_actions.py')) {
  $pf = Join-Path $dir $f
  if (Test-Path $pf) { Send-ToT1 $pf ("windows-pre-" + $f) }
}

# ---- [3/7] python + tkinter + uiautomation --------------------------------
Write-Host "[3/7] Checking python + tkinter + uiautomation ..."
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

# ---- [4/7] download --------------------------------------------------------
Write-Host "[4/7] Downloading receiver v1.11 + actions v1.14 + audio_switch v1.2 + presence_beat v1.0 ..."
try {
  Invoke-WebRequest -Uri "$BASE/win_receiver.py"     -OutFile "$dir\win_receiver.new"     -UseBasicParsing
  Invoke-WebRequest -Uri "$BASE/win_actions.py"      -OutFile "$dir\win_actions.new"      -UseBasicParsing
  Invoke-WebRequest -Uri "$BASE/win_audio_switch.py" -OutFile "$dir\win_audio_switch.new" -UseBasicParsing
  Invoke-WebRequest -Uri "$BASE/presence_beat.py"    -OutFile "$dir\presence_beat.new"    -UseBasicParsing
} catch {
  Write-Host "ERROR: download failed: $($_.Exception.Message)"
  Write-Host "  Is the T1 dist server running? Open http://T1_IP:8000/ in a browser to check."
  $ErrorActionPreference = $oldEAP
  return
}

# ---- [5/7] backup + stop ---------------------------------------------------
Write-Host "[5/7] Backup + stopping old receiver ..."
$TS = Get-Date -Format "yyyyMMdd-HHmmss"
if (Test-Path "$dir\win_receiver.py")     { Copy-Item "$dir\win_receiver.py"     "$dir\win_receiver.py.bak-$TS"     -Force }
if (Test-Path "$dir\win_actions.py")      { Copy-Item "$dir\win_actions.py"      "$dir\win_actions.py.bak-$TS"      -Force }
if (Test-Path "$dir\win_audio_switch.py") { Copy-Item "$dir\win_audio_switch.py" "$dir\win_audio_switch.py.bak-$TS" -Force }
if (Test-Path "$dir\presence_beat.py")    { Copy-Item "$dir\presence_beat.py"    "$dir\presence_beat.py.bak-$TS"    -Force }
if ($p) {
  Stop-Process -Id $p.ProcessId -Force
  Start-Sleep -Milliseconds 800
} else {
  Write-Host "  (cold update: nothing to stop)"
}

# ---- [6/7] replace + restart ----------------------------------------------
Write-Host "[6/7] Replacing files and restarting ..."
Move-Item -Force "$dir\win_receiver.new"     "$dir\win_receiver.py"
Move-Item -Force "$dir\win_actions.new"      "$dir\win_actions.py"
Move-Item -Force "$dir\win_audio_switch.new" "$dir\win_audio_switch.py"
Move-Item -Force "$dir\presence_beat.new"    "$dir\presence_beat.py"
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

# ---- [7/7] PING + selftest + post-upgrade upload ---------------------------
Write-Host "[7/7] Self-check PING :8788 ..."
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

# ---- post-upgrade forensics upload ---------------------------------------
Write-Host ""
Write-Host "Post-upgrade upload to :8001 ..."
$fpPost = Join-Path $env:TEMP "receiver-fingerprint-post.txt"
Write-Fingerprint $dir $fpPost
Send-ToT1 $fpPost "windows-fingerprint-post.txt"
if (Test-Path (Join-Path $dir "receiver.log")) {
  Send-ToT1 (Join-Path $dir "receiver.log") "windows-receiver-log-post.txt"
}
$sf = Join-Path $dir "selftest.log"
if (Test-Path $sf) { Send-ToT1 $sf "windows-selftest.log" }
$mr = Join-Path $dir "state\mouse-report.json"
if (Test-Path $mr) { Send-ToT1 $mr "windows-mouse-report.json" }

$ErrorActionPreference = $oldEAP
Write-Host ""
Write-Host "DONE (receiver v1.10 + win_actions v1.14 + audio_switch v1.2)."
Write-Host "Backups: *.bak-$TS in $dir"
Write-Host "Rollback: stop receiver, restore .bak files, start receiver again."
Write-Host ""
Write-Host "DEVICE SWITCH (v1.10 + v1.14): tap the power key 1/2/3 times = switch target to ATV / Mac / Windows;"
Write-Host "  when this machine is the (old or new) target you get a HUD overlay; long-press power still closes the app."
Write-Host ""
Write-Host "MOUSE mode (v1.9 + v1.13): OK key CLICK now actually works (SendInput type-class fix);"
Write-Host "  long-press the LIVE key (#41) toggles the mode (HUD: 鼠标模式/键盘模式);"
Write-Host "  dpad glides the cursor (speed resets per press - fine micro-adjust works);"
Write-Host "  OK = left click (long-press = right click); vol +/- = scroll; BACK (#158) exits;"
Write-Host "  home key is passed through inside the mode (APP:CYCLE / long = PICK); power = multi-tap switch / long = CLOSE."
Write-Host ""
Write-Host "APP:PICK picker v2.6: icon grid; light-gray frosted palette aligned with Mac (system-blue selection + near-black text); selected-cell icon fused (dual-backdrop tiles); grid-direction navigation; UWP real icons; long-name marquee; clean names."
Write-Host "  arrows move, OK open, BACK/ESC cancel, 10 s auto-cancel (crash fix retained)."
Write-Host "Remote key binding: open http://T1_IP:8765/keymap (tab: Windows)."
Write-Host "  Actions: CLICK / FOCUS_INPUT / APP:CYCLE / APP:PICK / APP:<exe name> / URL:<url> / RUN:<cmd>."
Write-Host "Mic note: WeChat IME microphone must be set to 'Default Device' ONCE (see TASK-mic-switch.md)."
