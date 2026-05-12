<#
.SYNOPSIS
  Pechepro dev convenience tasks.

.DESCRIPTION
  Run common dev commands (test, lint, format, smoke, coverage) without remembering exact pytest/ruff syntax.

.EXAMPLE
  .\tasks.ps1 test
  .\tasks.ps1 lint
  .\tasks.ps1 cov
  .\tasks.ps1 smoke
  .\tasks.ps1 hooks
  .\tasks.ps1 clean
  .\tasks.ps1 status
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("test", "lint", "format", "cov", "smoke", "hooks", "clean", "status", "help")]
    [string]$Task = "help"
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSStyle.OutputRendering = "Ansi"
}

# Activate venv if not already. Walks up parents to find .venv (so this script
# works from main repo OR from any worktree under .claude/worktrees/).
function Find-Venv {
    $current = $PSScriptRoot
    while ($current) {
        $candidate = Join-Path $current ".venv\Scripts\Activate.ps1"
        if (Test-Path $candidate) { return $candidate }
        $parent = Split-Path $current -Parent
        if ($parent -eq $current) { return $null }
        $current = $parent
    }
    return $null
}

if (-not $env:VIRTUAL_ENV) {
    $venvActivate = Find-Venv
    if ($venvActivate) {
        & $venvActivate
    } else {
        Write-Warning "No .venv found in $PSScriptRoot or parents. Run: python -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -e .[dev]"
        exit 1
    }
}

function Invoke-Test {
    Write-Host "---pytest (excluding smoke) ---" -ForegroundColor Cyan
    pytest -v -m "not smoke" $args
}

function Invoke-Lint {
    Write-Host "---ruff check ---" -ForegroundColor Cyan
    ruff check app tests
    Write-Host "---ruff format check ---" -ForegroundColor Cyan
    ruff format --check app tests
}

function Invoke-Format {
    Write-Host "---ruff format (apply) ---" -ForegroundColor Cyan
    ruff format app tests
    Write-Host "---ruff check --fix ---" -ForegroundColor Cyan
    ruff check --fix app tests
}

function Invoke-Cov {
    Write-Host "---pytest with coverage (≥80% gate) ---" -ForegroundColor Cyan
    pytest --cov=app --cov-report=term-missing --cov-report=html --cov-fail-under=80 -m "not smoke"
    Write-Host "Coverage HTML: " -NoNewline
    Write-Host (Resolve-Path ".\htmlcov\index.html") -ForegroundColor Green
}

function Invoke-Smoke {
    Write-Host "---pytest -m smoke (E2E) ---" -ForegroundColor Cyan
    pytest -v -m smoke
}

function Invoke-Hooks {
    Write-Host "---pre-commit run --all-files ---" -ForegroundColor Cyan
    pre-commit run --all-files
}

function Invoke-Clean {
    Write-Host "---cleaning build/test artifacts ---" -ForegroundColor Cyan
    @(".pytest_cache", ".coverage", "htmlcov", "build", "dist", "__pycache__") | ForEach-Object {
        Get-ChildItem -Path . -Recurse -Force -Directory -Filter $_ -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    Get-ChildItem -Path . -Recurse -Force -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host "Done." -ForegroundColor Green
}

function Invoke-Status {
    Write-Host "---repo status ---" -ForegroundColor Cyan
    git status --short
    Write-Host "`n---recent commits ---" -ForegroundColor Cyan
    git log --oneline -8
    Write-Host "`n---tags ---" -ForegroundColor Cyan
    git tag --list
    Write-Host "`n---worktrees ---" -ForegroundColor Cyan
    git worktree list
    Write-Host "`n---tests count ---" -ForegroundColor Cyan
    pytest --collect-only -q 2>&1 | Select-Object -Last 3
}

function Show-Help {
    @"
pechepro dev tasks
==================
.\tasks.ps1 test     Run pytest excluding smoke
.\tasks.ps1 lint     Run ruff check + format check (no fix)
.\tasks.ps1 format   Apply ruff format + auto-fix
.\tasks.ps1 cov      pytest with coverage report (≥80% gate)
.\tasks.ps1 smoke    Run smoke E2E tests only
.\tasks.ps1 hooks    Run pre-commit on all files
.\tasks.ps1 clean    Remove build/test artifacts
.\tasks.ps1 status   Show repo status, commits, tags, worktrees, test count
.\tasks.ps1 help     This message
"@ | Write-Host
}

switch ($Task) {
    "test"   { Invoke-Test }
    "lint"   { Invoke-Lint }
    "format" { Invoke-Format }
    "cov"    { Invoke-Cov }
    "smoke"  { Invoke-Smoke }
    "hooks"  { Invoke-Hooks }
    "clean"  { Invoke-Clean }
    "status" { Invoke-Status }
    default  { Show-Help }
}
