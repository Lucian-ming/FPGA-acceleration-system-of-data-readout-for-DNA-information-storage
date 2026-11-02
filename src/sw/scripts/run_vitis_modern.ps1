param(
    [Parameter(Mandatory=$true)][string]$Config,
    [string]$Vitis = $(if ($env:XILINX_VITIS) { Join-Path $env:XILINX_VITIS 'bin\vitis.bat' } else { '' }),
    [string]$LogDir = '',
    [string]$Script = '',
    [int]$TimeoutSeconds = 3600
)
# $PSScriptRoot 在 param 默认值里不可靠（Windows PowerShell 5.1 下可能取到空串），
# 故脚本路径放到参数解析之后再推导；显式传 -Script 时仍以传入值为准。
if (-not $Script) {
    $here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
    $Script = Join-Path $here 'create_vitis_modern.py'
}
# 2026.1启动器可能吞掉Python失败退出码：只认成功哨兵和真实产物哈希。
$ErrorActionPreference = 'Stop'
if (-not $Vitis) {throw '未指定 Vitis：请传 -Vitis <...\bin\vitis.bat>，或设置环境变量 XILINX_VITIS'}
$configPath = (Resolve-Path -LiteralPath $Config).Path
$scriptPath = (Resolve-Path -LiteralPath $Script).Path
$vitisPath = (Resolve-Path -LiteralPath $Vitis).Path
$settings = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
if ($settings.dry_run) {throw '真实构建wrapper不接受dry_run；配置预检请直接运行Python入口'}
if ($TimeoutSeconds -lt 30 -or $TimeoutSeconds -gt 86400) {throw 'TimeoutSeconds必须在30..86400内'}
if (-not $LogDir) {
    $LogDir = Join-Path (Split-Path -Parent $configPath) ('vitis-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
}
$logPath = Join-Path ([IO.Path]::GetFullPath($LogDir)) 'vitis.log'
if (Test-Path -LiteralPath $logPath) {throw "日志已存在，禁止覆盖：$logPath"}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) | Out-Null
$oldConfig = $env:DNA_VITIS_CONFIG
$oldPythonUtf8 = $env:PYTHONUTF8
$oldPythonIOEncoding = $env:PYTHONIOENCODING
try {
    $env:DNA_VITIS_CONFIG = $configPath
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $stdoutPath = Join-Path (Split-Path -Parent $logPath) 'vitis-stdout.txt'
    $stderrPath = Join-Path (Split-Path -Parent $logPath) 'vitis-stderr.txt'
    $stdinPath = Join-Path (Split-Path -Parent $logPath) 'stdin-empty.txt'
    [IO.File]::WriteAllBytes($stdinPath, [byte[]]@())
    # SDK decodes its server's stdout as UTF-8, including cmd.exe startup
    # diagnostics. Change only this hidden child's console code page.
    foreach ($path in @($vitisPath,$scriptPath)) {
        if ($path -match '["%\r\n]') {throw '构建脚本路径含不支持的cmd字符'}
    }
    $launchPath = Join-Path (Split-Path -Parent $logPath) 'launch-vitis.cmd'
    $launchText = "@echo off`r`nchcp 65001 >nul`r`ncall `"$vitisPath`" -s `"$scriptPath`"`r`nexit /b %errorlevel%`r`n"
    [IO.File]::WriteAllText($launchPath, $launchText, [Text.UTF8Encoding]::new($false))
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList @('/d','/c',('"'+$launchPath+'"')) -WorkingDirectory (Split-Path -Parent $vitisPath) -WindowStyle Hidden -PassThru -RedirectStandardInput $stdinPath -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    # Windows PowerShell 5 may lose ExitCode if the process handle was never
    # cached, or Refresh() discards the exit state after WaitForExit().
    $null = $process.Handle
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        # 只回收本wrapper刚创建的进程树，不影响共享/未知服务。
        if ([Environment]::Version.Major -ge 5) {
            $process.Kill($true)
        } else {
            # Windows PowerShell 5没有Kill(bool)，只回收本次创建的PID树。
            & taskkill.exe /PID $process.Id /T /F | Out-Null
        }
        $process.WaitForExit()
        throw "Vitis构建超时，已停止本次进程树；证据：$stdoutPath、$stderrPath"
    }
    $toolExit = $process.ExitCode
    if ($null -eq $toolExit) {throw '无法取得本次构建进程的退出码'}
    (Get-Content -LiteralPath $stdoutPath -Raw) + (Get-Content -LiteralPath $stderrPath -Raw) | Set-Content -LiteralPath $logPath -Encoding utf8
    Get-Content -LiteralPath $logPath
} finally {
    $env:DNA_VITIS_CONFIG = $oldConfig
    $env:PYTHONUTF8 = $oldPythonUtf8
    $env:PYTHONIOENCODING = $oldPythonIOEncoding
}
if ($toolExit -ne 0) {throw "Vitis返回失败$toolExit，证据：$logPath"}
$logText = Get-Content -LiteralPath $logPath -Raw
if ($logText -notmatch '(?m)^SOFTWARE_BUILD_PASS ') {throw "缺少成功哨兵，不能以Vitis exit=0判定成功：$logPath"}
$summaryPath = Join-Path $settings.export_dir 'software_build_config.json'
$summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
if ($summary.schema_version -ne 1 -or $summary.scope -ne 'software-build-only') {throw '软件摘要schema/scope不合法'}
foreach ($name in @('board_id','part','uart')) {
    if ($summary.$name -ne $settings.$name) {throw "软件摘要与输入配置不一致：$name"}
}
if ($summary.input_xsa_sha256 -ne (Get-FileHash -LiteralPath $settings.xsa -Algorithm SHA256).Hash.ToLowerInvariant()) {throw '软件摘要输入XSA哈希不一致'}
$requiredArtifacts = @('dna_lwip_app.elf','fsbl.elf','BOOT.bin','top_bd_wrapper.bit','ps7_init.tcl',(Split-Path -Leaf $settings.xsa))
foreach ($name in $requiredArtifacts) {
    if (-not $summary.artifacts.PSObject.Properties[$name] -or $summary.artifacts.$name -notmatch '^[0-9a-f]{64}$') {throw "软件摘要缺少有效产物哈希：$name"}
}
foreach ($artifact in $summary.artifacts.PSObject.Properties) {
    if ($artifact.Name -ne (Split-Path -Leaf $artifact.Name)) {throw "摘要产物必须为目录内文件：$($artifact.Name)"}
    $path = Join-Path $settings.export_dir $artifact.Name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {throw "产物缺失：$path"}
    if ((Get-Item -LiteralPath $path).Length -eq 0) {throw "产物为空：$path"}
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $artifact.Value) {throw "产物哈希不一致：$path"}
}
Write-Output "SOFTWARE_WRAPPER_PASS summary=$summaryPath log=$logPath"
