# Custom Alpine Linux Image Builder for Raspberry Pi

<img  alt="alpinepi_logo" src="https://github.com/user-attachments/assets/d6e18a03-1251-41eb-950d-0113be5e2a54" />


A lightweight, cross-platform Python wrapper that uses Docker to build a custom, pre-configured **Alpine Linux (armhf)** disk image for Raspberry Pi.

This builder creates a minimal (512MB) image with essential drivers, Wi-Fi support, SSH (Dropbear), and auto-configuration scripts pre-installed.

## 🚀 Features

* **⚡ Lightweight:** Base image size is set to **512MB** (expandable).
* **📶 Wi-Fi Ready:** Includes critical firmware (`brcmfmac`, `cypress`) and tools (`iwd`, `iw`, `wpa_supplicant`).
* **🛠️ Pre-Configured Services:**
    * **IWD WiFi:** Uses `setup-interfaces-iwd` to switch to a modern and easy-to-use `wpa_supplicant` replacement.
    * **Dropbear SSH:** Enabled by default with root login allowed.
    * **Auto-Resize:** Automatically expands the root partition to fill your SD card on the first boot.
    * **IP Display:** Clearly prints the Wi-Fi IP address to the console on boot.
    * **Auto-Mirrors:** Automatically detects and configures the fastest Alpine package mirrors once online.
* **🐳 Dockerized Build:** Runs entirely inside a container—no mess on your host machine. Works on Windows, macOS, and Linux.
* **🔧 Customizable:** Injects your own `config.txt`, `cmdline.txt`, and setup scripts.

## 📋 Prerequisites

1.  **Docker:** Ensure Docker is installed and running.
    * `sudo apt install docker.io` (Linux)
    * [Get Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac)
2.  **Python 3:** Required to run the build wrapper script.

🛠️ **Usage**
1. Run the Builder

Open your terminal in the project directory and run:
Bash

python3 build.py

2. **Flash the Image**

Once the build finishes, you will see a file named similar to: alpine-rpi-armhf-v3.23-20251214-123000.img.gz

Flash this file to your SD card using Raspberry Pi Imager or a similar tool.

🧩 **Customization**

To change the image properties, edit the variables at the top of build.py:
Python

```
ARCH = "armhf"           # Architecture (armhf, aarch64, etc.)
ALPINE_BRANCH = "v3.23"  # Alpine version
IMAGE_SIZE_MB = 512      # Initial image size (in MB)
```


## 📂 Project Structure

Ensure your directory contains the following files before running the builder:

```
text
.
├── build.py                   # The main Python build script
├── config.txt                 # Raspberry Pi boot configuration
├── cmdline.txt                # Kernel command line arguments
└── setup-interfaces-iwd.sh    # Custom script copied to /usr/sbin/
```
