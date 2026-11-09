$exe = 'E:\vibe coding\steam\tools\bin\relaycore.exe'
$out = 'D:\RelayGame\RimWorld'
$keys = 'E:\vibe coding\steam\src\data\keys\merged.json'
$index = 'E:\vibe coding\steam\tests\reports\mirror-index.json'
$state = Join-Path $out '.relaystore-state.json'
Remove-Item $state -Force -ErrorAction SilentlyContinue
$log = Join-Path $env:TEMP 'rimworld-download.log'
$p = Start-Process -FilePath $exe -ArgumentList "restore-app --appid 294100 --out `"$out`" --keys `"$keys`" --index `"$index`" --workers 8 --depot-workers 1 --state `"$state`"" -PassThru -NoNewWindow -RedirectStandardOutput $log
for ($i=1; $i -le 10; $i++) {
  Start-Sleep -Seconds 15
  $s = (Get-ChildItem $out -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum)
  't=' + ($i*15) + 's files=' + $s.Count + ' MB=' + [math]::Round($s.Sum/1MB,1)
}
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
'--- log tail ---'
if (Test-Path $log) { Get-Content $log -Tail 5 }