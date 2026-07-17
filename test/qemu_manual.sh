#!/usr/bin/env bash
# @file test/qemu_manual.sh
# Interactive LPSS test in QEMU using a pre-built rootfs tarball.
# The user supplies the tarball (--rootfs) that contains /boot with
# kernel/initrd.  The script creates two identical slots, changes
# their hostnames, installs LPSS and boots via QEMU.
#
# Modes:
#   Full cycle (default):  build image and start QEMU.
#   --build-only:           only build the disk image, do not start QEMU.
#   --run-only:             skip building, directly start QEMU with
#                           the existing disk.img in the work directory.
#
# Partition sizes: each root partition is as large as the unpacked
# rootfs plus a reserve (default 10% + 50 MiB absolute minimum).
#
# Usage:
#   sudo ./test/qemu_manual.sh --rootfs /path/to/rootfs.tgz
#   sudo ./test/qemu_manual.sh --rootfs /path/to/rootfs.tgz --build-only
#   sudo ./test/qemu_manual.sh --run-only --dir /path/to/workdir
#
# Requirements:
#   - qemu-system-x86_64, python3, grub-install available on the host
#   - script must be run as root (or with sudo)

set -euo pipefail

# defaults
WORK_DIR="build/qemu-test"
ROOTFS_TGZ=""
RESERVE_PCT=10
ESP_MB=128
LPSS_MB=256
BUILD_ONLY=false
RUN_ONLY=false

# parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
    --rootfs)
        ROOTFS_TGZ="$2"
        shift 2
        ;;
    --dir)
        WORK_DIR="$2"
        shift 2
        ;;
    --reserve)
        RESERVE_PCT="$2"
        shift 2
        ;;
    --build-only)
        BUILD_ONLY=true
        shift
        ;;
    --run-only)
        RUN_ONLY=true
        shift
        ;;
    --help | -h)
        echo "Usage: $0 --rootfs <rootfs.tgz> [--dir <work_dir>] [--reserve <percent>] [--build-only | --run-only]"
        exit 0
        ;;
    *)
        echo "Unknown option: $1"
        exit 1
        ;;
    esac
done

if $RUN_ONLY; then
    [[ -z "$WORK_DIR" ]] && die "--dir is required with --run-only"
else
    [[ -z "$ROOTFS_TGZ" ]] && die "--rootfs is required for building"
    [[ ! -f "$ROOTFS_TGZ" ]] && die "rootfs tarball not found: $ROOTFS_TGZ"
fi

# absolute paths
if ! $RUN_ONLY; then
    ROOTFS_TGZ_ABS="$(cd "$(dirname "$ROOTFS_TGZ")" && pwd)/$(basename "$ROOTFS_TGZ")"
fi
WORK_DIR_ABS="$(cd "$(dirname "$WORK_DIR")" 2>/dev/null && pwd)/$(basename "$WORK_DIR")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# locate LPSS tools
if [[ -x "$PROJECT_DIR/lpss_install.py" ]]; then
    LPSS_INSTALL="$PROJECT_DIR/lpss_install.py"
    LPSS_IMPORT="$PROJECT_DIR/lpss_import.py"
    LPSS_CTL="$PROJECT_DIR/lpss_ctl.py"
elif command -v lpss_install >/dev/null 2>&1; then
    LPSS_INSTALL="lpss_install"
    LPSS_IMPORT="lpss_import"
    LPSS_CTL="lpss_ctl"
else
    die "LPSS tools not found"
fi

# OVMF firmware
find_ovmf() {
    local candidates_code=(
        /usr/share/qemu/ovmf-x86_64-4m-code.bin
        /usr/share/qemu/ovmf-x86_64-code.bin
        /usr/share/edk2-ovmf/OVMF_CODE.fd
        /usr/share/edk2/ovmf/OVMF_CODE.fd
        /usr/share/OVMF/OVMF_CODE.fd
        /usr/share/qemu-ovmf/OVMF_CODE.fd
    )
    local candidates_vars=(
        /usr/share/qemu/ovmf-x86_64-4m-vars.bin
        /usr/share/qemu/ovmf-x86_64-vars.bin
        /usr/share/edk2-ovmf/OVMF_VARS.fd
        /usr/share/edk2/ovmf/OVMF_VARS.fd
        /usr/share/OVMF/OVMF_VARS.fd
        /usr/share/qemu-ovmf/OVMF_VARS.fd
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
        die "OVMF firmware files not found"
    fi
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}
step() { echo "==> $*"; }

# checks
step "Checking host dependencies"
command -v qemu-system-x86_64 >/dev/null || die "Missing qemu-system-x86_64"
command -v python3 >/dev/null || die "Missing python3"
find_ovmf

# build phase
if ! $RUN_ONLY; then
    mkdir -p "$WORK_DIR_ABS"
    cd "$WORK_DIR_ABS" || die "Cannot enter $WORK_DIR_ABS"
    rm -f lpss.conf grub.cfg

    step "Extracting rootfs into two slots"
    rm -rf slot_a slot_b
    mkdir slot_a slot_b
    tar xzf "$ROOTFS_TGZ_ABS" -C slot_a
    tar xzf "$ROOTFS_TGZ_ABS" -C slot_b

    echo "slot-a" >slot_a/etc/hostname
    echo "slot-b" >slot_b/etc/hostname

    export PYTHONPATH="$PROJECT_DIR"
    KERNEL_A=$(python3 -c "
from lib.utils import find_kernel_initrd_in_root
k, _ = find_kernel_initrd_in_root('$PWD/slot_a')
print(k or '')
")
    INITRD_A=$(python3 -c "
from lib.utils import find_kernel_initrd_in_root
_, i = find_kernel_initrd_in_root('$PWD/slot_a')
print(i or '')
")
    KERNEL_B=$(python3 -c "
from lib.utils import find_kernel_initrd_in_root
k, _ = find_kernel_initrd_in_root('$PWD/slot_b')
print(k or '')
")
    INITRD_B=$(python3 -c "
from lib.utils import find_kernel_initrd_in_root
_, i = find_kernel_initrd_in_root('$PWD/slot_b')
print(i or '')
")

    if [[ -z "$KERNEL_A" || -z "$INITRD_A" || -z "$KERNEL_B" || -z "$INITRD_B" ]]; then
        die "Could not find kernel/initrd in rootfs /boot"
    fi

    step "Detected kernel/initrd:"
    echo " slot-a: $KERNEL_A / $INITRD_A"
    echo " slot-b: $KERNEL_B / $INITRD_B"

    # Compute partition sizes
    step "Computing partition sizes"
    SLOT_SIZE_KIB=$(du -sk slot_a | awk '{print $1}')
    SLOT_SIZE_MIB=$(((SLOT_SIZE_KIB + 1023) / 1024))
    RESERVE_MIB=$((SLOT_SIZE_MIB * RESERVE_PCT / 100 + 50))
    ROOT_PART_MIB=$((SLOT_SIZE_MIB + RESERVE_MIB))
    TOTAL_MIB=$((ESP_MB + LPSS_MB + 2 * ROOT_PART_MIB + 50))

    echo "Rootfs size: ${SLOT_SIZE_KIB} KiB (~ ${SLOT_SIZE_MIB} MiB)"
    echo "Reserve: ${RESERVE_PCT}% + 50 MiB -> ${RESERVE_MIB} MiB"
    echo "Each root partition: ${ROOT_PART_MIB} MiB"
    echo "Total disk image: ${TOTAL_MIB} MiB"

    # Create disk image
    DISK_IMG="disk.img"
    step "Creating disk image (${TOTAL_MIB} MiB)"
    rm -f "$DISK_IMG"
    dd if=/dev/zero of="$DISK_IMG" bs=1M count="$TOTAL_MIB" status=progress

    parted -s "$DISK_IMG" mklabel gpt
    parted -s "$DISK_IMG" mkpart primary fat32 1MiB $((ESP_MB + 1))MiB
    parted -s "$DISK_IMG" set 1 esp on
    parted -s "$DISK_IMG" mkpart primary ext4 $((ESP_MB + 1))MiB $((ESP_MB + LPSS_MB + 1))MiB
    parted -s "$DISK_IMG" mkpart primary ext4 $((ESP_MB + LPSS_MB + 1))MiB $((ESP_MB + LPSS_MB + ROOT_PART_MIB + 1))MiB
    parted -s "$DISK_IMG" mkpart primary ext4 $((ESP_MB + LPSS_MB + ROOT_PART_MIB + 1))MiB 100%
    parted -s "$DISK_IMG" name 3 root.a
    parted -s "$DISK_IMG" name 4 root.b

    LOOP=$(losetup --show -fP "$DISK_IMG")
    mkfs.vfat "${LOOP}p1"
    mkfs.ext4 -F -L root.a "${LOOP}p3"
    mkfs.ext4 -F -L root.b "${LOOP}p4"
    mkfs.ext4 -F "${LOOP}p2"
    losetup -d "$LOOP"

    # Mount and populate partitions
    step "Mounting partitions"
    LOOP=$(losetup --show -fP "$DISK_IMG")
    mkdir -p mnt/esp mnt/lpss mnt/root_a mnt/root_b
    mount "${LOOP}p1" mnt/esp
    mount "${LOOP}p2" mnt/lpss
    mount "${LOOP}p3" mnt/root_a
    mount "${LOOP}p4" mnt/root_b

    cleanup_build() {
        set +e
        echo "Cleaning up mounts and loop"
        umount mnt/root_a mnt/root_b mnt/lpss mnt/esp 2>/dev/null
        losetup -d "$LOOP" 2>/dev/null
        rm -rf mnt
    }
    trap cleanup_build EXIT

    step "Copying slot contents to partitions"
    cp -a slot_a/. mnt/root_a/
    cp -a slot_b/. mnt/root_b/

    # Install LPSS
    step "Installing LPSS"
    rm -f mnt/lpss/grub.cfg mnt/lpss/grub2/grub.cfg
    "$LPSS_INSTALL" --lpss-dir "$PWD/mnt/lpss" --esp-dir "$PWD/mnt/esp" \
        --grub-install-extra="--removable --no-nvram"

    # Import slots
    step "Importing slots"
    "$LPSS_IMPORT" --lpss-dir "$PWD/mnt/lpss" \
        --root "$PWD/mnt/root_a" --id slot-a --locator label:root.a \
        --linux "/$KERNEL_A" --initrd "/$INITRD_A" \
        --options "ro console=ttyS0"
    "$LPSS_IMPORT" --lpss-dir "$PWD/mnt/lpss" \
        --root "$PWD/mnt/root_b" --id slot-b --locator label:root.b \
        --linux "/$KERNEL_B" --initrd "/$INITRD_B" \
        --options "ro console=ttyS0"

    # Set slot-a as default
    step "Setting slot-a as default and regenerating grub.cfg"
    "$LPSS_CTL" --lpss-dir "$PWD/mnt/lpss" enable slot-a
    "$LPSS_CTL" --lpss-dir "$PWD/mnt/lpss" default slot-a
    "$LPSS_CTL" --lpss-dir "$PWD/mnt/lpss" apply

    # Save debugging artifacts
    if [[ -d mnt/lpss/grub2 ]]; then
        GRUB_DIR="mnt/lpss/grub2"
    else
        GRUB_DIR="mnt/lpss/grub"
    fi

    echo "Saving configs to $WORK_DIR_ABS/"
    cp mnt/lpss/lpss.conf "$WORK_DIR_ABS/lpss.conf"
    cp "$GRUB_DIR/grub.cfg" "$WORK_DIR_ABS/grub.cfg"

    if command -v grub2-script-check >/dev/null; then
        echo "Checking grub.cfg syntax..."
        grub2-script-check "$GRUB_DIR/grub.cfg" || echo "WARNING: syntax error"
    fi

    echo "=== LPSS CONFIG ==="
    cat "$WORK_DIR_ABS/lpss.conf"
    echo "=== GENERATED GRUB.CFG ==="
    cat "$WORK_DIR_ABS/grub.cfg"

    echo "Syncing filesystems..."
    sync

    cleanup_build
    trap - EXIT

    echo "Build complete. Disk image at $WORK_DIR_ABS/$DISK_IMG."
    if $BUILD_ONLY; then
        echo "--build-only specified, exiting without running QEMU."
        exit 0
    fi
fi

# run phase
cd "$WORK_DIR_ABS" || die "Cannot enter $WORK_DIR_ABS"
DISK_IMG="disk.img"
if [[ ! -f "$DISK_IMG" ]]; then
    die "Disk image not found: $DISK_IMG. Run without --run-only first."
fi

step "Preparing UEFI firmware"
cp "$OVMF_VARS" vars.fd

step "Starting QEMU (Ctrl-A X to exit)"
qemu-system-x86_64 \
    -enable-kvm \
    -machine q35 \
    -cpu host \
    -m 512 \
    -drive file="$DISK_IMG",format=raw,if=virtio \
    -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
    -drive if=pflash,format=raw,file=vars.fd \
    -nographic \
    -serial mon:stdio

echo "QEMU exited. Disk image kept at $WORK_DIR_ABS/$DISK_IMG."
echo "Configs saved as $WORK_DIR_ABS/lpss.conf and $WORK_DIR_ABS/grub.cfg"
