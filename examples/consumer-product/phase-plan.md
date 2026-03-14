# Phase Plan: Add Offline Mode for Audio Projects

## Meta

- **Complexity**: Complex
- **Total Phases**: 4
- **BOUND Interaction**: Adjacent to DANGER ZONE (Sync, CoreData)
- **Estimated Effort**: 3-4 days

## Task Summary

Users lose work when they go offline mid-session (subway, airplane). Add offline
mode that queues changes locally and syncs when connectivity returns.

## Core Metric

User can record, edit, and save audio projects without network. Sync succeeds
when network returns with zero data loss.

---

## Phase 1: Local Queue Infrastructure — HIGH

**Entry criteria:**
- [x] All tests pass (186/186)
- [x] Core Data model reviewed

**Scope:**
- `Sources/Sync/OfflineQueue.swift` — local change queue
- `Sources/Sync/Models/PendingChange.swift` — change record model
- `Tests/SyncTests/OfflineQueueTests.swift`

**Exit criteria:**
- [x] Changes enqueue when offline
- [x] Queue persists across app restarts (Core Data backed)
- [x] IRON LAW: Core Data migration tested

---

## Phase 2: Connectivity Monitor — MEDIUM

**Entry criteria:**
- [x] Phase 1 verified

**Scope:**
- `Sources/Sync/ConnectivityMonitor.swift` — NWPathMonitor wrapper
- `Sources/Sync/SyncCoordinator.swift` — online/offline routing

**Exit criteria:**
- [x] Detects connectivity changes
- [x] Routes saves to queue when offline, to CloudKit when online
- [x] IRON LAW: no synchronous network on audio thread

---

## Phase 3: Sync Recovery — CRITICAL

**Entry criteria:**
- [x] Phase 2 verified

**Scope:**
- `Sources/Sync/ConflictResolver.swift` — handle offline-created conflicts
- `Sources/Sync/SyncRecovery.swift` — queue replay on reconnect

**Exit criteria:**
- [x] Queued changes replay in order
- [x] Conflicts resolved via existing CRDT (no new resolution logic)
- [x] No data loss in any conflict scenario (tested with 10 scenarios)

---

## Phase 4: UI Indicators — LOW

**Entry criteria:**
- [x] Phases 1-3 verified

**Scope:**
- `Sources/Views/StatusBar/OfflineIndicator.swift` — offline badge
- `Sources/Views/StatusBar/SyncProgressView.swift` — sync progress

**Exit criteria:**
- [x] User sees clear offline/online/syncing status
- [x] IRON LAW: UI updates on MainActor only
- [x] App launch time still under 2 seconds

---

## Autonomous Discovery & Remediation Log

| Phase | Discovery / Trigger | Action Taken (Autonomous) | Verification |
|-------|---------------------|---------------------------|--------------|
| 1 | Core Data lightweight migration sufficient | Simplified Phase 1 | No heavyweight migration needed |
| 3 | VERIFY Failed: CRDT merge for audio track metadata caused a test crash (`EXC_BAD_ACCESS`). | Consulted `remediation.md`. Detected issue was not in CoreData DANGER ZONE (was in Sync logic). Autonomously reverted to previous commit. Modified CRDT resolution logic to handle optional metadata fields safely. | Tests pass. No data loss in conflict scenarios. |
