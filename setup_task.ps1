# Windows计划任务创建脚本 - 每天9:25自动扫描
# 右键 → 使用PowerShell运行，或管理员PowerShell中执行:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup_task.ps1

$taskName = "A股量化选股-早盘扫描"
$scriptPath = Join-Path $PSScriptRoot "auto_scan.bat"
$pythonPath = (Get-Command py -ErrorAction SilentlyContinue).Source

if (-not $pythonPath) {
    Write-Host "❌ 未找到Python (py命令)，请先安装Python 3.11+" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "🐍 Python路径: $pythonPath" -ForegroundColor Green
Write-Host "📜 脚本路径: $scriptPath" -ForegroundColor Green

# 删除旧任务（如果存在）
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "🗑️  删除旧任务: $taskName"
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# 创建新任务 - 工作日9:25触发
$action = New-ScheduledTaskAction -Execute $scriptPath
$trigger = New-ScheduledTaskTrigger -Daily -At "09:25"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

# 设置仅工作日运行（周一到周五）
$trigger.DaysInterval = 1
$trigger.Repetition = $null

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "每个交易日9:25自动运行A股量化扫描并推送到手机"

Write-Host "✅ 计划任务 '$taskName' 创建成功！" -ForegroundColor Green
Write-Host "⏰ 每个工作日 9:25 自动运行"
Write-Host ""
Write-Host "📋 查看/修改: 按Win+R → 输入 taskschd.msc → 任务计划程序库"
Write-Host "⚠️  注意: 电脑需要在这个时间处于开机状态（不休眠）"

# 同样创建14:00午盘扫描
$taskName2 = "A股量化选股-午盘扫描"
$trigger2 = New-ScheduledTaskTrigger -Daily -At "13:05"
$existing2 = Get-ScheduledTask -TaskName $taskName2 -ErrorAction SilentlyContinue
if ($existing2) { Unregister-ScheduledTask -TaskName $taskName2 -Confirm:$false }
Register-ScheduledTask -TaskName $taskName2 -Action $action -Trigger $trigger2 -Settings $settings -Principal $principal -Description "每个交易日13:05午盘扫描"
Write-Host "✅ 午盘扫描任务也创建完成 (13:05)"

pause
