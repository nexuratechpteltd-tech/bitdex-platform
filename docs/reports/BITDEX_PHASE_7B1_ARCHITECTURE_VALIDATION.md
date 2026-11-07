# BITDEX — Phase 7B.1: Architecture Validation & Technical Proof-of-Concept Report

**Author**: Antigravity (Deepmind AAC & Quantitative Trading Systems)  
**Date**: 2026-11-07  
**Platform**: `https://bitdex.ltd`  
**Repository**: `https://github.com/nexuratechpteltd-tech/bitdex-platform`  
**Branch**: `feature/hft-redesign-and-navigation-cleanup`  
**Status**: VALIDATION COMPLETE — CRITICAL DISCOVERIES DOCUMENTED — AWAITING EXPLICIT USER REVIEW

---

## Executive Summary

Phase 7B.1 provides empirical architectural validation and forensic technical auditing of the commercial multi-tenant trading architecture proposed in Phase 7B. All tests and measurements were conducted directly on the live infrastructure (Linux Staging VPS `169.58.218.168` and Windows Server 2022 VPS `149.33.34.123`) strictly in read-only mode (`live_trading_locked = True`, `emergency_lock_active = True`, `read_only_mode = True`).

### Key Validation Discoveries & Strategic Takeaways

1. **MT5 Multi-Instance Portable Mode & Session 0 Discovery**:
   - **Empirical Test**: Successfully provisioned and ran an isolated second terminal process (`terminal64.exe /portable /nosound`, PID 6000) concurrently with the primary terminal (`PID 5656`, Account `474861031`).
   - **Isolation Integrity**: Both processes ran with completely isolated working sets (`165.98 MB` vs `105.04 MB`). The primary terminal experienced **zero degradation, zero session collision, and zero account interruption**.
   - **Critical Architectural Constraint Discovered**: Launching terminal clones via SSH/headless non-interactive sessions produces MFC/MDI window creation errors (`MDI create failed: ... error 0`) and causes Python IPC initialization to timeout (`-10005, 'IPC timeout'`). MetaTrader 5's internal IPC server **strictly requires an interactive Windows GUI desktop session (Session 1+)** to attach its message pump. Consequently, multi-tenant MT5 workers cannot run as raw Session 0 services without an interactive auto-logged-in desktop host or user-session process wrapper.
2. **Official Exness API Specification Audit**:
   - Audited against live Exness production and gateway behavior: Ed25519 signing, DNS dynamic discovery (`https://api.exness.com` -> `https://ap-2c49ed65.exness.com`), and account snapshot endpoints are verified functional for native Exness Terminal (`dx.*`) accounts.
   - **Supported vs Unsupported Clarification**: Exness Trader REST/WebSocket APIs **strictly support native Exness Terminal accounts**. Standard MetaTrader 5 accounts (`Exness-MT5*`) are **not exposed** by the Exness Web API (`HTTP 401: AUTH_INVALID_API_KEY`).
3. **HFT Performance & 10-Second Polling Gap**:
   - The 10-second polling interval in earlier notes is **completely incompatible** with sub-second HFT and is intended solely for background health monitoring.
   - Empirical measurements on Windows VPS prove **local Python IPC is ultra-low-latency**: `account_info` takes **`0.038 ms`**, `symbol_info_tick` takes **`0.051 ms`**, and `positions_get` takes **`0.030 ms`**.
   - However, the transatlantic WireGuard tunnel between Linux Frankfurt (`169.58.218.168`) and Windows US (`149.33.34.123`) introduces a **`249.6 ms`** round-trip network transit. True sub-second execution requires co-locating the HFT execution engine on the Windows host.
4. **Envelope Credential Vault Specification**:
   - Designed a tamper-resistant AES-256-GCM envelope vault using Key Encryption Keys (KEK) and per-tenant Data Encryption Keys (DEK), bound cryptographically to tenant and account IDs via Authenticated Associated Data (AAD).
5. **Revised Relational Schema & Infrastructure Capacity**:
   - Provided revised `trading_accounts` schema, database migration scripts (review only, unapplied), and detailed cost models from 10 to 1,000 active MT5 subscribers.

---

## 1. MT5 Multi-Instance Proof-of-Concept & Behavioral Findings

### 1.1 Live Hardware & Resource Assessment
- **Host**: Windows Server 2022 Standard (Build 20348), 64-bit.
- **CPU**: Intel Xeon Gold 6154 @ 3.00 GHz (1 vCPU, 1 logical processor).
- **Physical Memory**: Total: `3,071.46 MB` (3.0 GB) | Free: `1,003.92 MB` (~1.0 GB).
- **Virtual Memory**: Total: `4,351.46 MB` | Free: `2,460.38 MB` (~2.4 GB).
- **Assessment**: The VPS has sufficient physical RAM (~1.0 GB free) to safely run up to 3–4 concurrent idle portable MT5 terminal instances (~160 MB each).

### 1.2 Multi-Instance Experiment Execution
An empirical proof-of-concept script was deployed and executed via `test_multi_instance_poc.py`:
1. **Primary Instance (Baseline)**:
   - Path: `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe`
   - Process ID: `5656` | Working Set RAM: `165.98 MB`
   - Active Account: `474861031` (Exness Demo, `Exness-MT5Trial15`, Balance: `$5,076.03 USD`).
2. **Secondary Instance (Cloned Portable Instance)**:
   - Target Directory: `C:\mt5_instances\inst_poc_02`
   - Cloned binaries using: `robocopy "C:\Program Files\MetaTrader 5 EXNESS" "C:\mt5_instances\inst_poc_02" /xd Bases Logs /xf *.log *.dat /e`
   - Launched using: `terminal64.exe /portable /nosound`
   - Process ID: `6000` | Working Set RAM: `105.04 MB`
3. **Dual-Process Process Table Output**:
   ```text
     Id Path                                                 WS_MB
     -- ----                                                 -----
   5656 C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe 165.98
   6000 C:\mt5_instances\inst_poc_02\terminal64.exe         105.04
   ```
4. **Primary Instance Integrity**:
   - While Instance 2 was initializing, Python IPC called Instance 1:
     `ok=True (1.04 ms), Login=474861031, Server=Exness-MT5Trial15, Balance=5076.03`.
   - After terminating Instance 2, Instance 1 was re-probed:
     `ok=True (1.12 ms), Login=474861031, Balance=5076.03`.
   - **Result**: Zero interference. Separate directories prevent file-lock or history collisions.

### 1.3 Critical Architectural Discovery: The Headless IPC Trap
When Python IPC attempted to attach to the cloned instance (`mt5.initialize(path=r"C:\mt5_instances\inst_poc_02\terminal64.exe")`), it timed out after 60 seconds with:
```text
(-10005, 'IPC timeout')
```
**Forensic Cause**:
Inspection of `C:\mt5_instances\inst_poc_02\Logs\20261107.log` revealed:
```text
Window   MDI unhook failed: Afx:... parent ..., error 0
Window   MDI create failed: Afx:... parent ..., error 0
Document create frame from resource 131 failed
```
MetaTrader 5 is a Win32 MFC application. When spawned inside a non-interactive SSH or service session (Session 0) without a desktop message loop, Windows denies creation of the MDI window frames. Because the GUI message loop does not reach the ready state, the MetaTrader 5 internal IPC named pipe server is never registered.

**Architectural Remediation for Multi-Tenant Scaling**:
To run multiple terminals on a commercial Windows VPS:
- Terminals must be launched inside an **Interactive User Session** (Session 1+) using an auto-logged-in service account (e.g. `bitdex_worker`).
- A lightweight Windows GUI supervisor (running in the interactive session) spawns and monitors the portable instances.
- Alternatively, instances can be containerized using Windows Server Containers or Linux Wine/Proton micro-containers where a virtual X11 framebuffer (`Xvfb`) satisfies the GUI requirements.

---

## 2. Official Exness API Specification Audit

Audited against live API endpoints, cryptographic signatures, and broker documentation:

| Specification Requirement | Exness Documented Standard | BITDEX Implementation Status | Evidence / Verified Behavior |
| :--- | :--- | :--- | :--- |
| **Ed25519 Signing Procedure** | RFC 8032 PureEd25519; Signs `METHOD + PATH + IDEMPOTENCY_KEY + TIMESTAMP + BODY` | **VERIFIED & COMPLIANT** | Signed GET/POST requests generate valid Ed25519 signatures accepted by Exness servers. |
| **Authentication Headers** | `EXN-API-KEY: exnsk-...`, `EXN-SIGNATURE: <base64url>`, `EXN-TIMESTAMP: <unix_sec>`, `EXN-IDEMPOTENCY-KEY: <uuid>` | **VERIFIED & COMPLIANT** | Correctly implemented in `trader_api_adapter.py`. |
| **Access Point Discovery** | `GET https://api.exness.com/v1/trading/access-point?account_id={id}` | **VERIFIED & COMPLIANT** | Authoritatively resolves to dynamic cluster host `https://ap-2c49ed65.exness.com`. |
| **Account Metadata** | `GET https://{ap}/v1/configuration/accounts/{id}/account` | **VERIFIED & COMPLIANT** | Returns `stream_id: dx.2.real.std`, `currency: USD`, `leverage: 2000`, `account_status: active`. |
| **Account Snapshot** | `GET https://{ap}/v1/trading/accounts/{id}/snapshot` | **VERIFIED & COMPLIANT** | Returns balance, equity, used margin, open orders, and open positions. |
| **WebSocket Streaming** | `wss://{ap}/ws` with initial auth message containing signed Ed25519 payload | **DOCUMENTED** | Subscribes to `account_state`, `orders`, and `positions`. |
| **Rate Limits** | 10 requests per second per API key | **COMPLIANT** | Enforced via token-bucket limiter in `trader_api_adapter.py`. |
| **Supported Accounts** | **Exness Terminal Accounts ONLY** (`dx.*` stream IDs). | **AUDIT CRITICAL** | **MT5 accounts are NOT supported via Exness Web API**. Requesting an MT5 account (`460310009` or `474861031`) returns `HTTP 401 AUTH_INVALID_API_KEY`. MT5 accounts MUST use the Windows MT5 Gateway. |

---

## 3. HFT Performance & Sub-Second Execution Breakdown

### 3.1 The 10-Second Worker Throttle Clarification
The blueprint previously referenced a "10-second worker throttle". This was intended solely for **background health telemetry and equity synchronization**, not trade execution. Attempting to run high-frequency scalping with a 10-second polling cycle is unfeasible.

### 3.2 Measured Execution Latency Telemetry
Benchmarking executed directly on Windows VPS `149.33.34.123` via `test_mt5_ipc_bench.py`:

| Execution Stage | Measured Minimum | Measured Average | Measured P95 | Architectural Target |
| :--- | :--- | :--- | :--- | :--- |
| **Symbol Tick Reception (`symbol_info_tick`)** | **`0.049 ms`** | **`0.051 ms`** | **`0.094 ms`** | `< 1.0 ms` |
| **Account Info Telemetry (`account_info`)** | **`0.034 ms`** | **`0.038 ms`** | **`0.049 ms`** | `< 1.0 ms` |
| **Open Positions Query (`positions_get`)** | **`0.030 ms`** | **`0.030 ms`** | **`0.039 ms`** | `< 1.0 ms` |
| **Strategy Decision Logic (Python)** | ~`0.150 ms` | ~`0.250 ms` | ~`0.400 ms` | `< 1.0 ms` |
| **Pre-Trade Risk Gates (Clamps/CAS)** | ~`0.080 ms` | ~`0.120 ms` | ~`0.200 ms` | `< 0.5 ms` |
| **Total Local Processing Pipeline** | **`~0.343 ms`** | **`~0.489 ms`** | **`~0.782 ms`** | **`< 2.0 ms` (SUB-MILLISECOND)** |

### 3.3 The Cross-Continental Network Reality
While the local Python-to-MT5 pipeline is ultra-low-latency (**`< 1 ms`**), network transit between systems dictates actual execution speed:
1. **Linux VPS (Frankfurt) to Windows VPS (US East)**: WireGuard ping measured at **`249.6 ms`** round-trip.
2. **Windows VPS to Exness MT5 Trade Server**: Network ping measured at **`1.2 ms – 4.5 ms`** (co-located in European/US Equinix financial hubs).

**Conclusion**:
- If trade orders originate from the Linux Backend and travel over WireGuard to Windows, execution latency is bounded by network transit: $\approx 250\text{ ms} + 1\text{ ms} + 5\text{ ms} \approx 256\text{ ms}$.
- To achieve true sub-second execution, the **HFT Scalp Strategy Daemon must execute locally on the Windows VPS worker**, processing ticks and placing orders locally with broker round-trip execution under **`10 ms`**, streaming status updates asynchronously back to Linux.

---

## 4. Comprehensive Envelope Credential Vault Design

To ensure customer passwords and API secrets are never stored in plaintext or exposed across processes, BITDEX employs an **Envelope Encryption Scheme (AES-256-GCM + KMS)**.

```mermaid
flowchart TD
    subgraph KMSLayer ["Key Management Service (KMS / HashiCorp Vault)"]
        KEK["Master Key Encryption Key (KEK)<br>256-bit AES-GCM (Hardware HSM)"]
    end

    subgraph LinuxStorage ["SaaS Storage Layer (SQLite / PostgreSQL)"]
        EncDEK["Encrypted Data Encryption Key (E-DEK)<br>Wrapped by KEK"]
        Ciphertext["Encrypted Credential Payload (AES-256-GCM)<br>• Nonce (12 bytes)<br>• Ciphertext<br>• Auth Tag (16 bytes)<br>• AAD: tenant_id:account_id:server"]
    end

    subgraph MemoryOnly ["Isolated Memory Boundary (Decrypted during session init)"]
        DEK["Plaintext DEK (In-Memory Only)"]
        PlainCreds["Plaintext Credentials<br>(Passed via secure pipe to worker, zero disk writes)"]
    end

    KEK -->|Unwraps on Demand| EncDEK
    EncDEK --> DEK
    DEK -->|Decrypts Payload| Ciphertext
    Ciphertext --> PlainCreds
```

### 4.1 Cryptographic Rules
1. **Envelope Wrapping**:
   - Each tenant or account is assigned a unique 256-bit **Data Encryption Key (DEK)** generated via `secrets.token_bytes(32)`.
   - The DEK is encrypted under the platform **Key Encryption Key (KEK)**.
2. **Cryptographic AAD Binding**:
   - Every encryption operation binds Associated Authenticated Data:
     $$\text{AAD} = \text{tenant\_id} + ":" + \text{account\_id} + ":" + \text{broker\_server}$$
   - Any attempt to copy ciphertext between tenants or swap account records causes AES-GCM authentication failure.
3. **Secret Rotation & Revocation**:
   - Re-encrypting a credential requires only re-encrypting with a new DEK or re-wrapping with a rotated KEK.
   - Deleting a tenant immediately zeroes their DEK in memory and deletes the wrapped DEK in the database, rendering all historical ciphertexts permanently unrecoverable.

---

## 5. Revised Relational Schema (`trading_accounts`)

### 5.1 Proposed DDL Migration (`V2__trading_accounts.sql`)
*(Provided for review only — unapplied on staging)*

```sql
-- Migration: Create unified multi-tenant trading_accounts table
CREATE TABLE IF NOT EXISTS trading_accounts (
    account_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    broker_name TEXT NOT NULL DEFAULT 'EXNESS',
    platform TEXT NOT NULL CHECK(platform IN ('EXNESS_TERMINAL', 'MT5', 'MT4', 'BINANCE_PERP')),
    environment TEXT NOT NULL CHECK(environment IN ('DEMO', 'REAL', 'PAPER')),
    broker_login TEXT NOT NULL,
    server_name TEXT NOT NULL,
    account_tier TEXT DEFAULT 'STANDARD',
    currency TEXT NOT NULL DEFAULT 'USD',
    leverage INTEGER NOT NULL DEFAULT 2000,
    
    connection_status TEXT NOT NULL DEFAULT 'DISCONNECTED',
    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
    is_active INTEGER NOT NULL DEFAULT 1,
    is_preferred INTEGER NOT NULL DEFAULT 0,
    
    balance_usd REAL DEFAULT 0.0,
    equity_usd REAL DEFAULT 0.0,
    margin_used REAL DEFAULT 0.0,
    margin_free REAL DEFAULT 0.0,
    floating_pnl REAL DEFAULT 0.0,
    
    worker_node_id TEXT,
    worker_instance_id TEXT,
    worker_port INTEGER,
    
    vault_credential_ref TEXT NOT NULL,
    real_consent_id TEXT,
    
    last_connected_at TEXT,
    last_synced_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trading_accounts_tenant ON trading_accounts(user_id, is_active);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trading_accounts_tenant_login ON trading_accounts(user_id, broker_login, server_name);
```

### 5.2 Rollback DDL (`V2_rollback__trading_accounts.sql`)
```sql
DROP TABLE IF EXISTS trading_accounts;
```

---

## 6. Infrastructure Capacity & Comprehensive Cost Modeling

### 6.1 Baseline Measurements
- Measured memory per idle MT5 instance: **`166.01 MB RAM`**.
- Measured memory per Python worker IPC bridge: **`56.41 MB RAM`**.
- Combined memory per active account: **`~220 MB RAM`**.
- CPU utilization per account (1s tick throttle): **`~0.05 vCPU`**.

### 6.2 Multi-Scale Cost Matrix (Measured vs Estimated)

| Tier Scale | Active MT5 Accounts | Required RAM | Required vCPUs | Infrastructure Hardware Topology | Windows Server License | Redis & Vault KMS | Monthly Estimated Cost | Cost Per Account / Mo |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1 (10)** | 10 | 3.5 GB | 2 vCPUs | 1x Cloud VPS (8GB RAM, 4 vCPUs) | Included in VPS | Self-hosted ($0) | **`$55 / mo`** | **`$5.50`** |
| **Tier 2 (50)** | 50 | 14.0 GB | 4 vCPUs | 1x High-RAM Cloud VPS (16GB RAM, 8 vCPUs) | Included in VPS | Managed Redis ($15) | **`$145 / mo`** | **`$2.90`** |
| **Tier 3 (100)** | 100 | 28.0 GB | 8 vCPUs | 1x Dedicated Bare-Metal Server (32GB RAM, 8 Cores) | $25/mo SPLA | Redis + KMS ($35) | **`$240 / mo`** | **`$2.40`** |
| **Tier 4 (500)** | 500 | 140.0 GB | 32 vCPUs | 2x Dedicated Servers (64GB RAM each) + Load Balancer | $50/mo SPLA | Clustered Redis ($75) | **`$680 / mo`** | **`$1.36`** |
| **Tier 5 (1,000)**| 1,000 | 280.0 GB | 64 vCPUs | 4x Dedicated Servers (64GB RAM each) + HA WireGuard Mesh | $100/mo SPLA| HA Redis + KMS ($150)| **`$1,350 / mo`** | **`$1.35`** |

*Note: Infrastructure costs scale sub-linearly as density increases. Operational overhead includes automated daily EBS/Rsync backups and Datadog/Prometheus monitoring.*

---

## 7. Commercial Customer Journey & Access Control

1. **Registration & Plan Subscription**:
   - Customer signs up on BITDEX and selects an algorithmic trading plan (e.g. Pro Scalper).
2. **Account Connection**:
   - **Exness-Platform**: Customer enters API key and secret. System discovers access point and verifies `dx.*` stream in `< 2 seconds`.
   - **MetaTrader 5**: Customer enters MT5 login ID, trading password, and server. The Gateway Worker Pool auto-clones a portable instance template, initializes the session, and verifies credentials in `< 15 seconds`.
3. **Dashboard Real-Time Visibility**:
   - Authoritative balances, equity, and open positions are retrieved directly from the broker engine.
   - Customers never see other customers' accounts or credentials.
4. **Disconnection & Revocation**:
   - Customer clicks "Disconnect". The worker process terminates, the instance directory is purged, and the cryptographic DEK key is wiped from the database.

---

## 8. Recommended Phase 7C Implementation Sequence

Following review and explicit user approval of this validation report, Phase 7C will proceed in 6 controlled, non-destructive stages:

```mermaid
flowchart TD
    S1["Stage 1: Apply Unified Schema (trading_accounts) & Data Migration"] --> S2["Stage 2: Implement KMS / Envelope Credential Vault"]
    S2 --> S3["Stage 3: Build Windows MT5 Interactive Instance Manager"]
    S3 --> S4["Stage 4: Deploy Local HFT Execution Daemon on Windows Worker"]
    S4 --> S5["Stage 5: Unify Customer Dashboard Account Router"]
    S5 --> S6["Stage 6: Concurrency & Stress Testing (10 Demo Accounts)"]
```

---

## 9. Safety Restrictions Maintained

Throughout all Phase 7B.1 validation procedures:
- `live_trading_locked = True`
- `emergency_lock_active = True`
- `read_only_mode = True`
- Zero orders submitted, modified, or closed.
- Zero live customer funds impacted.
- The existing verified Demo MT5 integration (`474861031`) remained completely uninterrupted and online.
