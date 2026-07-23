[CmdletBinding()]
param(
    [string]$Model = "gemma4",
    [string]$SpeechModel = "small",
    [switch]$SkipModelPull,
    [switch]$SkipSpeechModelDownload,
    [switch]$SkipOllamaInstall,
    [switch]$InstallFfmpeg
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$modelWasExplicit = $PSBoundParameters.ContainsKey("Model")

if ([string]::IsNullOrWhiteSpace($Model)) {
    throw "Model cannot be empty."
}
if ([string]::IsNullOrWhiteSpace($SpeechModel)) {
    throw "SpeechModel cannot be empty."
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-OllamaApi {
    try {
        Invoke-RestMethod `
            -Uri "http://127.0.0.1:11434/api/tags" `
            -Method Get `
            -TimeoutSec 2 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

Push-Location $projectRoot
try {
    Write-Step "Checking Python"
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found. Install Python 3.10 or newer from https://python.org."
    }
    $pythonExecutable = $pythonCommand.Source

    & $pythonExecutable -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Tubby requires Python 3.10 or newer."
    }

    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step "Creating .venv"
        & $pythonExecutable -m venv $venvPath
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the Python virtual environment."
        }
    }

    Write-Step "Installing Tubby and Python dependencies"
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Could not upgrade pip."
    }
    & $venvPython -m pip install -e $projectRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Could not install Tubby."
    }

    if (-not $SkipSpeechModelDownload) {
        Write-Step "Downloading local speech model $SpeechModel"
        & $venvPython `
            -c "import sys; from tubby.media_transcript import download_transcription_model; download_transcription_model(sys.argv[1])" `
            $SpeechModel
        if ($LASTEXITCODE -ne 0) {
            throw "Could not download speech model '$SpeechModel'."
        }
    }

    Write-Step "Checking Ollama"
    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
    $ollamaExecutable = if ($ollamaCommand) { $ollamaCommand.Source } else { $null }
    if (-not $ollamaCommand -and -not $SkipOllamaInstall) {
        $wingetCommand = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $wingetCommand) {
            throw "Ollama is not installed and winget is unavailable. Install Ollama from https://ollama.com/download/windows."
        }

        Write-Step "Installing Ollama"
        & $wingetCommand.Source install `
            --id Ollama.Ollama `
            --exact `
            --accept-package-agreements `
            --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "winget could not install Ollama."
        }

        $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
        if ($ollamaCommand) {
            $ollamaExecutable = $ollamaCommand.Source
        }
        else {
            $installedOllama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
            if (Test-Path -LiteralPath $installedOllama) {
                $ollamaExecutable = $installedOllama
            }
        }
    }

    if (-not $ollamaExecutable) {
        throw "Ollama was not found. Install it from https://ollama.com/download/windows and rerun setup.ps1."
    }

    if (-not (Test-OllamaApi)) {
        Write-Step "Starting the local Ollama service"
        Start-Process `
            -FilePath $ollamaExecutable `
            -ArgumentList "serve" `
            -WindowStyle Hidden | Out-Null

        $ollamaReady = $false
        foreach ($attempt in 1..20) {
            Start-Sleep -Seconds 1
            if (Test-OllamaApi) {
                $ollamaReady = $true
                break
            }
        }
        if (-not $ollamaReady) {
            throw "Ollama did not start at http://127.0.0.1:11434."
        }
    }

    Write-Step "Choosing an Ollama report model"
    $chooserArguments = @(
        "-m",
        "tubby.ollama_models",
        "choose-setup",
        "--preferred",
        $Model
    )
    if ($modelWasExplicit) {
        $chooserArguments += "--explicit"
    }
    if ($SkipModelPull) {
        $chooserArguments += "--no-install"
    }

    $selectionOutput = & $venvPython @chooserArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Could not choose an Ollama report model."
    }
    $selectionLine = [string](@($selectionOutput)[-1])
    $selectionParts = $selectionLine -split "`t"
    if ($selectionParts.Count -lt 2) {
        throw "Tubby returned an invalid Ollama model selection."
    }
    $Model = $selectionParts[0]
    $modelState = $selectionParts[1]
    if ($modelState -notin @("installed", "missing")) {
        throw "Tubby returned an unknown Ollama model state '$modelState'."
    }

    if ($modelState -eq "missing") {
        Write-Step "Downloading Ollama model $Model"
        & $ollamaExecutable pull $Model
        if ($LASTEXITCODE -ne 0) {
            throw "Ollama could not download model '$Model'."
        }
    }
    else {
        Write-Step "Using installed Ollama model $Model"
    }

    if ($InstallFfmpeg -and -not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        $wingetCommand = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $wingetCommand) {
            throw "winget is required to install FFmpeg automatically."
        }
        Write-Step "Installing FFmpeg for downloader CLI audio and high-resolution video"
        & $wingetCommand.Source install `
            --id Gyan.FFmpeg `
            --exact `
            --accept-package-agreements `
            --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "winget could not install FFmpeg."
        }
    }

    Write-Host ""
    Write-Host "Tubby setup is complete." -ForegroundColor Green
    Write-Host "Report model: $Model"
    Write-Host "Start the desktop app with:"
    Write-Host "  .\.venv\Scripts\python -m tubby"
    Write-Host ""
    Write-Host "The downloader CLI remains available with:"
    Write-Host "  .\.venv\Scripts\tubby --help"
}
finally {
    Pop-Location
}
