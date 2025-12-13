# Custom Alpine Linux Image Builder for Raspberry Pi

A lightweight, cross-platform Python wrapper that uses Docker to build a custom, pre-configured **Alpine Linux (armhf)** disk image for Raspberry Pi.

This builder creates a minimal (512MB) image with essential drivers, Wi-Fi support, SSH (Dropbear), and auto-configuration scripts pre-installed.

## 🚀 Features

* **⚡ Lightweight:** Base image size is set to **512MB** (expandable).
* **📶 Wi-Fi Ready:** Includes critical firmware (`brcmfmac`, `cypress`) and tools (`iwd`, `iw`, `wpa_supplicant`).
* **🛠️ Pre-Configured Services:**
    * **Dropbear SSH:** Enabled by default with root login allowed.
    * **Auto-Resize:** Automatically expands the root partition to fill your SD card on the first boot.
    * **IP Display:** Clearly prints the Wi-Fi IP address to the console on boot.
    * **Auto-Mirrors:** Automatically detects and configures the fastest Alpine package mirrors once online.
* **🐳 Dockerized Build:** Runs entirely inside a container—no mess on your host machine. Works on Windows, macOS, and Linux.
* **🔧 Customizable:** Injects your own `config.txt`, `cmdline.txt`, and setup scripts.

## 📋 Prerequisites

1.  **Docker:** Ensure Docker is installed and running.
    * [Get Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac)
    * `sudo apt install docker.io` (Linux)
2.  **Python 3:** Required to run the build wrapper script.

## 📂 Project Structure

Ensure your directory contains the following files before running the builder:

```text
.
├── build.py                   # The main Python build script
├── config.txt                 # Raspberry Pi boot configuration
├── cmdline.txt                # Kernel command line arguments
└── setup-interfaces-iwd.sh    # Custom script copied to /usr/sbin/
