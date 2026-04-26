$scriptPath = Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) '..\run_backend.ps1')
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors) {
    $errors | ForEach-Object { $_.ToString() }
    exit 1
} else {
    Write-Output 'NO_ERRORS'
}
