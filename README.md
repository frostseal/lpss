# LPSS — Linux Partition Slot System

LPSS is a lightweight boot management layer for Linux systems that allows
multiple independent Linux installations to coexist on one machine.

The goal is simple: treat Linux root filesystems as replaceable system
images that can be installed, backed up, restored, tested, and switched
without rebuilding the whole boot infrastructure.

Example:


```
          LPSS

    +-------------+
    |             |
 root.a        root.b
 stable       testing
```



LPSS is useful when you want to:

- test different Linux distributions;
- experiment with kernels, drivers, or system changes;
- keep a known-good system while modifying another one;
- quickly restore a previous system state (instead of a full backup, just copy the rootfs using `tar` or `fsarchiver`).

LPSS uses GRUB as the bootloader backend.
It does not replace GRUB and does not create its own boot chain.

---

## Design principles

- **LPSS is not a bootloader.**
  GRUB loads kernels and initrds.

- **LPSS is not a partition manager.**
  Disk layout and filesystem creation are outside its scope.

- **LPSS is not a backup system.**
  Backup tools such as `fsarchiver` can be used together with LPSS.

- **LPSS is a boot management layer.**
  It manages Linux installations and their boot states.

A Linux installation managed by LPSS should not modify:

- EFI boot configuration;
- LPSS `grub.cfg`;
- LPSS `grubenv`.

A managed Linux system provides only:

- root filesystem;
- kernel;
- initramfs;
- additional kernel options.

---

## Basic concepts

### Entry
A single bootable Linux system described by a human-readable ID
(`arch`, `opensuse`, …), a root filesystem locator, kernel/initrd
paths, and extra kernel options.

### Enabled
The entry is available for manual or automatic boot.

### Active
The default entry for a role (only one per role).  `active` implies
`enabled`.

### Trial
A one-shot boot performed via GRUB’s `grub-reboot`.  The kernel
command line receives `lpss_trial=1`.  After a successful test,
`lpss_ctl confirm` makes the trial entry permanent.

---

## Disk layout

```
GPT
 ESP
  └─ EFI/BOOT/
       └─ BOOTX64.EFI          (LPSS loader, removable media path)
 LPSS partition (ext4)
  ├─ lpss.conf
  ├─ flags/
  ├─ grub/                     (or grub2, depending on distribution)
  │    ├─ grub.cfg             (main menu)
  │    └─ x86_64-efi/          (GRUB runtime modules)
  └─ grubenv
 root.a
 root.b
 …
```

---

## Quick start

### 1. Prepare the disk manually
Partition the disk and format the filesystems with standard tools
(`parted`, `mkfs.vfat`, `mkfs.ext4`, …).

```bash
# example (adjust to your setup)
parted /dev/sda mklabel gpt
parted /dev/sda mkpart ESP fat32 1MiB 512MiB
parted /dev/sda set 1 esp on
parted /dev/sda mkpart LPSS ext4 512MiB 2.5GiB
parted /dev/sda mkpart root.a ext4 2.5GiB 100%

mkfs.vfat /dev/sda1
mkfs.ext4 /dev/sda2
mkfs.ext4 /dev/sda3
```

### 2. Mount everything
```bash
mount /dev/sda2 /mnt/lpss      # LPSS partition
mount /dev/sda1 /boot/efi      # EFI System Partition
```

### 3. Install LPSS infrastructure
```bash
lpss_install --lpss-dir /mnt/lpss --esp-dir /boot/efi
```

LPSS runs the distribution’s `grub-install` (or `grub2-install`)
to set up the bootloader, then overwrites the generated `grub.cfg`
with its own themed menu.  To create a removable EFI executable that
does not modify NVRAM, pass extra flags:

```bash
lpss_install --lpss-dir /mnt/lpss --esp-dir /boot/efi \
    --grub-install-extra "--removable --no-nvram"
```

LPSS will create the `lpss.conf` configuration file and the `flags/`
directory on the LPSS partition.

### 4. Import a Linux system
Mount the root filesystem of your existing installation:
```bash
mount /dev/sda3 /mnt/rootfs
```

Register it as an LPSS entry:
```bash
lpss_import --lpss-dir /mnt/lpss --root /mnt/rootfs \
    --id arch --locator label:root.a
```

The tool auto‑detects kernel and initrd.  Omit `--linux` or `--initrd`
to see the detected values.  Supported locator types include
`partlabel`, `label`, `fsuuid`, and `partuuid` (the backend is
extensible).

### 5. Enable, activate, and apply
```bash
lpss_ctl --lpss-dir /mnt/lpss enable arch
lpss_ctl --lpss-dir /mnt/lpss activate arch
lpss_ctl --lpss-dir /mnt/lpss apply        # regenerate grub.cfg
```

Now `arch` will boot automatically.

### 6. Trial‑boot another entry
```bash
lpss_ctl --lpss-dir /mnt/lpss boot opensuse
reboot
```

The system starts `opensuse` once with `lpss_trial=1` on the kernel
command line.  If everything works, make it the permanent default:

```bash
lpss_ctl --lpss-dir /mnt/lpss confirm
```

`confirm` activates the current trial entry for its role.

---

## Configuration (`lpss.conf`)

Located at the root of the LPSS partition.  Contains only static
information; runtime state lives in `flags/` and `grubenv`.

```ini
[lpss]
# UUID format: 8-4-4-4-12 hexadecimal characters
id=aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee
version=1

[entry.arch]
id=arch
role=root
locator=label:root.a
linux=/boot/vmlinuz-linux
initrd=/boot/initramfs-linux.img
options=quiet splash

[entry.opensuse]
id=opensuse
role=root
locator=label:root.b
linux=/boot/vmlinuz
initrd=/boot/initrd
options=splash=silent
```

The `locator` field tells the GRUB generator how to find the root
filesystem.  Supported types:

- `label:<filesystem label>`
- `partlabel:<GPT PARTLABEL>`
- `fsuuid:<filesystem UUID>`
- `partuuid:<GPT PARTUUID>`

---

## Tools

All tools accept `--lpss-dir` (preferred) or the environment variable
`LPSS_MOUNT`.  If both are omitted, `/mnt/lpss` is used.

| Tool           | Purpose |
|----------------|---------|
| `lpss_install` | Install LPSS infrastructure onto an already‑prepared partition. |
| `lpss_import`  | Register an existing Linux installation as an LPSS entry. |
| `lpss_ctl`     | Manage entries —  `enable`, `disable`, `activate`, ... |
| `lpss_check`   | (planned) Diagnose configuration consistency. |

`lpss_ctl current` reads the running entry from `/proc/cmdline`.
For testing, you can override the command line with the environment
variable `LPSS_CMDLINE_FILE`.

---

## Technical design

### LPSS discovery
The EFI executable placed by `grub-install` (usually at
`EFI/BOOT/BOOTX64.EFI` in removable mode) loads its configuration
from the LPSS partition.  The main `grub.cfg` (generated by LPSS)
begins with a `search --fs-uuid` command that sets `$root` to the
LPSS partition.  The kernel receives:

```
lpss_uuid=<LPSS_UUID> lpss_entry=<entry_id>
```

and, during a trial boot, additionally `lpss_trial=1`.

### Entry locator abstraction
The root filesystem is not hard‑coded into the menu.  The GRUB
generator translates a `locator` into the appropriate `search` command,
making the menu independent of the underlying naming scheme.  The
generator also automatically derives a matching `root=` kernel
parameter from the locator.

### State storage
Runtime state is kept as empty files under `flags/<entry>/`:

```
flags/
 arch/
  ├── enabled
  └── active
 opensuse/
  └── enabled
```

Invariants (enforced by `lpss_ctl`):

- an active entry must also be enabled,
- only one entry per role may be active,
- disabling an active entry is rejected.

Trial state is stored **only** in GRUB’s `grubenv` (the `next_entry`
variable).

### Boot flow
1. EFI starts GRUB (installed by the distribution’s `grub-install`
   at the standard removable path).
2. GRUB loads the main `grub.cfg` from the LPSS partition.
3. The themed menu shows an `Automatic` entry and all registered
   Linux slots.
4. `Automatic` boots the active+enabled entry (or the first enabled
   if none is active).
5. Manual selection triggers a one‑shot trial boot.
6. After a successful trial, `lpss_ctl confirm` promotes the entry
   to active.

---

## Current status

Early development — the core workflow is functional on GPT + UEFI
systems with an ext4 LPSS partition.  What is implemented:

- `lpss_install`, `lpss_import`, `lpss_ctl` with all listed commands,
- `partlabel`, `label`, `fsuuid` locators,
- `root` role only,
- `smoke_test.py` for offline validation.

Planned:

- additional roles (`home`, `data`, …),
- `lpss_check` diagnostic tool,
- improved importers (fsarchiver, raw images, …).

---

## Development & testing

A smoke test that runs the full cycle within one test folder is located
at `test/smoke_test.py`.  It creates temporary loop images, installs
LPSS using the host’s `grub-install`, and exercises every LPSS tool.
The test requires `grub-install` (or `grub2-install`) to be available.

```bash
# Run from the project root
sudo ./test/smoke_test.py --dir /tmp/lpss-smoke
```

The test prints `[PASS]` / `[FAIL]` for each check.

---

LPSS keeps Linux systems simple:

**A Linux installation should be replaceable like any other component
of the system.**

