param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$DbPath = "data\algorithm_push.sqlite3",
    [string]$ConfigPath = "algorithm_push\config\algorithm_push.yaml",
    [Nullable[int]]$Seed = $null,
    [ValidateSet("console", "qq")]
    [string]$Adapter = "",
    [switch]$Force,
    [switch]$SkipImportDefaults,
    [switch]$SkipReadiness,
    [string]$PythonPath = "",
    [string]$LogPath = "data\logs\algorithm_push_scheduler.log"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed.StartsWith("export ")) {
            $trimmed = $trimmed.Substring(7).TrimStart()
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts.Count -ne 2) {
            continue
        }
        $key = $parts[0].Trim()
        if ($key -notmatch "^[A-Za-z_][A-Za-z0-9_]*$") {
            continue
        }
        $value = $parts[1].Trim()
        if (
            $value.Length -ge 2 -and
            (($value.StartsWith('"') -and $value.EndsWith('"')) -or
             ($value.StartsWith("'") -and $value.EndsWith("'")))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

function Resolve-PythonCommand {
    param([string]$RequestedPython)

    $candidates = @()
    if ($RequestedPython) {
        $candidates += $RequestedPython
    }
    if ($env:ALGORITHM_PYTHON) {
        $candidates += $env:ALGORITHM_PYTHON
    }
    $candidates += (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    $candidates += (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")

    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        if (Test-Path -LiteralPath $candidate) {
            try {
                & $candidate --version *> $null
                if ($LASTEXITCODE -eq 0) {
                    return $candidate
                }
            } catch {
                continue
            }
        }
    }

    $globalPython = Get-Command python -ErrorAction SilentlyContinue
    if ($globalPython) {
        try {
            & $globalPython.Source --version *> $null
            if ($LASTEXITCODE -eq 0) {
                return $globalPython.Source
            }
        } catch {
        }
    }

    throw "No working Python interpreter found. Set ALGORITHM_PYTHON or pass -PythonPath."
}

function Invoke-AlgorithmPush {
    param([string[]]$Arguments)
    & $script:Python -m algorithm_push @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "algorithm_push failed: $($Arguments -join ' ')"
    }
}

$project = Resolve-Path -LiteralPath $ProjectRoot
Set-Location -LiteralPath $project.Path
Import-DotEnv -Path (Join-Path $project.Path ".env")

$log = Join-Path $project.Path $LogPath
New-Item -ItemType Directory -Path (Split-Path -Parent $log) -Force | Out-Null
$script:Python = Resolve-PythonCommand -RequestedPython $PythonPath

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
"[$timestamp] algorithm scheduler start project=$($project.Path) python=$script:Python" |
    Tee-Object -FilePath $log -Append

$globalArgs = @("--db-path", $DbPath, "--config", $ConfigPath)

try {
    if (-not $SkipImportDefaults) {
        Invoke-AlgorithmPush -Arguments ($globalArgs + @("import-defaults")) |
            Tee-Object -FilePath $log -Append
    }
    if (-not $SkipReadiness) {
        Invoke-AlgorithmPush -Arguments ($globalArgs + @("readiness", "--days", "30", "--strict")) |
            Tee-Object -FilePath $log -Append
    }

    $schedulerArgs = $globalArgs + @("scheduler-once")
    if ($Seed -ne $null) {
        $schedulerArgs += @("--seed", [string]$Seed)
    }
    if ($Adapter) {
        $schedulerArgs += @("--adapter", $Adapter)
    }
    if ($Force) {
        $schedulerArgs += "--force"
    }
    Invoke-AlgorithmPush -Arguments $schedulerArgs |
        Tee-Object -FilePath $log -Append

    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")] algorithm scheduler done" |
        Tee-Object -FilePath $log -Append
} catch {
    "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")] algorithm scheduler failed: $_" |
        Tee-Object -FilePath $log -Append
    throw
}
