param(
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Gateway = Join-Path $Root 'carla-service\ghostdriver'
$GatewayPython = Join-Path $Gateway '.venv\Scripts\python.exe'
$RaftPython = Join-Path $Root 'raft-env\Scripts\python.exe'
$RaftCheckpoint = Join-Path $Gateway 'RAFT\models\raft-small.pth'
$CarlaRoot = if ($env:CARLA_ROOT) { $env:CARLA_ROOT } else { 'D:\WindowsNoEditor' }
$CarlaExe = Join-Path $CarlaRoot 'CarlaUE4.exe'

function ConvertTo-PowerShellLiteral([string]$Value) {
    return "'" + $Value.Replace("'", "''") + "'"
}

function Test-TcpPort([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(250)) {
            return $false
        }
        $client.EndConnect($connect)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-BackendHealth {
    try {
        $response = Invoke-WebRequest -Uri 'http://localhost:4000/api/health' -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200 -and ($response.Content | ConvertFrom-Json).success
    } catch {
        return $false
    }
}

function Test-FrontendHealth {
    try {
        $response = Invoke-WebRequest -Uri 'http://localhost:5173/' -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-AiPrediction {
    try {
        $health = (Invoke-WebRequest -Uri 'http://localhost:4000/api/health' -UseBasicParsing -TimeoutSec 2).Content | ConvertFrom-Json
        return $health.services.aiPrediction.status -eq 'connected'
    } catch {
        return $false
    }
}

function Start-CommandWindow([string]$Title, [string]$WorkingDirectory, [string]$Command) {
    $titleLiteral = ConvertTo-PowerShellLiteral $Title
    $directoryLiteral = ConvertTo-PowerShellLiteral $WorkingDirectory
    $windowCommand = "`$Host.UI.RawUI.WindowTitle = $titleLiteral; Set-Location -LiteralPath $directoryLiteral; $Command"
    return Start-Process -FilePath 'powershell.exe' -ArgumentList @(
        '-NoExit',
        '-NoProfile',
        '-Command',
        $windowCommand
    ) -PassThru
}

function Wait-ForPort(
    [int]$Port,
    [int]$TimeoutSeconds,
    [string]$ServiceName,
    [System.Diagnostics.Process]$Process = $null
) {
    for ($second = 0; $second -lt $TimeoutSeconds; $second++) {
        if (Test-TcpPort $Port) {
            return $true
        }
        if ($Process) {
            $Process.Refresh()
            if ($Process.HasExited) {
                Write-Host "$ServiceName exited before opening port $Port (exit code $($Process.ExitCode))." -ForegroundColor Red
                return $false
            }
        }
        Start-Sleep -Seconds 1
    }
    Write-Host "$ServiceName did not open port $Port within $TimeoutSeconds seconds." -ForegroundColor Red
    return $false
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'Node.js/npm is not installed or is not on PATH. Install Node.js LTS and try again.'
}
if (-not (Test-Path $CarlaExe)) {
    throw "CARLA executable not found at '$CarlaExe'. Set CARLA_ROOT to the folder containing CarlaUE4.exe."
}
if (-not (Test-Path $GatewayPython)) {
    throw "Gateway Python not found at '$GatewayPython'. The CARLA gateway needs its Python 3.7 .venv."
}
if (-not (Test-Path $RaftPython) -or -not (Test-Path $RaftCheckpoint)) {
    throw 'RAFT environment or raft-small.pth checkpoint is missing. Check raft-env and carla-service\ghostdriver\RAFT\models.'
}
if (-not (Test-Path (Join-Path $Gateway 'carla_gateway.py'))) {
    throw "CARLA gateway script not found in '$Gateway'."
}

Write-Host 'Checking Python environments...' -ForegroundColor Cyan
& $GatewayPython -c 'import carla, socketio, cv2, numpy'
if ($LASTEXITCODE -ne 0) {
    throw 'The gateway .venv is missing CARLA, python-socketio, OpenCV, or NumPy. Install the CARLA 0.9.15 wheel and gateway dependencies into carla-service\ghostdriver\.venv.'
}
& $RaftPython -c 'import torch, cv2, numpy'
if ($LASTEXITCODE -ne 0) {
    throw 'The raft-env is missing PyTorch, OpenCV, or NumPy.'
}
Write-Host 'Gateway and RAFT Python dependencies are ready.' -ForegroundColor Green

if (-not (Test-Path (Join-Path $Backend 'node_modules'))) {
    Write-Host 'Installing backend dependencies...' -ForegroundColor Cyan
    Push-Location $Backend
    try {
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw 'Backend npm install failed.' }
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    Write-Host 'Installing frontend dependencies...' -ForegroundColor Cyan
    Push-Location $Frontend
    try {
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw 'Frontend npm install failed.' }
    } finally {
        Pop-Location
    }
}

if ($CheckOnly) {
    Write-Host 'Startup checks passed. Run .\start.ps1 to start all services.' -ForegroundColor Green
    exit 0
}

if (Test-BackendHealth) {
    Write-Host 'Backend already running and healthy.' -ForegroundColor Green
} else {
    if (Test-TcpPort 4000) {
        throw 'Port 4000 is occupied by a service that did not pass the Ghost Driver health check.'
    }
    Write-Host 'Starting backend...' -ForegroundColor Cyan
    $npm = (Get-Command npm.cmd).Source
    $npmLiteral = ConvertTo-PowerShellLiteral $npm
    Start-CommandWindow 'Ghost Driver Backend' $Backend "& $npmLiteral run dev" | Out-Null
    if (-not (Wait-ForPort 4000 30 'Backend') -or -not (Test-BackendHealth)) {
        throw 'Backend did not become healthy. Check the Ghost Driver Backend terminal.'
    }
}

if (Test-FrontendHealth) {
    Write-Host 'Frontend already running and healthy.' -ForegroundColor Green
} else {
    if (Test-TcpPort 5173) {
        throw 'Port 5173 is occupied by a service that did not return the dashboard.'
    }
    Write-Host 'Starting frontend...' -ForegroundColor Cyan
    $npm = (Get-Command npm.cmd).Source
    $npmLiteral = ConvertTo-PowerShellLiteral $npm
    Start-CommandWindow 'Ghost Driver Frontend' $Frontend "& $npmLiteral run dev -- --host 0.0.0.0" | Out-Null
    if (-not (Wait-ForPort 5173 30 'Frontend') -or -not (Test-FrontendHealth)) {
        throw 'Frontend did not become ready. Check the Ghost Driver Frontend terminal.'
    }
}

if (Test-TcpPort 2000) {
    Write-Host 'CARLA RPC port 2000 is already available.' -ForegroundColor Green
} else {
    $runningCarla = Get-Process -Name 'CarlaUE4' -ErrorAction SilentlyContinue
    $carlaProcess = $null
    if (-not $runningCarla) {
        Write-Host 'Starting CARLA...' -ForegroundColor Cyan
        $carlaProcess = Start-Process -FilePath $CarlaExe -WorkingDirectory $CarlaRoot -ArgumentList @(
            '-dx11',
            '-quality-level=Low',
            '-windowed',
            '-nosound',
            '-ResX=640',
            '-ResY=480'
        ) -PassThru
    } else {
        Write-Host 'CARLA is already running; waiting for its RPC port...' -ForegroundColor Yellow
    }
    if (-not (Wait-ForPort 2000 120 'CARLA' $carlaProcess)) {
        throw 'CARLA did not become ready on port 2000. Check the CARLA window and GPU driver.'
    }
}

$gatewayProcesses = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' or Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf('carla_gateway.py', [StringComparison]::OrdinalIgnoreCase) -ge 0 })
if ($gatewayProcesses.Count -gt 0) {
    Write-Host 'CARLA gateway is already running.' -ForegroundColor Green
} else {
    if (Test-TcpPort 5001) {
        throw 'Port 5001 is occupied, but no CARLA gateway process was found.'
    }
    Write-Host 'Starting CARLA gateway (it starts the RAFT worker automatically)...' -ForegroundColor Cyan
    $pythonLiteral = ConvertTo-PowerShellLiteral $GatewayPython
    $scriptLiteral = ConvertTo-PowerShellLiteral (Join-Path $Gateway 'carla_gateway.py')
    Start-CommandWindow 'Ghost Driver CARLA Gateway' $Gateway "& $pythonLiteral $scriptLiteral" | Out-Null
}

if (-not (Wait-ForPort 5001 180 'CARLA camera')) {
    throw 'The gateway did not start its camera server. Check the CARLA Gateway terminal for CARLA, camera, or GPU errors.'
}
if (-not (Wait-ForPort 5002 90 'RAFT worker')) {
    throw 'The RAFT worker did not become ready. Check the CARLA Gateway terminal and raft-env.'
}

$predictionReady = $false
for ($second = 0; $second -lt 120; $second++) {
    if (Test-AiPrediction) {
        $predictionReady = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $predictionReady) {
    Write-Host 'Camera and RAFT are running, but the gateway has not reported a completed prediction yet.' -ForegroundColor Yellow
    Write-Host 'Check the CARLA Gateway terminal for "[gateway] prediction failed" messages.' -ForegroundColor Yellow
} else {
    Write-Host 'Video prediction is ready.' -ForegroundColor Green
}

Write-Host ''
Write-Host 'Ghost Driver is ready.' -ForegroundColor Green
Write-Host 'Dashboard:       http://localhost:5173' -ForegroundColor Green
Write-Host 'Vehicle webcam:  http://localhost:5173/vehicle-sim.html' -ForegroundColor Green
Write-Host 'Backend health:  http://localhost:4000/api/health' -ForegroundColor Green
Write-Host 'CARLA camera:    http://localhost:5001/stream.mjpg' -ForegroundColor Green
Write-Host ''
Write-Host 'Keep the CARLA and service terminal windows open. Press Ctrl+C in each service terminal to stop it.' -ForegroundColor Yellow
