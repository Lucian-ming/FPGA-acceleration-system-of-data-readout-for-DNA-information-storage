# G3 串口实录（由 tools/run_g3.sh 后台拉起）
#
# COM6 一次只能被一个进程占用：跑之前确认没有别的串口终端开着。
# 与历史的 uart_cap.ps1 的两点区别：
#   1) 日志路径可传参 —— 每轮存到独立的 run 目录，不再覆盖 D:\dna_board_smoke\uart.log；
#   2) 支持 -StopFile —— run_g3.sh 在 first.py 收工后建这个文件即可收尾，
#      不必为了等固定窗口而空转（时长上限仍由 -Seconds 兜底）。
param(
    [Parameter(Mandatory=$true)][string]$LogPath,
    [int]$Seconds = 240,
    [string]$StopFile = '',
    [string]$PortName = 'COM6',
    [int]$Baud = 115200
)
Remove-Item $LogPath -ErrorAction SilentlyContinue
$port = New-Object System.IO.Ports.SerialPort $PortName,$Baud,'None',8,'one'
$port.ReadTimeout = 500
$port.NewLine = "`n"
try { $port.Open() } catch { Write-Output "OPEN_FAIL $_"; exit 1 }
$sw = New-Object System.IO.StreamWriter($LogPath, $false)
$sw.AutoFlush = $true
$sw.WriteLine("# UART capture $PortName @$Baud, started $((Get-Date).ToUniversalTime().ToString('o')), window ${Seconds}s")
Write-Output "CAPTURING $PortName $Baud for $Seconds s -> $LogPath"
$deadline = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $deadline) {
    if ($StopFile -ne '' -and (Test-Path $StopFile)) { break }
    try { $sw.WriteLine($port.ReadLine()) } catch { Start-Sleep -Milliseconds 50 }
}
$sw.WriteLine("# UART capture ended $((Get-Date).ToUniversalTime().ToString('o'))")
$sw.Close(); $port.Close()
Write-Output "CAPTURE_DONE"
