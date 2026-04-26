<#
Simple runner for the backend (PowerShell)

Performs:
 - loads .env (if present)
 - creates a virtualenv `.venv` if missing
 - activates venv and installs requirements
 - initializes DB via `python models.py`
 - runs uvicorn on 0.0.0.0:8000
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host '=== run_backend.ps1 ==='

# Dir containing this script
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

# Load .env if present
$envFile = Join-Path $scriptDir '.env'
if (Test-Path $envFile) {
    Write-Host 'Loading variables from' $envFile
    Get-Content $envFile | ForEach-Object {
        if ($_ -and -not $_.StartsWith('#')) {
            $parts = $_ -split '=', 2
            if ($parts.Length -eq 2) {
                $name  = $parts[0].Trim()
                $value = $parts[1].Trim()
                # If value is quoted (matching opening and closing ' or "), unwrap it.
                if ($value.Length -ge 2) {
                    $first = $value.Substring(0,1)
                    $last = $value.Substring($value.Length - 1, 1)
                    if ((($first -eq [char]34) -and ($last -eq [char]34)) -or (($first -eq [char]39) -and ($last -eq [char]39))) {
                        $value = $value.Substring(1, $value.Length - 2)
                    }
                }
                [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
            }
        }
    }
} else {
    Write-Host $envFile 'not found; skipping.'
}

# Create virtualenv if missing
$venvDir = Join-Path $scriptDir '.venv'
if (-not (Test-Path $venvDir)) {
    Write-Host 'Creating virtualenv .venv'
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { Write-Error "python -m venv a échoué (code $LASTEXITCODE)"; exit $LASTEXITCODE }   # ✅ Correction 2
}

# ✅ Correction 3 : chemin cross-platform
# Détecte Windows de façon compatible avec PowerShell 5.1 et 7
$is_windows_env = $false
if ($env:OS -and $env:OS -eq 'Windows_NT') { $is_windows_env = $true }
# Choisit le script d'activation approprié
if ($is_windows_env) {
    $activateScript = Join-Path $venvDir 'Scripts\\Activate.ps1'
} else {
    # sous Unix le script d'activation est 'bin/activate' (bash); PowerShell non interactif peut ignorer
    $activateScript = Join-Path $venvDir 'bin/activate'
}
if (Test-Path $activateScript) {
    Write-Host 'Activating venv and installing requirements'
    . $activateScript
    python -m pip install --upgrade pip
    $reqFile = Join-Path $scriptDir 'requirements.txt'
    if (Test-Path $reqFile) {
        python -m pip install -r $reqFile
    } else {
        Write-Host $reqFile 'not found; skipping requirements install.'
    }
} else {
    Write-Host 'Activation script not found at' $activateScript '; continuing without activation.'
}

Write-Host 'Initializing database via python models.py'
python models.py
if ($LASTEXITCODE -ne 0) { Write-Error "models.py a échoué (code $LASTEXITCODE)"; exit $LASTEXITCODE }   # ✅ Correction 2

Write-Host 'Starting uvicorn on 0.0.0.0:8000'
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000




 