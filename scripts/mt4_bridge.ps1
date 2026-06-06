# MetaTrader 4/5 Price Bridge for TradingSignal Pro
# This script ensures the mt4_prices.csv file exists and is accessible.
# It can also be used to simulate prices for testing or to aggregate data.

$MT4Path = "C:\Users\USUARIO\AppData\Roaming\MetaQuotes\Terminal\Common\Files"
$CSVFile = "$MT4Path\mt4_prices.csv"

if (-not (Test-Path $MT4Path)) {
    Write-Host "Error: MetaTrader Common Files path not found at $MT4Path" -ForegroundColor Red
    Write-Host "Please update the path in app/core/config.py and this script."
    exit
}

Write-Host "Starting MT4 Price Bridge..." -ForegroundColor Cyan
Write-Host "Monitoring: $CSVFile"

# Create the file with headers if it doesn't exist
if (-not (Test-Path $CSVFile)) {
    "Symbol,Bid,Ask" | Out-File -FilePath $CSVFile -Encoding utf8
    Write-Host "Created initial CSV file."
}

Write-Host "Bridge is active. MT4 should now write to this file." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop."

# Keep alive
while($true) {
    Start-Sleep -Seconds 60
}
