param([string]$In, [string]$Out)
$ErrorActionPreference = 'Stop'
$pp = New-Object -ComObject PowerPoint.Application
$pre = $pp.Presentations.Count
$p = $null
try {
  # Open(FileName, ReadOnly, Untitled, WithWindow)
  $p = $pp.Presentations.Open($In, -1, 0, 0)
  $p.SaveAs($Out, 32)
  Write-Output ("SLIDES=" + $p.Slides.Count)
  $p.Close()
  $p = $null
} finally {
  if ($p -ne $null) { try { $p.Close() } catch {} }
  if ($pre -eq 0) { $pp.Quit() }
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
}
