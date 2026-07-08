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
- quickly restore a previous system state.

LPSS uses GRUB as the bootloader backend.
It does not replace GRUB and does not create its own boot chain.

---

# Design principles

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

# Basic concepts

## Entry

An Entry is one bootable Linux system.

It describes:

- root filesystem location;
- kernel;
- initramfs;
- kernel parameters.

Example:

```

arch
opensuse
fedora

```

---

## Enabled

The Entry is available for use.

---

## Active

The Entry selected for automatic boot.

Only one Entry per role can be active.

---

## Trial

A one-time boot of an Entry.

Trial boots are handled through GRUB's `grub-reboot`.

After successful testing:

```

lpss_ctl confirm

```

makes the Entry permanent.

---

# Disk layout

```

GPT

ESP
|
+-- EFI/LPSS/
|
+-- grubx64.efi
+-- grub.cfg        (bootstrap)

LPSS partition
|
+-- lpss.conf
+-- flags/
+-- grub.cfg
+-- grubenv

root.a
root.b
root.c

```

---

# Configuration

LPSS configuration is stored in:

```

lpss.conf

````

Configuration contains only static information.
Runtime state is stored separately.

Example:

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
````

---

# Tools

## lpss_init

Creates LPSS infrastructure:

* LPSS partition;
* EFI boot entry;
* GRUB bootstrap;
* initial configuration.

---

## lpss_import

Imports an existing Linux installation:

* reads kernel/initramfs;
* extracts boot parameters;
* creates an LPSS Entry.

Supported sources:

* installed root filesystem;
* fsarchiver image;
* filesystem image.

---

## lpss_ctl

Main management utility.

Examples:

```bash
lpss_ctl list

lpss_ctl status

lpss_ctl boot opensuse

lpss_ctl activate arch

lpss_ctl confirm
```

---

## lpss_check

Diagnostic tool.

Checks:

* configuration;
* states;
* GRUB integration;
* Entry consistency.

---

# Technical design

## LPSS discovery

The EFI loader starts GRUB from the ESP.

The bootstrap `grub.cfg` contains the LPSS filesystem UUID:

```
search --fs-uuid <LPSS_UUID>
configfile /grub.cfg
```

The main LPSS `grub.cfg` is stored on the LPSS partition.

Linux receives:

```
lpss_uuid=<uuid>
lpss_entry=<entry_id>
```

and during trial boot:

```
lpss_trial=1
```

---

## Entry locator

The root filesystem is not hardcoded.

LPSS uses:

```
locator=<type>:<value>
```

Examples:

```
locator=partlabel:root.a

locator=partuuid:xxxx

locator=fsuuid:xxxx

locator=label:ROOT
```

The GRUB generator converts this into the appropriate `search` command.

---

## State storage

State is stored as files:

```
flags/

arch/
 ├── enabled
 └── active

opensuse/
 └── enabled
```

Rules:

* active Entry must be enabled;
* only one active Entry exists per role;
* disabling an active Entry is forbidden.

The trial state is stored only in GRUB `grubenv`.

---

## Boot flow

1. EFI starts GRUB.
2. GRUB finds LPSS.
3. LPSS configuration is loaded.
4. GRUB generates menu entries.

Menu:

```
LPSS

Automatic

Arch Linux

OpenSUSE
```

Automatic selection:

```
active + enabled Entry

or

first enabled Entry
```

Manual selection creates a trial boot.

After successful boot:

```
lpss_ctl confirm
```

changes the tested Entry to active.

---

# Current status

Early development.

Initial target:

* GPT systems;
* GRUB backend;
* partition role: root only;
* filesystem-based state;
* file-based configuration.

Future:

* additional roles (`home`, `data`);
* more filesystems;
* more locator types;
* improved importers.

---

LPSS keeps Linux systems simple:

**A Linux installation should be replaceable without rebuilding the machine around it.**


