# G3 XSDB桥接：参数分别传入，不拼cmd命令字符串，支持安装/留证路径含空格。
param(
    [Parameter(Mandatory=$true)][string]$XsdbPath,
    [Parameter(Mandatory=$true)][string]$TclPath
)
$ErrorActionPreference = 'Stop'
if (!(Test-Path -LiteralPath $XsdbPath -PathType Leaf)) { throw "XSDB_NOT_FOUND: $XsdbPath" }
if (!(Test-Path -LiteralPath $TclPath -PathType Leaf)) { throw "TCL_NOT_FOUND: $TclPath" }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $XsdbPath $TclPath
    $xsdbExitCode = $LASTEXITCODE
} finally { Pop-Location }
if ($xsdbExitCode -ne 0) { exit $xsdbExitCode }
