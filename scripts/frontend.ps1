param(
  [ValidateSet('version','install','test','build','dev','preview')]
  [string]$Command='version',
  [Parameter(ValueFromRemainingArguments=$true)]
  [string[]]$Arguments=@()
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$node=(Get-Command node -ErrorAction SilentlyContinue).Source
if(-not $node -or (& $node --version) -ne 'v16.13.0') {
  $node=Join-Path $root '.tmp-tools\node-v16.13.0-win-x64\node.exe'
}
if(-not (Test-Path -LiteralPath $node) -or (& $node --version) -ne 'v16.13.0') {
  throw 'Node 16.13.0 is required. Activate an approved installation before running this frontend.'
}
$nodeDirectory=Split-Path -Parent $node
$npm=Join-Path $nodeDirectory 'node_modules\npm\bin\npm-cli.js'
if(-not (Test-Path -LiteralPath $npm)) { throw 'The selected Node installation has no npm CLI.' }
$previousPath=$env:PATH
Push-Location (Join-Path $root 'frontend')
try {
  $env:PATH="$nodeDirectory;$previousPath"
  if($Command -eq 'version') {
    & $node --version
    & $node $npm --version
  } elseif($Command -eq 'install') {
    & $node $npm ci --include=dev @Arguments
  } else {
    & $node $npm run $Command -- @Arguments
  }
  $result=$LASTEXITCODE
} finally {
  $env:PATH=$previousPath
  Pop-Location
}
exit $result
