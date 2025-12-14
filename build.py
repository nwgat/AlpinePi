import os
import sys
import subprocess
import datetime
import platform

# --- CONFIGURATION -----------------------------------------------------------
ARCH = "armhf"
ALPINE_BRANCH = "v3.23"
IMAGE_SIZE_MB = 512
ROOTFS = "/tmp/alpine-build"
BOOTFS = "/tmp/alpine-boot"

# --- INTERNAL BUILD SCRIPT (Runs inside the Docker container) ----------------
INTERNAL_SCRIPT = f"""
set -e

# Redefine variables inside container
ARCH="{ARCH}"
ALPINE_BRANCH="{ALPINE_BRANCH}"
IMAGE_SIZE_MB={IMAGE_SIZE_MB}
ROOTFS="{ROOTFS}"
BOOTFS="{BOOTFS}"

# --- BUILD FUNCTIONS ---

setup_environment() {{
    echo "--> 1. Installing build tools and setting up directories..."
    apk add --no-cache apk-tools openrc dosfstools mtools parted e2fsprogs

    mkdir -p "$ROOTFS" "$BOOTFS"

    # Copy keys for package integrity checking
    mkdir -p "$ROOTFS/etc/apk/keys"
    cp /etc/apk/keys/* "$ROOTFS/etc/apk/keys/"
}}

install_packages() {{
    echo "--> 2. Installing base system and packages..."
    apk --root "$ROOTFS" --initdb --arch "$ARCH" \\
        --allow-untrusted \\
        --repository "http://dl-cdn.alpinelinux.org/alpine/$ALPINE_BRANCH/main" \\
        --repository "http://dl-cdn.alpinelinux.org/alpine/$ALPINE_BRANCH/community" \\
        add \\
        alpine-base \\
        alpine-conf \\
        linux-rpi \\
        raspberrypi-bootloader \\
        linux-firmware-brcm \\
        linux-firmware-cypress \\
        openresolv \\
        dbus \\
        openrc \\
        e2fsprogs \\
        e2fsprogs-extra \\
        parted \\
        nano \\
        dropbear \\
        kbd \\
        kbd-bkeymaps \\
        iwd \\
        wpa_supplicant \\
        iw
}}

configure_system() {{
    echo "--> 3. Configuring base services, Drivers, and Networking..."
    
    # Basic boot/sysinit services
    for srv in bootmisc hostname syslog modules sysctl networking urandom; do
        ln -s /etc/init.d/"$srv" "$ROOTFS/etc/runlevels/boot/$srv"
    done
    for srv in devfs dmesg mdev; do
        ln -s /etc/init.d/"$srv" "$ROOTFS/etc/runlevels/sysinit/$srv"
    done

    # Default services (Networking, D-Bus, Dropbear, NTPD)
    ln -s /etc/init.d/dbus "$ROOTFS/etc/runlevels/default/dbus"
    ln -s /etc/init.d/dropbear "$ROOTFS/etc/runlevels/default/dropbear"
    ln -s /etc/init.d/ntpd "$ROOTFS/etc/runlevels/default/ntpd"

    # --- CRITICAL FIX: ENABLE WIFI DRIVERS ---
    echo "brcmfmac" > "$ROOTFS/etc/modules"

    # Hostname
    echo "alpine-pi" > "$ROOTFS/etc/hostname"

    # Network Interfaces
    cat <<NET > "$ROOTFS/etc/network/interfaces"
auto lo
iface lo inet loopback

auto wlan0
iface wlan0 inet dhcp
NET

    # Configure Dropbear
    mkdir -p "$ROOTFS/etc/dropbear"
    
    # --- COPY CUSTOM SCRIPT ---
    echo "--> Installing custom setup-interfaces-iwd.sh..."
    if [ -f "/input/setup-interfaces-iwd.sh" ]; then
        cp /input/setup-interfaces-iwd.sh "$ROOTFS/usr/sbin/setup-interfaces-iwd.sh"
        chmod +x "$ROOTFS/usr/sbin/setup-interfaces-iwd.sh"
    else
        echo "WARNING: setup-interfaces-iwd.sh was not found inside the container."
    fi
}}

create_custom_services() {{
    echo "--> 4. Creating custom services..."

    # --- RESIZE ROOTFS SERVICE ---
    cat <<'RESIZE_SERVICE' > "$ROOTFS/etc/init.d/resize-rootfs"
#!/sbin/openrc-run
description="Expands the root partition and filesystem to fill the SD card on first boot."

depend() {{
    need localmount
    before dbus
}}

start() {{
    ebegin "Expanding root filesystem to fill SD card"
    # 1. Expand Partition Table
    parted -s /dev/mmcblk0 resizepart 2 100% || true
    # 2. Resize Filesystem
    resize2fs /dev/mmcblk0p2
    # 3. Remove this script so it doesn't run again
    rc-update del resize-rootfs default
    eend $?
}}
RESIZE_SERVICE
    chmod +x "$ROOTFS/etc/init.d/resize-rootfs"
    ln -s /etc/init.d/resize-rootfs "$ROOTFS/etc/runlevels/default/resize-rootfs"

    # --- SHOW IP SERVICE ---
    cat <<'IP_SERVICE' > "$ROOTFS/etc/init.d/show-ip"
#!/sbin/openrc-run
description="Display network IP address on the console."
depend() {{
    need local
}}
start() {{
    ebegin "Synchronizing system clock and checking IP Address"
    rc-service ntpd restart
    sleep 5 
    IP_WLAN=$(ip a show wlan0 | grep 'inet ' | awk '{{print $2}}' | cut -d/ -f1)
    
    echo -e "\\n\\n*************************************************************" > /dev/tty1
    if [ ! -z "$IP_WLAN" ]; then
        echo -e "* IP ADDRESS (WLAN0): $IP_WLAN" >> /dev/tty1
    else
        echo -e "* IP ADDRESS (WLAN0): Not found" >> /dev/tty1
    fi
    echo -e "* SSH ENABLED (Dropbear): Login as root" >> /dev/tty1
    echo -e "*************************************************************\\n\\n" >> /dev/tty1
    eend 0
}}
IP_SERVICE
    chmod +x "$ROOTFS/etc/init.d/show-ip"
    ln -s /etc/init.d/show-ip "$ROOTFS/etc/runlevels/default/show-ip"

    # --- SETUP MIRRORS SERVICE (Run Once on Success) ---
    cat <<'MIRROR_SERVICE' > "$ROOTFS/etc/init.d/setup-mirrors"
#!/sbin/openrc-run
description="Finds and configures the fastest APK repositories."
depend() {{
    after show-ip
}}
start() {{
    ebegin "Checking for active network connection"

    # 1. Fast Fail: Check if any interface has a global IP.
    if ! ip -o addr show scope global | grep -q "inet"; then
        ewarn "No global IP address detected. Will retry next boot."
        eend 0
        return 0
    fi

    ebegin "Checking internet connectivity..."
    
    # 2. Wait loop: Try pinging Google DNS (8.8.8.8)
    count=0
    while [ $count -lt 15 ]; do
        if ping -c 1 -W 1 8.8.8.8 >/dev/null 2>&1; then
            break
        fi
        sleep 1
        count=$((count+1))
    done
    
    # 3. If ping failed, exit gracefully so we try again next boot
    if [ $count -ge 15 ]; then
        ewarn "Internet unreachable. Will retry next boot."
        eend 0
        return 0
    fi

    ebegin "Internet ONLINE. Setting up fastest APK repositories..."
    
    # 4. Run setup-apkrepos
    CMD="setup-apkrepos"
    if [ -x /sbin/setup-apkrepos ]; then CMD="/sbin/setup-apkrepos"; fi
    if [ -x /usr/sbin/setup-apkrepos ]; then CMD="/usr/sbin/setup-apkrepos"; fi

    # 5. Execute command and check success
    if $CMD -1 -c > /dev/tty1 2>&1; then
        einfo "Mirrors configured successfully."
        # SUCCESS: Disable this service so it does not run again
        rc-update del setup-mirrors default
        eend 0
    else
        eerror "Failed to setup mirrors. Will retry next boot."
        eend 1
    fi
}}
MIRROR_SERVICE
    chmod +x "$ROOTFS/etc/init.d/setup-mirrors"
    ln -s /etc/init.d/setup-mirrors "$ROOTFS/etc/runlevels/default/setup-mirrors"
}}

configure_bootloader() {{
    echo "--> 5. Finalizing bootloader configuration..."
    
    # fstab
    cat <<FSTAB > "$ROOTFS/etc/fstab"
/dev/mmcblk0p1 /boot vfat defaults 0 2
/dev/mmcblk0p2 /    ext4 defaults,noatime 0 1
FSTAB

    # Copy cmdline.txt from host mount
    if [ -f "/input/cmdline.txt" ]; then
        cp /input/cmdline.txt "$ROOTFS/boot/cmdline.txt"
        echo "Copied custom cmdline.txt"
    else
        echo "WARNING: cmdline.txt not found, using default fallback"
        echo "modules=loop,squashfs,sd-mod,usb-storage quiet root=/dev/mmcblk0p2 rootfstype=ext4 console=serial0,115200 console=tty1 video=Composite-1:720x576@50ie" > "$ROOTFS/boot/cmdline.txt"
    fi

    # Copy config.txt from host mount
    if [ -f "/input/config.txt" ]; then
        cp /input/config.txt "$ROOTFS/boot/config.txt"
        echo "Copied custom config.txt"
    else
        echo "WARNING: config.txt not found, using default fallback"
        cat <<CONF > "$ROOTFS/boot/config.txt"
kernel=vmlinuz-rpi
initramfs initramfs-rpi
include usercfg.txt
dtoverlay=vc4-fkms-v3d,composite=1
dtoverlay=miniuart-max-clock=3000000
pi3-miniuart-freq=250000000
disable_overscan=1
sdtv_mode=2
sdtv_aspect=1
max_framebuffers=2
dtparam=audio=on
CONF
    fi
}}

generate_image() {{
    echo "--> 6. Generating Disk Image ($IMAGE_SIZE_MB MB)..."

    rm -rf "$ROOTFS/boot/*" 2>/dev/null || true
    mv "$ROOTFS/boot"/* "$BOOTFS/" 2>/dev/null || true

    # 1. BOOT PARTITION
    dd if=/dev/zero of=boot.img bs=1M count=256
    mkfs.vfat -n BOOT -F 32 boot.img
    mcopy -i boot.img -s "$BOOTFS"/* ::/

    # 2. ROOT PARTITION
    ROOT_SIZE=$(( $IMAGE_SIZE_MB - 260 ))
    
    # Double brackets {{ }} to pass literal shell variable to shell
    mkfs.ext4 -L ROOT -d "$ROOTFS" root.img "${{ROOT_SIZE}}M"

    # 3. COMBINE
    dd if=/dev/zero of=alpine-rpi.img bs=1M count="$IMAGE_SIZE_MB"
    parted -s alpine-rpi.img mklabel msdos
    parted -s alpine-rpi.img mkpart primary fat32 4MiB 260MiB
    parted -s alpine-rpi.img mkpart primary ext4 260MiB 100%
    parted -s alpine-rpi.img set 1 boot on

    dd if=boot.img of=alpine-rpi.img bs=1M seek=4 conv=notrunc
    dd if=root.img of=alpine-rpi.img bs=1M seek=260 conv=notrunc

    # Calculated timestamp for filename (inside container)
    TIMESTAMP_FINAL=$(date +%Y%m%d-%H%M%S)
    
    # Double curly braces {{ARCH}} ensure shell sees '${ARCH}' and substitutes 'armhf'
    FINAL_IMG_NAME_INNER="alpine-rpi-${{ARCH}}-${{ALPINE_BRANCH}}-${{TIMESTAMP_FINAL}}.img.gz"

    echo "--> Compressing to $FINAL_IMG_NAME_INNER..."
    gzip -c alpine-rpi.img > /output/"$FINAL_IMG_NAME_INNER"
    
    echo ">>> Disk Image Build Complete. Output file: $FINAL_IMG_NAME_INNER"
}}

main() {{
    setup_environment
    install_packages
    configure_system
    create_custom_services
    configure_bootloader
    generate_image
}}

main
"""

def main():
    required_files = ["setup-interfaces-iwd.sh", "config.txt", "cmdline.txt"]
    current_dir = os.getcwd()

    # 1. Check for prerequisite files
    for f in required_files:
        if not os.path.exists(f):
            print(f"Error: Required file '{f}' not found in current directory.")
            sys.exit(1)

    print(f">>> Starting Alpine Builder for {ARCH} on {platform.system()}...")

    # 2. Construct Docker Command
    docker_cmd = [
        "docker", "run", "-i", "--rm",
        "-v", f"{current_dir}:/output",
        "-v", f"{os.path.join(current_dir, 'setup-interfaces-iwd.sh')}:/input/setup-interfaces-iwd.sh",
        "-v", f"{os.path.join(current_dir, 'config.txt')}:/input/config.txt",
        "-v", f"{os.path.join(current_dir, 'cmdline.txt')}:/input/cmdline.txt",
        "alpine:latest",
        "/bin/sh"
    ]

    # 3. Execute Docker
    try:
        process = subprocess.run(
            docker_cmd,
            input=INTERNAL_SCRIPT.encode('utf-8'), 
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"\n!!! Build Failed with error code {e.returncode} !!!")
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("\n!!! Error: Docker not found. Is it installed and in your PATH? !!!")
        sys.exit(1)

if __name__ == "__main__":
    main()
