# ============================================================
# Windows one-time setup (ASCII only, run as ADMINISTRATOR)
#   1) Install & enable OpenSSH Server (port 22)
#   2) Install deploy public key (passwordless login)
#   3) Print a host report (user / OS / IPv4 / Python / IME)
# Usage (Admin PowerShell):
#   irm http://T1_IP:8000/setup-windows.ps1 | iex
# ============================================================
$ErrorActionPreference = 'Continue'

# --- 1) OpenSSH Server ---
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd

# --- 2) Firewall rule for port 22 ---
if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}

# --- 3) Deploy public key (admin user path) ---
$pub = 'ssh-ed25519 REPLACE-WITH-YOUR-OWN-DEPLOY-KEY windows-deploy'
$f = "$env:ProgramData\ssh\administrators_authorized_keys"
Add-Content -Path $f -Value $pub -Encoding ascii
icacls $f /inheritance:r /grant:r 'SYSTEM:F' /grant:r 'BUILTIN\Administrators:F' | Out-Null
Restart-Service sshd

# --- 4) Report ---
Write-Output ''
Write-Output '===== Windows SETUP REPORT ====='
Write-Output ('whoami  : ' + (whoami))
$os = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
Write-Output ('OS      : ' + $os.ProductName + ' / ' + $os.DisplayVersion + ' / build ' + $os.CurrentBuild)
Write-Output ('host    : ' + $env:COMPUTERNAME)
Write-Output ('sshd    : ' + (Get-Service sshd).Status)
Write-Output '--- IPv4 ---'
ipconfig | Select-String 'IPv4' | ForEach-Object { Write-Output ('  ' + $_.Line.Trim()) }
Write-Output '--- Python ---'
if (Get-Command python -ErrorAction SilentlyContinue) { Write-Output ('  ' + ((python --version 2>&1) -join ' ')) } else { Write-Output '  python: NOT FOUND' }
if (Get-Command py -ErrorAction SilentlyContinue) { Write-Output '  py launcher: FOUND' }
Write-Output '--- IME (WeType / WeChat / Tencent) ---'
$hits = @()
foreach ($root in 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*') {
  $hits += Get-ItemProperty $root -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'WeType|Weixin|WeChat|Tencent' } | Select-Object -ExpandProperty DisplayName
}
if ($hits.Count) { $hits | ForEach-Object { Write-Output ('  ' + $_) } } else { Write-Output '  no match found' }
Write-Output '===== DONE ====='
