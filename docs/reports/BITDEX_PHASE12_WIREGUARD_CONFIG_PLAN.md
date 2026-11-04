# BITDEX — Phase 12: WireGuard Tunnel Configuration Plan

**Topology:** Point-to-Point Secure Tunnel  
**Linux Staging:** `10.88.0.1/24` (Public IP: `169.58.218.168`, UDP Port: `51820`)  
**Windows VPS:** `10.88.0.2/24` (Public IP: `<WINDOWS_VPS_PUBLIC_IP>`)  
**Date:** November 5, 2026  

---

## 1. Cryptographic Principles & Rules
- **Zero Inventions:** Private keys must never be pre-invented or hardcoded in templates. Each host must generate its own private key locally.
- **Mutual Exchange:** Only public keys and public endpoints are exchanged between peers.
- **Port Security:** Gateway port `8001` listens strictly on the internal WireGuard tunnel IP `10.88.0.2` and is never exposed to the public Internet.

---

## 2. Linux Configuration Template (`/etc/wireguard/wg0.conf`)

### Step 2.1: Key Generation on Linux Staging
To be executed on `169.58.218.168`:
```bash
apt-get update && apt-get install -y wireguard
umask 077
wg genkey | tee /etc/wireguard/linux_private.key | wg pubkey > /etc/wireguard/linux_public.key
```

### Step 2.2: `/etc/wireguard/wg0.conf` Template
```ini
[Interface]
# Linux Staging Gateway Endpoint
Address = 10.88.0.1/24
ListenPort = 51820
PrivateKey = <CONTENTS_OF_/etc/wireguard/linux_private.key>
SaveConfig = false

# PostUp firewall rules to allow traffic across tunnel
PostUp = ufw allow in on wg0 to any port 8002 proto tcp
PostUp = ufw allow 51820/udp
PostDown = ufw delete allow 51820/udp

[Peer]
# Windows MT5 Gateway Host
PublicKey = <WINDOWS_HOST_PUBLIC_KEY>
AllowedIPs = 10.88.0.2/32
Endpoint = <WINDOWS_VPS_PUBLIC_IP>:51820
PersistentKeepalive = 25
```

---

## 3. Windows Configuration Template (`C:\Program Files\WireGuard\Data\Configurations\wg0.conf`)

### Step 3.1: Key Generation on Windows Host
Executed in elevated PowerShell or WireGuard GUI on the Windows VPS:
```powershell
$priv = wg genkey
$pub = $priv | wg pubkey
$priv | Out-File -Encoding ascii "C:\BitdexGateway\windows_private.key"
$pub | Out-File -Encoding ascii "C:\BitdexGateway\windows_public.key"
```

### Step 3.2: Configuration Template for Windows
```ini
[Interface]
# Windows MT5 Host Endpoint
Address = 10.88.0.2/24
PrivateKey = <CONTENTS_OF_windows_private.key>

[Peer]
# Linux Staging Server
PublicKey = <LINUX_HOST_PUBLIC_KEY>
AllowedIPs = 10.88.0.0/24
Endpoint = 169.58.218.168:51820
PersistentKeepalive = 25
```

---

## 4. Activation & Verification Sequence

1. **Firewall Open on Linux:**
   ```bash
   ufw allow 51820/udp
   ```
2. **Bring Up Linux Tunnel:**
   ```bash
   systemctl enable --now wg-quick@wg0
   ```
3. **Bring Up Windows Tunnel:**
   In WireGuard UI, click "Activate" on tunnel `wg0`.
4. **Handshake Verification (Linux side):**
   ```bash
   wg show wg0
   # Expected: latest handshake: 10 seconds ago, transfer: XX KiB received, YY KiB sent
   ```
5. **Bidirectional ICMP Ping:**
   ```bash
   # From Linux to Windows
   ping -c 3 10.88.0.2
   ```
6. **HTTP Gateway Verification:**
   ```bash
   curl -s -m 5 -H "X-Gateway-Auth-Token: <TOKEN>" http://10.88.0.2:8001/health
   ```
