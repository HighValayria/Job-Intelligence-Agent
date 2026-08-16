param(
    [string]$TaskName = "AlgorithmDailyPush"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Output "scheduled task not found: $TaskName"
    return
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Output "unregistered scheduled task: $TaskName"
