param(
    [Parameter(Mandatory=$true)][string]$InputDir,
    [Parameter(Mandatory=$true)][string]$RunDir,
    [string]$VivadoRoot = 'D:\xilinx\2026.1\Vivado'
)
# 正式LC50：只读带SHA的源码/fixture快照，不连接板卡，不更改IP打包源码。
$ErrorActionPreference = 'Stop'
$inputPath = (Resolve-Path -LiteralPath $InputDir).Path
$runPath = [IO.Path]::GetFullPath($RunDir)
if (Test-Path -LiteralPath $runPath) {throw 'RunDir必须不存在，禁止覆盖仿真证据'}
$manifest = Get-Content -LiteralPath (Join-Path $inputPath 'source_manifest.json') -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne 1) {throw '输入manifest版本错误'}
foreach ($entry in $manifest.files.PSObject.Properties) {
    if ($entry.Name -match '(^|[\\/])\.\.([\\/]|$)|^[\\/]|:') {throw '输入manifest路径越界'}
    $source = Join-Path $inputPath $entry.Name
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {throw "输入哈希不一致：$source"}
}
$names = @('Dna_accelerator_core_v1_0.v','Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v','fifo_sync_sdpram_b64.v','s2mm_pack64.v','srpe_batch_4way.v','srpe_batch_pway.v')
$sources = @($names | ForEach-Object {Join-Path $inputPath ('hdl/'+$_)})
$fixture = (Join-Path $inputPath 'fixtures').Replace('\','/')
New-Item -ItemType Directory -Path $runPath | Out-Null
Copy-Item -LiteralPath (Join-Path $inputPath 'source_manifest.json') -Destination $runPath
function Invoke-XsimTool([string]$name, [string[]]$arguments, [string]$log) {
    & (Join-Path $VivadoRoot ('bin/'+$name+'.bat')) @arguments *> $log
    $code=$LASTEXITCODE
    $content=Get-Content -LiteralPath $log -Raw
    if ($code -ne 0 -or $content -match 'FATAL:|ERROR:|\bFAIL\b|FAILED') {throw "${name}失败，exit=$code，见$log"}
}
foreach ($case in @('equivalence','interface')) {
    $dir=Join-Path $runPath $case
    New-Item -ItemType Directory -Path $dir | Out-Null
    Push-Location $dir
    try {
        $top='tb_dna_stage1_p16_'+$case
        $tb=Join-Path $inputPath ('tb/'+$top+'.v')
        $snapshot='production_'+$case
        # Both production testbenches default to LC50; the final sentinel
        # must confirm that value. Avoid cmd.bat splitting NAME=50 macros.
        Invoke-XsimTool 'xvlog' (@('-work','work')+$sources+@($tb)) (Join-Path $dir 'xvlog.console.txt')
        Invoke-XsimTool 'xelab' @('-debug','off',$top,'-s',$snapshot) (Join-Path $dir 'xelab.console.txt')
        Write-Output "XSIM_PRODUCTION_BUILT $case LC=50"
        Invoke-XsimTool 'xsim' @($snapshot,'-runall','-testplusarg',('"fixture_dir='+$fixture+'"')) (Join-Path $dir 'xsim.console.txt')
        $content=Get-Content -LiteralPath (Join-Path $dir 'xsim.console.txt') -Raw
        $pattern=if ($case -eq 'equivalence') {'\[PRODUCTION EQ\] PASS '} else {'\[PRODUCTION AXIS\] PASS LC=50 '}
        if ($content -notmatch $pattern) {throw "$case缺少完整LC50通过哨兵"}
        if ($case -eq 'equivalence' -and ($content -notmatch 'round=0 LC=50 ' -or $content -notmatch 'round=1 LC=50 ')) {throw '等价测试未证明两轮均为正式LC50'}
        $content -split "`n" | Where-Object {$_ -match '\[PRODUCTION'} | Write-Output
    } finally {Pop-Location}
}
Write-Output "XSIM_STAGE1_PRODUCTION_FULL_PASS run=$runPath"
