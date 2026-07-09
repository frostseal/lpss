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
- quickly restore a previous system state. Instead of full backup you just copy rootfs using tar or fsarchiver).

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
  └─ EFI/LPSS/
       ├─ grubx64.efi
       └─ grub.cfg          (bootstrap)
 LPSS partition (ext4)
  ├─ lpss.conf
  ├─ flags/
  ├─ grub.cfg               (main menu)
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

If you need extra `grub-install` flags (e.g. `--removable`,
`--no-nvram`), pass them with `--grub-install-extra`:

```bash
lpss_install --lpss-dir /mnt/lpss --esp-dir /boot/efi \
    --grub-install-extra "--removable --no-nvram"
```

### 4. Import a Linux system
Mount the root filesystem of your existing installation:
```bash
mount /dev/sda3 /mnt/rootfs
```

Register it as an LPSS entry:
```bash
lpss_import --lpss-dir /mnt/lpss --root /mnt/rootfs \
    --id arch --locator partlabel:root.a
```

The tool auto‑detects kernel and initrd.  Omit `--locator` to see
a list of possible values and choose interactively.

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
id=550e8400-e29b-41d4-a716-446655440000
version=1

[entry.arch]
id=arch
role=root
locator=partlabel:root.a
linux=/boot/vmlinuz-linux
initrd=/boot/initramfs-linux.img
options=quiet splash

[entry.opensuse]
id=opensuse
role=root
locator=partlabel:root.b
linux=/boot/vmlinuz
initrd=/boot/initrd
options=splash=silent
```

The `locator` field tells the GRUB generator how to find the root
filesystem.  Supported types (the backend is extensible):

- `partlabel:<GPT PARTLABEL>`
- `partuuid:<GPT PARTUUID>`
- `fsuuid:<filesystem UUID>`
- `label:<filesystem label>`

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
The bootstrap `grub.cfg` in the ESP contains the LPSS filesystem UUID:

```
search --fs-uuid --set=root <LPSS_UUID>
set prefix=($root)/grub
configfile ($root)/grub.cfg
```

GRUB loads the main `grub.cfg` from the LPSS partition.  The kernel
receives:

```
lpss_uuid=<LPSS_UUID> lpss_entry=<entry_id>
```

and, during a trial boot, additionally `lpss_trial=1`.

### Entry locator abstraction
The root filesystem is not hard‑coded into the menu.  The GRUB
generator translates a `locator` into the appropriate `search` command,
making the menu independent of the underlying naming scheme.

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
1. EFI starts GRUB.
2. GRUB reads the bootstrap config, locates the LPSS partition.
3. The main `grub.cfg` builds a menu from all registered entries.
4. The `Automatic` menu item boots the active+enabled entry (or
   the first enabled if none is active).
5. Manual selection triggers a trial boot (one‑shot).
6. After a successful trial, `lpss_ctl confirm` promotes the entry
   to active.

---

## Current status

Early development — the core workflow is functional on GPT + UEFI
systems with an ext4 LPSS partition.  What is implemented:

- `lpss_install`, `lpss_import`, `lpss_ctl` with all listed commands,
- `partlabel` locator,
- `root` role only,
- `smoke_test.py` for offline validation.

Planned:

- additional roles (`home`, `data`, …),
- more locator backends,
- `lpss_check` diagnostic tool,
- improved importers (fsarchiver, raw images, …).

---

## Development & testing

A smoke test that runs the full cycle within one test folder is located
at `test/smoke_test.py`.  It creates mock GRUB tools and a fake rootfs,
then exercises every LPSS tool.

```bash
# Run from the project root
sudo ./test/smoke_test.py --dir /tmp/lpss-smoke
```

The test prints `[PASS]` / `[FAIL]` for each check.  It requires
`sudo` only to allow the mock scripts to work with file permissions;
no real devices are touched.

---

LPSS keeps Linux systems simple:

**A Linux installation should be replaceable without rebuilding the machine around it.**


