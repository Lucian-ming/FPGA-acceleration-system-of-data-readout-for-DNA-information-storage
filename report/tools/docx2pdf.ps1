param([string]$In, [string]$Out)
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
$pre = $w.Documents.Count
$oldAlerts = $w.DisplayAlerts
$w.DisplayAlerts = 0
$d = $null
try {
  $d = $w.Documents.Open($In, $false, $true, $false)
  $d.Repaginate()
  $d.Fields.Update() | Out-Null
  foreach ($s in $d.Sections) { foreach ($f in $s.Footers) { $f.Range.Fields.Update() | Out-Null } }
  $d.ExportAsFixedFormat($Out, 17)
  Write-Output ("PAGES=" + $d.ComputeStatistics(2))
  $d.Close(0)
  $d = $null
} finally {
  if ($d -ne $null) { try { $d.Close(0) } catch {} }
  $w.DisplayAlerts = $oldAlerts
  if ($pre -eq 0) { $w.Quit() }
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($w) | Out-Null
}
