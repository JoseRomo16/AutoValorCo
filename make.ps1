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
    [ValidateSet('help', 'setup', 'scrape', 'transform', 'train', 'serve', 'test',
        'lint', 'format', 'docker-build', 'docker-up', 'clean')]
    [string]$Target = 'help',

    [string]$ApiHost = '127.0.0.1',
    [int]$Port = 8000,
    [int]$Pages = 10
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Invoke-Step {
    param([Parameter(Mandatory)][string[]]$Command)
    Write-Host "> $($Command -join ' ')" -ForegroundColor Cyan
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) { throw "$($Command[0]) exited with code $LASTEXITCODE" }
}

switch ($Target) {
    'help' {
        Write-Host 'AutoValor CO - available targets:'
        Write-Host '  setup          Install Python, browser and frontend dependencies'
        Write-Host '  scrape         Capture TuCarro listings into data/bronze'
        Write-Host '  transform      Run dbt (silver and gold) and the Pandera validations'
        Write-Host '  train          Train the models and log them to MLflow (F2)'
        Write-Host '  serve          Run the API locally with autoreload'
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
        if (Test-Path 'frontend') {
            Push-Location 'frontend'
            try { Invoke-Step 'npm', 'install' } finally { Pop-Location }
        }
        else {
            Write-Host 'frontend/ not created yet (F4), skipping npm install'
        }
    }
    'scrape' {
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.ingest.cli',
        '--vehicle-type', 'all', '--pages', "$Pages"
    }
    'transform' {
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.quality.cli', '--stage', 'bronze'
        Invoke-Step 'uv', 'run', 'dbt', 'build', '--project-dir', 'dbt', '--profiles-dir', 'dbt'
        Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.quality.cli',
        '--stage', 'silver', '--stage', 'gold'
    }
    'train' { Invoke-Step 'uv', 'run', 'python', '-m', 'autovalor.models.train' }
    'serve' {
        Invoke-Step 'uv', 'run', 'uvicorn', 'autovalor.api.main:app', '--reload',
        '--host', $ApiHost, '--port', "$Port"
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
