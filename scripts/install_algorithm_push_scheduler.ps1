param(
    [string]$TaskName = "AlgorithmDailyPush",
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Time = "09:00",
    [string]$DbPath = "data\algorithm_push.sqlite3",
    [string]$ConfigPath = "algorithm_push\config\algorithm_push.yaml",
    [ValidateSet("console", "qq")]
    [string]$Adapter = "",
    [Nullable[int]]$Seed = $null,
    [string]$PythonPath = "",
    [switch]$Force,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$project = Resolve-Path -LiteralPath $ProjectRoot
$runner = Join-Path $project.Path "scripts\run_algorithm_scheduler_once.ps1"
if (-not (Test-Path -LiteralPath $runner)) {
    throw "Scheduler runner script not found: $runner"
}

$argumentParts = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$runner`"",
    "-ProjectRoot", "`"$($project.Path)`"",
    "-DbPath", "`"$DbPath`"",
    "-ConfigPath", "`"$ConfigPath`""
)
if ($Adapter) {
    $argumentParts += @("-Adapter", $Adapter)
}
if ($Seed -ne $null) {
    $argumentParts += @("-Seed", [string]$Seed)
}
if ($PythonPath) {
    $argumentParts += @("-PythonPath", "`"$PythonPath`"")
}
if ($Force) {
    $argumentParts += "-Force"
}

$taskArgument = $argumentParts -join " "

if ($WhatIf) {
    Write-Output "would register scheduled task: $TaskName at $Time"
    Write-Output "execute: powershell.exe"
    Write-Output "argument: $taskArgument"
    Write-Output "working_directory: $($project.Path)"
    Write-Output "runner: $runner"
    return
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument $taskArgument `
    -WorkingDirectory $project.Path

$trigger = New-ScheduledTaskTrigger -Daily -At ([DateTime]::ParseExact($Time, "HH:mm", $null))
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Run Algorithm Daily Push scheduler-once from $($project.Path)" `
    -Force | Out-Null

Write-Output "registered scheduled task: $TaskName at $Time"
Write-Output "runner: $runner"
Write-Output "project: $($project.Path)"
