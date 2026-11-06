<#
.SYNOPSIS
    BITDEX Windows MT5 Gateway Automated Production Deployment Script (Phase 4.3)
.DESCRIPTION
    Automates the installation, environment configuration, Windows service registration,
    firewall rule creation, and health verification for the BITDEX Exness MT5 Gateway Daemon.
.NOTES
    Must be executed in an elevated PowerShell session (Run as Administrator) on Windows Server 2022/2025.
#>

[CmdletBinding()]
param(
    [string]$GatewayPort = "8095",
    [string]$StagingIP = "169.58.218.168",
    [string]$TunnelIP = "10.88.0.1",
    [string]$AuthToken = ""
)

$ErrorActionPreference = "Stop"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "BITDEX WINDOWS MT5 GATEWAY PRODUCTION INSTALLER (Phase 4.3)" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# 1. Check Administrator Privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "CRITICAL: This installer must be executed from an elevated PowerShell terminal (Run as Administrator)."
    exit 1
}
Write-Host "[✓] Elevated Administrator permissions confirmed." -ForegroundColor Green

# 2. Check Python 64-bit Installation
try {
    $pythonVer = python --version 2>&1
    Write-Host "[✓] Detected Python: $pythonVer" -ForegroundColor Green
    
    # Check 64-bit
    $is64Bit = python -c "import struct; print(struct.calcsize('P') * 8)"
    if ($is64Bit.Trim() -ne "64") {
        Write-Error "CRITICAL: Python must be 64-bit to link with MetaTrader5. Found $is64Bit-bit."
        exit 1
    }
    Write-Host "[✓] 64-bit Python architecture verified." -ForegroundColor Green
} catch {
    Write-Error "CRITICAL: Python is not installed or not in system PATH. Install Python 3.11 or 3.12 64-bit."
    exit 1
}

# 3. Verify Exness MT5 Desktop Terminal Installation
$terminalPaths = @(
    "C:\Program Files\Exness MetaTrader 5\terminal64.exe",
    "C:\Program Files\MetaTrader 5\terminal64.exe",
    "C:\ExnessMT5\terminal64.exe",
    "C:\MT5\terminal64.exe"
)
$foundTerminal = $null
foreach ($path in $terminalPaths) {
    if (Test-Path $path) {
        $foundTerminal = $path
        break
    }
}

if ($foundTerminal) {
    Write-Host "[✓] Located MetaTrader 5 Terminal executable at: $foundTerminal" -ForegroundColor Green
} else {
    Write-Warning "[!] Exness MT5 terminal not found in default paths. Ensure terminal64.exe is installed before starting gateway."
}

# 4. Install Required Python Packages
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }
$reqPath = Join-Path $scriptDir "requirements.txt"

if (Test-Path $reqPath) {
    Write-Host "[*] Installing Python dependencies from requirements.txt..." -ForegroundColor Yellow
    python -m pip install --upgrade pip
    python -m pip install -r $reqPath
    Write-Host "[✓] Python dependencies installed successfully." -ForegroundColor Green
} else {
    Write-Warning "[!] requirements.txt not found in $scriptDir. Installing baseline packages directly..."
    python -m pip install "MetaTrader5>=5.0.45" "fastapi>=0.110.0" "uvicorn[standard]>=0.28.0" "pydantic>=2.6.0" "cryptography>=42.0.0"
}

# 5. Configure Authentication Token
if (-not $AuthToken) {
    $existingToken = [Environment]::GetEnvironmentVariable("EXNESS_GATEWAY_AUTH_TOKEN", "Machine")
    if ($existingToken -and $existingToken.Length -ge 32) {
        $AuthToken = $existingToken
        Write-Host "[✓] Using existing machine EXNESS_GATEWAY_AUTH_TOKEN." -ForegroundColor Green
    } else {
        # Generate cryptographically strong 64-character token
        $AuthToken = python -c "import secrets; print(secrets.token_hex(32))"
        [Environment]::SetEnvironmentVariable("EXNESS_GATEWAY_AUTH_TOKEN", $AuthToken.Trim(), "Machine")
        Write-Host "[✓] Generated and saved strong EXNESS_GATEWAY_AUTH_TOKEN to Machine environment." -ForegroundColor Green
    }
} else {
    [Environment]::SetEnvironmentVariable("EXNESS_GATEWAY_AUTH_TOKEN", $AuthToken.Trim(), "Machine")
    Write-Host "[✓] Configured provided EXNESS_GATEWAY_AUTH_TOKEN in Machine environment." -ForegroundColor Green
}

# Configure IP & Port settings (Bind exclusively to private WireGuard tunnel and localhost)
$BindHost = "10.88.0.2"
[Environment]::SetEnvironmentVariable("EXNESS_GATEWAY_PORT", $GatewayPort, "Machine")
[Environment]::SetEnvironmentVariable("EXNESS_GATEWAY_HOST", $BindHost, "Machine")
[Environment]::SetEnvironmentVariable("ALLOWED_CLIENT_IPS", "127.0.0.1,::1,$TunnelIP,10.88.0.2", "Machine")

# 6. Configure Windows Firewall Inbound Rules (Restrict strictly to WireGuard private tunnel)
Write-Host "[*] Configuring Windows Firewall rule for Port $GatewayPort..." -ForegroundColor Yellow
$firewallRuleName = "BITDEX_MT5_GATEWAY_INGRESS"
Remove-NetFirewallRule -DisplayName $firewallRuleName -ErrorAction SilentlyContinue

New-NetFirewallRule -DisplayName $firewallRuleName `
    -Direction Inbound `
    -LocalPort $GatewayPort `
    -Protocol TCP `
    -Action Allow `
    -RemoteAddress "$TunnelIP,127.0.0.1" `
    -Description "Allows authorized Linux staging backend over private WireGuard tunnel (10.88.0.1) to reach BITDEX MT5 Gateway"

Write-Host "[✓] Windows Firewall rule '$firewallRuleName' created. Access restricted strictly to private WireGuard tunnel ($TunnelIP)." -ForegroundColor Green

# 7. Register Persistent Windows Service (BitdexMT5Gateway) with Automatic Startup & Failure Recovery
$serviceName = "BitdexMT5Gateway"
$serverPy = Join-Path $scriptDir "mt5_gateway_server.py"
$pythonExe = (Get-Command python).Source
$nssmExe = Join-Path $scriptDir "nssm.exe"

if (Test-Path $nssmExe) {
    Write-Host "[*] Registering persistent Windows service '$serviceName' via NSSM..." -ForegroundColor Yellow
    & $nssmExe stop $serviceName 2>$null
    & $nssmExe remove $serviceName confirm 2>$null
    & $nssmExe install $serviceName $pythonExe "`"$serverPy`""
    & $nssmExe set $serviceName AppDirectory $scriptDir
    & $nssmExe set $serviceName Start SERVICE_AUTO_START
    & $nssmExe set $serviceName AppExit Default Restart
    & $nssmExe set $serviceName AppRestartDelay 5000
    & sc.exe failure $serviceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
    & $nssmExe start $serviceName
    Write-Host "[✓] Windows service '$serviceName' registered and started (SERVICE_AUTO_START + Failure Recovery)." -ForegroundColor Green
} else {
    Write-Host "[*] Registering persistent startup scheduled task / service wrapper for '$serviceName'..." -ForegroundColor Yellow
    $action = New-ScheduledTaskAction -Execute $pythonExe -Argument "`"$serverPy`"" -WorkingDirectory $scriptDir
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $serviceName -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
    Write-Host "[✓] Persistent startup task '$serviceName' registered with automatic restart on failure." -ForegroundColor Green
}

# 8. Self-Test & Diagnostic
Write-Host "[*] Starting test verification of gateway on port $GatewayPort..." -ForegroundColor Yellow
$env:EXNESS_GATEWAY_AUTH_TOKEN = $AuthToken
$env:EXNESS_GATEWAY_PORT = $GatewayPort
$env:EXNESS_GATEWAY_HOST = "127.0.0.1"
$env:STRICT_STARTUP_CHECK = "true"

$testJob = Start-Process python -ArgumentList "$serverPy" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

try {
    $headers = @{ "X-Gateway-Auth-Token" = $AuthToken }
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$GatewayPort/health" -Headers $headers -TimeoutSec 5
    Write-Host "[✓] Gateway Health Self-Test PASSED!" -ForegroundColor Green
    Write-Host "    Service: $($response.service) v$($response.version)" -ForegroundColor Green
    Write-Host "    MT5 Available: $($response.mt5_available)" -ForegroundColor Green
    Write-Host "    Terminal Connected: $($response.terminal_connected)" -ForegroundColor Green
} catch {
    Write-Warning "[!] Self-test health check did not respond immediately. Check MT5 terminal status."
} finally {
    Stop-Process -Id $testJob.Id -Force -ErrorAction SilentlyContinue
}

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "WINDOWS MT5 GATEWAY CONFIGURATION COMPLETE" -ForegroundColor Cyan
Write-Host "Auth Token: $($AuthToken.Substring(0, 8))...$($AuthToken.Substring($AuthToken.Length - 4)) [MASKED FOR SECURITY]" -ForegroundColor Yellow
Write-Host "Configured Bind Host: $BindHost : $GatewayPort" -ForegroundColor Yellow
Write-Host "Private Tunnel Allowlist: $TunnelIP, 127.0.0.1" -ForegroundColor Yellow
Write-Host "Service Persistence: $serviceName (Auto-Start + Failure Recovery Enabled)" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

