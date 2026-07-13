#!/usr/bin/env bash
# @file test/qemu_manual.sh
# Interactive LPSS test in QEMU.
# Prepares a disk image with two Alpine slots (slot-a, slot-b),
# installs LPSS and boots using the host's GRUB tools.
#
# Uses filesystem labels (label:root.a, label:root.b) for maximum
# compatibility. Host kernel and initrd are located automatically
# via lib.utils. Generated configs are saved in the work directory.
#
# To start completely clean:  rm -rf <WORK_DIR>

set -euo pipefail

WORK_DIR="${1:-build/qemu-test}"
WORK_DIR_ABS="$(cd "$(dirname "$WORK_DIR")" 2>/dev/null && pwd)/$(basename "$WORK_DIR")"
CACHE_DIR="cache"

ALPINE_BASE="https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64"
MINIRT_URL="${ALPINE_BASE}/alpine-minirootfs-3.24.1-x86_64.tar.gz"
MINIRT_TAR="alpine-minirootfs-3.24.1-x86_64.tar.gz"

# Locate LPSS tools
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -x "$PROJECT_DIR/lpss_install.py" ]]; then
    LPSS_INSTALL="$PROJECT_DIR/lpss_install.py"
    LPSS_IMPORT="$PROJECT_DIR/lpss_import.py"
    LPSS_CTL="$PROJECT_DIR/lpss_ctl.py"
elif command -v lpss_install >/dev/null 2>&1; then
    LPSS_INSTALL="lpss_install"
    LPSS_IMPORT="lpss_import"
    LPSS_CTL="lpss_ctl"
else
    echo "ERROR: LPSS tools not found." >&2
    exit 1
fi

# OVMF firmware
find_ovmf() {
    local candidates_code=(
        /usr/share/qemu/ovmf-x86_64-4m-code.bin /usr/share/qemu/ovmf-x86_64-code.bin
        /usr/share/edk2-ovmf/OVMF_CODE.fd /usr/share/edk2/ovmf/OVMF_CODE.fd
        /usr/share/OVMF/OVMF_CODE.fd /usr/share/qemu-ovmf/OVMF_CODE.fd
    )
    local candidates_vars=(
        /usr/share/qemu/ovmf-x86_64-4m-vars.bin /usr/share/qemu/ovmf-x86_64-vars.bin
        /usr/share/edk2-ovmf/OVMF_VARS.fd /usr/share/edk2/ovmf/OVMF_VARS.fd
        /usr/share/OVMF/OVMF_VARS.fd /usr/share/qemu-ovmf/OVMF_VARS.fd
    )
    for code in "${candidates_code[@]}"; do
        if [[ -f "$code" ]]; then
            OVMF_CODE="$code"
            break
        fi
    done
    for vars in "${candidates_vars[@]}"; do
        if [[ -f "$vars" ]]; then
            OVMF_VARS="$vars"
            break
        fi
    done
    if [[ -z "${OVMF_CODE:-}" ]] || [[ -z "${OVMF_VARS:-}" ]]; then
        echo "ERROR: OVMF firmware files not found." >&2
        exit 1
    fi
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}
step() { echo "==> $*"; }

check_deps() {
    step "Checking host dependencies"
    command -v qemu-system-x86_64 >/dev/null || die "Missing qemu-system-x86_64"
    command -v wget >/dev/null || die "Missing wget"
    sudo -n true 2>/dev/null || die "sudo not available or requires a password."
    find_ovmf
}

download_if_missing() {
    local url="$1" dest="$2"
    mkdir -p "$CACHE_DIR"
    if [[ -f "$dest" ]]; then
        echo "[cache] $dest already exists"
        return 0
    fi
    echo "[download] $url -> $dest"
    wget -q --show-progress -O "$dest" "$url"
}

main() {
    check_deps
    mkdir -p "$WORK_DIR_ABS"
    cd "$WORK_DIR_ABS" || die "Cannot enter $WORK_DIR_ABS"
    rm -f lpss.conf grub.cfg

    # Locate host kernel and initrd using lib.utils
    export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}"
    KERNEL_SRC=$(python3 -c "from lib.utils import find_host_kernel; print(find_host_kernel())")
    INITRD_SRC=$(python3 -c "from lib.utils import find_host_initrd; print(find_host_initrd())")

    if [[ -z "$KERNEL_SRC" ]] || [[ -z "$INITRD_SRC" ]]; then
        die "Could not find host kernel/initrd. Check /boot or /usr/lib/modules."
    fi
    if [[ ! -f "$KERNEL_SRC" ]]; then die "Kernel file not found: $KERNEL_SRC"; fi
    if [[ ! -f "$INITRD_SRC" ]]; then die "Initrd file not found: $INITRD_SRC"; fi

    KERNEL_NAME="vmlinuz-host"
    INITRD_NAME="initramfs-host"

    step "Downloading Alpine rootfs"
    download_if_missing "$MINIRT_URL" "$CACHE_DIR/$MINIRT_TAR"

    DISK_IMG="disk.img"
    step "Creating disk image (1.5 GiB)"
    rm -f "$DISK_IMG"
    dd if=/dev/zero of="$DISK_IMG" bs=1M count=1536 status=progress
    sudo parted -s "$DISK_IMG" mklabel gpt
    sudo parted -s "$DISK_IMG" mkpart primary fat32 1MiB 129MiB
    sudo parted -s "$DISK_IMG" set 1 esp on
    sudo parted -s "$DISK_IMG" mkpart primary ext4 129MiB 385MiB
    sudo parted -s "$DISK_IMG" mkpart primary ext4 385MiB 897MiB
    sudo parted -s "$DISK_IMG" mkpart primary ext4 897MiB 1409MiB
    sudo parted -s "$DISK_IMG" name 3 root.a
    sudo parted -s "$DISK_IMG" name 4 root.b
    LOOP=$(sudo losetup --show -fP "$DISK_IMG")
    sudo mkfs.vfat "${LOOP}p1"
    sudo mkfs.ext4 -F -L root.a "${LOOP}p3"
    sudo mkfs.ext4 -F -L root.b "${LOOP}p4"
    sudo mkfs.ext4 -F "${LOOP}p2"
    sudo losetup -d "$LOOP"

    step "Mounting partitions"
    LOOP=$(sudo losetup --show -fP "$DISK_IMG")
    sudo mkdir -p mnt/esp mnt/lpss mnt/root_a mnt/root_b
    sudo mount "${LOOP}p1" mnt/esp
    sudo mount "${LOOP}p2" mnt/lpss
    sudo mount "${LOOP}p3" mnt/root_a
    sudo mount "${LOOP}p4" mnt/root_b

    cleanup() {
        set +e
        echo "Cleaning up mounts and loop"
        sudo umount mnt/root_a mnt/root_b mnt/lpss mnt/esp 2>/dev/null
        sudo losetup -d "$LOOP" 2>/dev/null
        sudo rm -rf mnt
    }
    trap cleanup EXIT

    step "Populating slots with Alpine rootfs and host kernel"
    sudo tar xzf "$CACHE_DIR/$MINIRT_TAR" -C mnt/root_a
    sudo tar xzf "$CACHE_DIR/$MINIRT_TAR" -C mnt/root_b
    echo "slot-a" | sudo tee mnt/root_a/etc/hostname >/dev/null
    echo "slot-b" | sudo tee mnt/root_b/etc/hostname >/dev/null
    sudo mkdir -p mnt/root_a/boot mnt/root_b/boot
    sudo cp "$KERNEL_SRC" "mnt/root_a/boot/$KERNEL_NAME"
    sudo cp "$INITRD_SRC" "mnt/root_a/boot/$INITRD_NAME"
    sudo cp "$KERNEL_SRC" "mnt/root_b/boot/$KERNEL_NAME"
    sudo cp "$INITRD_SRC" "mnt/root_b/boot/$INITRD_NAME"

    step "Installing LPSS"
    sudo rm -f mnt/lpss/grub.cfg mnt/lpss/grub2/grub.cfg
    sudo "$LPSS_INSTALL" --lpss-dir "$(pwd)/mnt/lpss" --esp-dir "$(pwd)/mnt/esp" \
        --grub-install-extra="--removable --no-nvram"

    step "Importing slots"
    sudo "$LPSS_IMPORT" --lpss-dir "$(pwd)/mnt/lpss" \
        --root "$(pwd)/mnt/root_a" --id slot-a --locator label:root.a \
        --linux "/boot/$KERNEL_NAME" --initrd "/boot/$INITRD_NAME" \
        --options "ro "
    sudo "$LPSS_IMPORT" --lpss-dir "$(pwd)/mnt/lpss" \
        --root "$(pwd)/mnt/root_b" --id slot-b --locator label:root.b \
        --linux "/boot/$KERNEL_NAME" --initrd "/boot/$INITRD_NAME" \
        --options "ro "

    step "Activating slot-a"
    sudo "$LPSS_CTL" --lpss-dir "$(pwd)/mnt/lpss" enable slot-a
    sudo "$LPSS_CTL" --lpss-dir "$(pwd)/mnt/lpss" activate slot-a
    sudo "$LPSS_CTL" --lpss-dir "$(pwd)/mnt/lpss" apply

    if [[ -d mnt/lpss/grub2 ]]; then
        GRUB_DIR="mnt/lpss/grub2"
    else GRUB_DIR="mnt/lpss/grub"; fi

    echo "Saving configs to $WORK_DIR_ABS/"
    sudo cp mnt/lpss/lpss.conf "$WORK_DIR_ABS/lpss.conf"
    sudo cp "$GRUB_DIR/grub.cfg" "$WORK_DIR_ABS/grub.cfg"

    if command -v grub2-script-check >/dev/null; then
        echo "Checking grub.cfg syntax..."
        grub2-script-check "$GRUB_DIR/grub.cfg" || echo "WARNING: syntax error"
    fi

    echo "=== LPSS CONFIG ==="
    cat "$WORK_DIR_ABS/lpss.conf"
    echo "=== GENERATED GRUB.CFG ==="
    cat "$WORK_DIR_ABS/grub.cfg"

    echo "Syncing filesystems..."
    sudo sync
    cleanup
    trap - EXIT

    step "Preparing UEFI firmware"
    cp "$OVMF_VARS" vars.fd

    step "Starting QEMU (Ctrl-A X to exit)"
    # qemu-system-x86_64 \
    #     -machine q35 -m 512 \
    #     -drive file="$DISK_IMG",format=raw,if=virtio \
    #     -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
    #     -drive if=pflash,format=raw,file=vars.fd \
    #     -nographic -serial mon:stdio

    qemu-system-x86_64 \
        -enable-kvm \
        -cpu host \
        -smp 2 \
        -machine q35 -m 512 \
        -drive file="$DISK_IMG",format=raw,if=virtio \
        -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
        -drive if=pflash,format=raw,file=vars.fd \
        -display gtk \
        -monitor stdio

    echo "QEMU exited. Disk image kept at $WORK_DIR_ABS/$DISK_IMG."
    echo "Configs saved as $WORK_DIR_ABS/lpss.conf and $WORK_DIR_ABS/grub.cfg"
}

main "$@"
