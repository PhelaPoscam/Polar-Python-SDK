# PowerShell script to pair Polar Vantage M3 directly by MAC address using Windows Runtime (WinRT) APIs

$ErrorActionPreference = "Stop"

# Load Windows Runtime types
[Windows.Devices.Bluetooth.BluetoothLEDevice, Windows.Devices.Bluetooth, ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Enumeration.DevicePairingProtectionLevel, Windows.Devices.Enumeration, ContentType=WindowsRuntime] | Out-Null

$macAddressHex = "24ACAC15197D" # Vantage M3 MAC Address
$macAddressVal = [Convert]::ToUInt64($macAddressHex, 16)

Write-Host "Connecting to Polar Vantage M3 (MAC: 24:AC:AC:15:19:7D)..." -ForegroundColor Cyan

# Fetch BLE device object
$deviceTask = [Windows.Devices.Bluetooth.BluetoothLEDevice]::FromBluetoothAddressAsync($macAddressVal)
while (-not $deviceTask.IsCompleted) {
    Start-Sleep -Milliseconds 100
}
$device = $deviceTask.GetResults()

if ($device -eq $null) {
    Write-Error "Failed to connect to the BLE device. Please make sure the watch is nearby and broadcasting."
    exit 1
}

Write-Host "Connected! Name: $($device.Name)" -ForegroundColor Green
Write-Host "Initiating OS-level pairing request. Look at your watch screen and Windows notifications for the PIN code..." -ForegroundColor Yellow

# Trigger pairing
$pairing = $device.DeviceInformation.Pairing
$pairTask = $pairing.PairAsync([Windows.Devices.Enumeration.DevicePairingProtectionLevel]::None)

# Poll for completion while allowing Windows to process the pairing UI
while (-not $pairTask.IsCompleted) {
    Start-Sleep -Milliseconds 200
}
$result = $pairTask.GetResults()

Write-Host "`nPairing completed with status: $($result.Status)" -ForegroundColor Green

if ($result.Status -eq "Paired" -or $result.Status -eq "AlreadyPaired") {
    Write-Host "[OK] Pairing succeeded!" -ForegroundColor Green
} else {
    Write-Host "[FAILED] Pairing failed: $($result.Status)" -ForegroundColor Red
}
