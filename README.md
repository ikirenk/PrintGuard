# 🖨️ PrintGuard

**🇬🇧 English** | [🇹🇷 Türkçe](README.tr.md)

**PrintGuard** is a lightweight Flask server that manages CUPS network/USB printers through a web UI, optically verifies every printed page using a **USB webcam + ArUco 4x4 markers + CMYK ink patches + binary page strip**, orchestrates manual duplex batch printing, and tracks per-user page counts.

> **🐧 Tested on DietPi:** This project has been tested on **DietPi** (a lightweight Debian-based Linux distribution) with CUPS and a USB webcam. It is designed to run 24/7 with minimal footprint on SBCs like Raspberry Pi, Orange Pi, and similar devices.

---

## ✨ Features

- **Web Control Panel:** Upload PDFs, select CUPS queues, toggle grayscale/color, add page numbers, and monitor a live camera stream (`/video_feed`).
- **Optical Print Verification:** Stamps ArUco (900/901) anchors, CMYK patches, and a 15-bit page number strip on each page and verifies them via webcam after printing—automatically pausing on ink/paper issues.
- **Smart Duplex Batch Orchestration:** Guides users through reverse-even (`10,8,6,4,2 -> 1,3,5,7,9`) or normal duplex printing in configurable sheet batches.
- **User Management & Page Counter:** Manage users and passwords directly from the Web UI (**Kullanıcı Yönetimi**) or via `users.json`, with per-user monthly page counters and admin-only reset.
- **Tailscale Compatible:** Binds to `0.0.0.0:5000` by default, making it immediately accessible over your Tailscale network without router port forwarding.

---

## 🌐 Tailscale Compatibility

PrintGuard listens on all network interfaces (`0.0.0.0:5000`) and orders its systemd unit after `tailscaled.service`.

1. Once Tailscale is running on your host, access the web panel from any device in your Tailnet:
   ```text
   http://<tailscale-ip>:5000
   ```
   Or via MagicDNS:
   ```text
   http://<hostname>:5000
   ```
2. Optionally expose it over HTTPS inside your Tailnet with:
   ```bash
   tailscale serve --bg 5000
   ```

---

## 🚀 Installation (DietPi / Debian)

### 1. Install System Dependencies
```bash
sudo apt update
sudo apt install -y git python3 python3-pip python3-venv cups libgl1 libglib2.0-0
```
*(Optional: On ARM boards, you can install `sudo apt install -y python3-opencv` to avoid building OpenCV from source.)*

### 2. Clone into `/opt/printguard`
```bash
sudo mkdir -p /opt/printguard
sudo git clone <REPO_URL> /opt/printguard
cd /opt/printguard
```

### 3. Create a Virtual Environment & Install Python Packages
```bash
sudo python3 -m venv /opt/printguard/venv
sudo /opt/printguard/venv/bin/pip install --upgrade pip
sudo /opt/printguard/venv/bin/pip install -r /opt/printguard/requirements.txt
```

### 4. User Configuration (`users.json`)
You can copy and edit the example config:
```bash
sudo cp /opt/printguard/users.example.json /opt/printguard/users.json
sudo nano /opt/printguard/users.json
```
If `users.json` does not exist on first launch, PrintGuard automatically creates one with a default admin account:
- **Username:** `admin`
- **Password:** `admin`

> ⚠️ **Security Note:** Change the default `admin` password immediately after your first login using the **Şifre Değiştir** form in the Web UI. `users.json` is excluded in `.gitignore`.

---

## ⚙️ Systemd Service Setup

Use the included [`printguard.service`](printguard.service) file to run PrintGuard as a background service on boot:

```bash
# Copy the service unit file
sudo cp /opt/printguard/printguard.service /etc/systemd/system/printguard.service

# Reload systemd
sudo systemctl daemon-reload

# Enable on boot and start immediately
sudo systemctl enable --now printguard
```

### Useful Service Commands
```bash
# Check service status
sudo systemctl status printguard

# Follow live logs
sudo journalctl -u printguard -f

# Restart the service
sudo systemctl restart printguard

# Stop the service
sudo systemctl stop printguard
```

---

## 🔧 Environment Variables (Optional)

You can customize these in `printguard.service` or your shell:

| Variable | Default | Description |
|---|---|---|
| `PRINTGUARD_HOST` | `0.0.0.0` | Bind address |
| `PRINTGUARD_PORT` | `5000` | Web UI port |
| `PRINTGUARD_LANG` | `en` | Default UI & server language (`en` or `tr`) |
| `PRINTGUARD_CAMERA_INDEX` | `0` | OpenCV camera index (`/dev/video0`) |
| `PRINTGUARD_WORKSPACE` | `/opt/printguard/printguard_workspace` | Archives, counters, and logs directory |
| `PRINTGUARD_USERS_FILE` | `/opt/printguard/users.json` | Path to user config JSON |
| `PRINTGUARD_SOUND_FILE` | `/opt/printguard/a.mp3` | Optional completion sound file |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
