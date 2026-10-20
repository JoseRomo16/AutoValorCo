#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Windows equivalent of the Makefile targets (GNU make is not available on Windows).
.EXAMPLE
    .\make.ps1 lint
    .\make.ps1 serve -Port 8080
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'scrape', 'enrich', 'pull-history', 'push-history',
        'transform', 'train', 'export-model', 'results', 'serve', 'web', 'web-build', 'web-lint',
        'test', 'lint', 'format', 'docker-build',
        'docker-up', 'clean')]
    [string]$Target = 'help',

    [string]$ApiHost = '127.0.0.1',
    [int]$Port = 8000,
    [int]$Pages = 10,
    # Listings fetched per enrichment run. A polite pause makes this a time budget:
    # roughly 35 minutes for 500.
    [int]$Budget = 500,
    # Optuna budget per tree model and vertical. Zero skips the search; -1 leaves the
    # per-model defaults in place (LightGBM 40, CatBoost 20).
    [int]$Trials = -1
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Invoke-Step {
    param([Parameter(Mandatory)][string[]]$Command)
    Write-Host "> $($Command -join ' ')" -ForegroundColor Cyan
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) { throw "$($Command[0]) exited with code $LASTEXITCODE" }
}

function Invoke-NpmStep {
    <#
    .SYNOPSIS
    Run an npm script from frontend/.

    .DESCRIPTION
    Separate from Invoke-Step because npm on Windows is a .cmd shim, and Windows
    PowerShell splices a splatted argument array into a single string before handing it
    over: `& npm @('run', 'lint')` reaches npm as the one unknown command "run lint".
    Passing the whole line through cmd avoids the splice entirely.
    #>
    param([Parameter(Mandatory)][string]$Arguments)
    Write-Host "> npm $Arguments" -ForegroundColor Cyan
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try {
        cmd /c "npm $Arguments"
        if ($LASTEXITCODE -ne 0) { throw "npm $Arguments exited with code $LASTEXITCODE" }
    }
    finally {
        Pop-Location
    }
}

switch ($Target) {
    'help' {
        Write-Host 'AutoValor CO - available targets:'
        Write-Host '  setup          Install Python, browser and frontend dependencies'
        Write-Host '  scrape         Capture TuCarro listings into data/bronze'
        Write-Host '  enrich         Read the detail page of motorcycles without one (-Budget N)'
        Write-Host '  pull-history   Bring the published captures into data/bronze'
        Write-Host '  push-history   Publish the local captures to the data branch'
        Write-Host '  transform      Run dbt (silver and gold) and the Pandera validations'
        Write-Host '  train          Train the models and log them to MLflow (-Trials N)'
        Write-Host '  export-model   Train the served model into artifacts/models/'
        Write-Host '  results        Estimate the economic results and export them to docs/'
        Write-Host '  serve          Run the API locally with autoreload'
        Write-Host '  web            Run the front end in development'
        Write-Host '  web-build      Build the static export into frontend/out'
        Write-Host '  web-lint       Lint and type-check the front end'
        Write-Host '  test           Run the test suite with coverage'
        Write-Host '  lint           Run ruff (lint + format check) and mypy'
        Write-Host '  format         Apply ruff formatting and autofixes'
        Write-Host '  docker-build   Build the API image'
        Write-Host '  docker-up      Start the API with docker compose'
        Write-Host '  clean          Remove caches and coverage artifacts'
    }
    'setup' {
        Invoke-Step 'uv', 'sync'
        Invoke-Step 'uv', 'run', 'playwright', 'install', 'chromium'
        Invoke-Step 'uv', 'run', 'pre-commit', 'install'
        Invoke-NpmStep 'install'
    }
    'scrape' {
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.ingest.cli',
        '--vehicle-type', 'all', '--pages', "$Pages"
    }
    'enrich' {
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.ingest.detail_cli',
        '--budget', "$Budget"
    }
    'pull-history' {
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.ingest.history', 'pull'
    }
    'push-history' {
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.ingest.history', 'push'
    }
    'transform' {
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.quality.cli', '--stage', 'bronze'
        Invoke-Step 'uv', 'run', 'dbt', 'build', '--project-dir', 'dbt', '--profiles-dir', 'dbt'
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.quality.cli',
        '--stage', 'silver', '--stage', 'gold'
    }
    'train' {
        $trainCommand = @('uv', 'run', 'python', '-m', 'autovalor.models.train')
        if ($Trials -ge 0) { $trainCommand += @('--trials', "$Trials") }
        Invoke-Step $trainCommand
    }
    'export-model' {
        $exportCommand = @('uv', 'run', 'python', '-m', 'autovalor.models.export')
        if ($Trials -ge 0) { $exportCommand += @('--trials', "$Trials") }
        Invoke-Step $exportCommand
    }
    'results' {
        $resultsCommand = @('uv', 'run', 'python', '-m', 'autovalor.analysis.cli')
        if ($Trials -ge 0) { $resultsCommand += @('--trials', "$Trials") }
        Invoke-Step $resultsCommand
    }
    'serve' {
        Invoke-Step 'uv', 'run', 'uvicorn', 'autovalor.api.main:app', '--reload',
        '--host', $ApiHost, '--port', "$Port"
    }
    'web' { Invoke-NpmStep 'run dev' }
    'web-build' { Invoke-NpmStep 'run build' }
    'web-lint' {
        Invoke-NpmStep 'run lint'
        Invoke-NpmStep 'run typecheck'
    }
    'test' { Invoke-Step 'uv', 'run', 'pytest' }
    'lint' {
        Invoke-Step 'uv', 'run', 'ruff', 'check', '.'
        Invoke-Step 'uv', 'run', 'ruff', 'format', '--check', '.'
        Invoke-Step 'uv', 'run', 'mypy'
    }
    'format' {
        Invoke-Step 'uv', 'run', 'ruff', 'check', '--fix', '.'
        Invoke-Step 'uv', 'run', 'ruff', 'format', '.'
    }
    'docker-build' { Invoke-Step 'docker', 'compose', 'build' }
    'docker-up' { Invoke-Step 'docker', 'compose', 'up', '-d', 'api' }
    'clean' {
        $paths = @('.ruff_cache', '.mypy_cache', '.pytest_cache', '.coverage', 'htmlcov', 'coverage.xml')
        foreach ($path in $paths) {
            if (Test-Path $path) { Remove-Item -Recurse -Force $path }
        }
        Get-ChildItem -Path . -Filter '__pycache__' -Recurse -Directory -Force |
            Where-Object { $_.FullName -notmatch '\\(\.venv|node_modules)\\' } |
            Remove-Item -Recurse -Force
    }
}
