# Action Plan: Fix Connection Issue

## 🎯 The Real Problem

**We cannot connect to the user's actual Nuanic ring** (54:EF:C5:C4:02:93)

All previous testing was on a neighbor's wrong ring. Before any implementation can happen, we need to fix the BLE connection issue.

---

## 🔧 Phase 1: Debug Connection Timeout

### Problem Symptoms
- Ring discovered: ✓ (appears in BLE scan as "Nuanic")
- Connection attempts: ✗ (timeout during GATT negotiation)
- Pairwise window: ~2-3 minutes (very tight)

### Root Cause Unknown
Possibilities to investigate:
1. Pairwise timeout closing connection before GATT negotiation completes
2. Ring requires bonding before accepting GATT operations
3. Bleak timeout settings need adjustment
4. Ring GATT stack behaves differently during pairwise vs normal mode

### Actions to Try

**Option 1: Test without pairwise mode**
- Remove ring from dock
- Power it on normally  
- Attempt connection without pairwise window
- See if bonding helps

**Option 2: Increase timeout windows**
- Bleak currently uses 3-5 second connection timeouts
- Try 10-15 second timeouts to span full GATT negotiation

**Option 3: Check if ring requires pairing**
- Ring may not accept GATT until it's bonded to system
- Test pairing via system Bluetooth settings first
- Then connect via Bleak

**Option 4: Investigate Bleak-specific issues**
- Different backend (WinRT vs Windows API)
- Bleak version compatibility
- Characteristic discovery delay

---

## 🎯 Phase 2: GATT Discovery

Once connection is stable:

### Goals
1. Discover all services and characteristics on actual ring
2. Find the correct stress data characteristic (may NOT be 00000010-0060-7990-5544-1cce81af42f0)
3. Determine if data is readable or requires notifications

### Output
- CSV file with all services/characteristics
- Which characteristics contain data
- Data format specifications

---

## 🎯 Phase 3: Validation

Once GATT is discovered:

### Goals
1. Connect and read the stress characteristic
2. Verify Byte 14 contains DNE (0-100 range)
3. Verify app display matches BLE reads

### Success Criteria
- Read `stress_value` from BLE
- `0 <= stress_value <= 100`
- Value matches or correlates with app display

---

## 📋 Immediate Next Steps

1. **Try PowerOn Mode** (no pairwise)
   - Put ring on finger or table without dock
   - Test connection via Bleak
   - Time how long connection takes

2. **Run Protocol Discovery** (if connection works)
   ```powershell
   python scripts/ble/nuanic_protocol_discovery.py
   ```

3. **Document findings**
   - Which approach works
   - How long connection takes
   - Any error messages

4. **Share results** so we can plan Phase 2

---

## Note

**Do not proceed with implementation** until connection issue is resolved.
All Phase 1 findings are invalid because they're based on wrong device.

See: [STATUS_HONEST.md](STATUS_HONEST.md)
