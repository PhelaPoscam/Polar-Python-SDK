# Pair a Polar watch by MAC address through the Windows Runtime (WinRT) APIs.
# Run in Windows PowerShell 5.1 (PowerShell 7 cannot load WinRT types this way):
#   .\scripts\pair_watch.ps1 -Mac 24:AC:AC:00:00:00

param(
    [Parameter(Mandatory = $true)]
    [string]$Mac
)

$ErrorActionPreference = "Stop"

# Load Windows Runtime types
[Windows.Devices.Bluetooth.BluetoothLEDevice, Windows.Devices.Bluetooth, ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Enumeration.DevicePairingProtectionLevel, Windows.Devices.Enumeration, ContentType=WindowsRuntime] | Out-Null

$macAddressHex = $Mac -replace '[:-]', ''
$macAddressVal = [Convert]::ToUInt64($macAddressHex, 16)

# WinRT async operations expose Status (Started/Completed/Canceled/Error), not IsCompleted.
function Wait-WinRT($operation) {
    while ($operation.Status -eq 'Started') {
        Start-Sleep -Milliseconds 100
    }
    if ($operation.Status -ne 'Completed') {
        throw "WinRT operation ended with status $($operation.Status)"
    }
    return $operation.GetResults()
}

Write-Host "Connecting to Polar device (MAC: $Mac)..." -ForegroundColor Cyan

$device = Wait-WinRT ([Windows.Devices.Bluetooth.BluetoothLEDevice]::FromBluetoothAddressAsync($macAddressVal))

if ($device -eq $null) {
    Write-Error "Failed to connect to the BLE device. Please make sure the watch is nearby and broadcasting."
    exit 1
}

Write-Host "Connected! Name: $($device.Name)" -ForegroundColor Green
Write-Host "Initiating OS-level pairing request. Look at your watch screen and Windows notifications for the PIN code..." -ForegroundColor Yellow

$pairing = $device.DeviceInformation.Pairing
$result = Wait-WinRT ($pairing.PairAsync([Windows.Devices.Enumeration.DevicePairingProtectionLevel]::None))

Write-Host "`nPairing completed with status: $($result.Status)" -ForegroundColor Green

if ($result.Status -eq "Paired" -or $result.Status -eq "AlreadyPaired") {
    Write-Host "[OK] Pairing succeeded!" -ForegroundColor Green
} else {
    Write-Host "[FAILED] Pairing failed: $($result.Status)" -ForegroundColor Red
    exit 1
}
