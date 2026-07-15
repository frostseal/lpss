#!/usr/bin/env python3
# @file test/smoke_test.py
"""
Smoke test for LPSS.

Creates temporary loop images, formats them, mounts them, and runs
the full LPSS cycle using the host's GRUB tools (grub-install,
grub-editenv).  Uses grub-install with --removable --no-nvram so
that BOOTX64.EFI is placed in the standard removable path.

All locators use 'label' type (e.g., label:root.test) for maximum
compatibility.
"""
import argparse
import os
import shutil
import subprocess
import sys

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Global counters for test results
pass_count = 0
fail_count = 0


def check_file(path, description):
    global pass_count, fail_count
    if os.path.exists(path):
        print(f"  [PASS] {description} ({path})")
        pass_count += 1
    else:
        print(f"  [FAIL] {description} ({path}) missing")
        fail_count += 1


def check_file_contains(path, substring, description, invert=False):
    global pass_count, fail_count
    try:
        with open(path) as f:
            content = f.read()
        found = substring in content
        if (found and not invert) or (not found and invert):
            print(f"  [PASS] {description} ({path})")
            pass_count += 1
        else:
            if invert:
                msg = f"'{substring}' unexpectedly found in {path}"
            else:
                msg = f"'{substring}' not found in {path}"
            print(f"  [FAIL] {description}: {msg}")
            fail_count += 1
    except FileNotFoundError:
        print(f"  [FAIL] {description}: file {path} not found")
        fail_count += 1


def check_flag_exists(flags_dir, entry, flag):
    path = os.path.join(flags_dir, entry, flag)
    check_file(path, f"flag {entry}/{flag}")


def run(cmd, **kwargs):
    print(f"  Running: {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)


def find_grub_tool(name):
    """Locate grub-<name> or grub2-<name>."""
    for candidate in [f'grub-{name}', f'grub2-{name}']:
        path = shutil.which(candidate)
        if path:
            return path
    return None


def main():
    global pass_count, fail_count
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', required=True, help='Working directory')
    args = parser.parse_args()

    base = os.path.abspath(args.dir)
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(base, exist_ok=True)

    if not find_grub_tool('install'):
        print("SKIP: grub-install (or grub2-install) not found.")
        sys.exit(0)

    lpss_img = os.path.join(base, 'lpss.img')
    esp_img = os.path.join(base, 'esp.img')
    run(['dd', 'if=/dev/zero', f'of={lpss_img}', 'bs=1M', 'count=256'],
        check=True)
    run(['dd', 'if=/dev/zero', f'of={esp_img}', 'bs=1M', 'count=64'],
        check=True)
    run(['mkfs.ext4', '-F', lpss_img], check=True)
    run(['mkfs.vfat', esp_img], check=True)

    lpss_mnt = os.path.join(base, 'lpss')
    esp_mnt = os.path.join(base, 'esp')
    os.makedirs(lpss_mnt, exist_ok=True)
    os.makedirs(esp_mnt, exist_ok=True)
    run(['mount', '-o', 'loop', lpss_img, lpss_mnt], check=True)
    run(['mount', '-o', 'loop', esp_img, esp_mnt], check=True)

    try:
        lpss_install = os.path.join(PROJECT_DIR, 'lpss_install.py')
        lpss_import = os.path.join(PROJECT_DIR, 'lpss_import.py')
        lpss_ctl = os.path.join(PROJECT_DIR, 'lpss_ctl.py')

        for tool in (lpss_install, lpss_import, lpss_ctl):
            if not os.path.exists(tool):
                print(f"Error: LPSS tool not found: {tool}", file=sys.stderr)
                sys.exit(1)

        env = os.environ.copy()

        print("=== 1. lpss_install ===")
        fake_uuid = 'fake-uuid-1234-abcd'
        run([lpss_install,
             '--lpss-dir', lpss_mnt,
             '--esp-dir', esp_mnt,
             '--lpss-uuid', fake_uuid,
             '--grub-install-extra=--removable --no-nvram'],
            env=env, check=True)

        check_file(os.path.join(lpss_mnt, 'lpss.conf'), 'lpss.conf')
        check_file_contains(os.path.join(lpss_mnt, 'lpss.conf'), fake_uuid,
                            'UUID in lpss.conf')
        check_file(os.path.join(lpss_mnt, 'flags'), 'flags directory')

        grub_dir = os.path.join(lpss_mnt, 'grub2')
        if not os.path.isdir(grub_dir):
            grub_dir = os.path.join(lpss_mnt, 'grub')
        check_file(grub_dir, 'GRUB directory')
        check_file(os.path.join(grub_dir, 'x86_64-efi'), 'GRUB modules dir')
        check_file(os.path.join(esp_mnt, 'EFI', 'BOOT', 'BOOTX64.EFI'),
                   'LPSS BOOTX64.EFI')
        check_file(os.path.join(grub_dir, 'grub.cfg'), 'LPSS themed grub.cfg')

        # Rootfs with kernel and initrd for testlinux
        rootfs_dir = os.path.join(base, 'rootfs')
        os.makedirs(rootfs_dir + '/boot', exist_ok=True)
        kernel_path = os.path.join(rootfs_dir, 'boot/vmlinuz-5.10.0')
        initrd_path = os.path.join(rootfs_dir, 'boot/initrd.img-5.10.0')
        open(kernel_path, 'w').close()
        open(initrd_path, 'w').close()

        print("\n=== 2. lpss_import (with initrd) ===")
        run([lpss_import,
             '--lpss-dir', lpss_mnt,
             '--root', rootfs_dir,
             '--id', 'testlinux',
             '--locator', 'label:root.test'],
            env=env, check=True)

        check_file_contains(os.path.join(lpss_mnt, 'lpss.conf'),
                            '[entry.testlinux]', 'entry added')
        check_file_contains(os.path.join(grub_dir, 'grub.cfg'),
                            'entry_testlinux', 'grub.cfg updated')

        print("\n=== 3. lpss_ctl enable + default + apply ===")
        run([lpss_ctl, '--lpss-dir', lpss_mnt, 'enable', 'testlinux'],
            env=env, check=True)
        run([lpss_ctl, '--lpss-dir', lpss_mnt, 'default', 'testlinux'],
            env=env, check=True)
        run([lpss_ctl, '--lpss-dir', lpss_mnt, 'apply'],
            env=env, check=True)

        flags_dir = os.path.join(lpss_mnt, 'flags')
        check_flag_exists(flags_dir, 'testlinux', 'enabled')
        check_flag_exists(flags_dir, 'testlinux', 'default')

        # ---- Import entry without initrd ---------------------------------
        print("\n=== 3b. lpss_import (without initrd) ===")
        rootfs_nointrd_dir = os.path.join(base, 'rootfs_nointrd')
        os.makedirs(rootfs_nointrd_dir + '/boot', exist_ok=True)
        kernel_nointrd_path = os.path.join(rootfs_nointrd_dir,
                                           'boot/vmlinuz-5.10.0')
        open(kernel_nointrd_path, 'w').close()
        run([lpss_import,
             '--lpss-dir', lpss_mnt,
             '--root', rootfs_nointrd_dir,
             '--id', 'testnointrd',
             '--locator', 'label:root.test2'],
            env=env, check=True)

        check_file_contains(os.path.join(lpss_mnt, 'lpss.conf'),
                            '[entry.testnointrd]', 'entry testnointrd added')
        # Verify no initrd= in the testnointrd section specifically
        with open(os.path.join(lpss_mnt, 'lpss.conf')) as f:
            full_conf = f.read()
        start = full_conf.find('[entry.testnointrd]')
        if start == -1:
            print("  [FAIL] section [entry.testnointrd] not found")
            fail_count += 1
        else:
            end = full_conf.find('[', start + 1)
            if end == -1:
                end = len(full_conf)
            section_text = full_conf[start:end]
            if 'initrd=' in section_text:
                print("  [FAIL] initrd absent for testnointrd: "
                      "'initrd=' found in section")
                fail_count += 1
            else:
                print("  [PASS] initrd absent for testnointrd")
                pass_count += 1
        check_file_contains(os.path.join(grub_dir, 'grub.cfg'),
                            'entry_testnointrd',
                            'grub.cfg contains entry_testnointrd')

        # ---- Trial boot and confirm --------------------------------------
        editenv = find_grub_tool('editenv')
        if editenv:
            print("\n=== 4. lpss_ctl trial (trial boot) ===")
            run([lpss_ctl, '--lpss-dir', lpss_mnt, 'trial', 'testlinux'],
                env=env, check=True)
            check_file_contains(os.path.join(grub_dir, 'grubenv'),
                                'next_entry=entry_testlinux',
                                'grubenv trial set')

            print("\n=== 5. lpss_ctl confirm ===")
            fake_cmdline = os.path.join(base, 'fake_cmdline')
            with open(fake_cmdline, 'w') as f:
                f.write('lpss_entry=testlinux lpss_trial=1 quiet')
            env['LPSS_CMDLINE_FILE'] = fake_cmdline
            run([lpss_ctl, '--lpss-dir', lpss_mnt, 'confirm'],
                env=env, check=True)
            check_flag_exists(flags_dir, 'testlinux', 'default')
            print("  [INFO] confirm with trial succeeded.")

            with open(fake_cmdline, 'w') as f:
                f.write('lpss_entry=testlinux quiet')
            result = run([lpss_ctl, '--lpss-dir', lpss_mnt, 'confirm'],
                         env=env, capture_output=True, text=True)
            if result.returncode != 0 and 'not a trial' in result.stderr:
                print("  [PASS] confirm missing trial flag correctly rejected")
                pass_count += 1
            else:
                print("  [FAIL] confirm should have rejected missing trial flag")
                fail_count += 1
        else:
            print("\n=== Trial boot tests skipped (no grub-editenv) ===")

    finally:
        run(['umount', lpss_mnt], check=False)
        run(['umount', esp_mnt], check=False)
        if os.path.exists(lpss_img):
            os.remove(lpss_img)
        if os.path.exists(esp_img):
            os.remove(esp_img)

    print("\n=== Smoke test summary ===")
    total = pass_count + fail_count
    print(f"Total checks: {total}")
    print(f"  PASS: {pass_count}")
    print(f"  FAIL: {fail_count}")
    if fail_count > 0:
        print("FAILED (errors encountered)")
        sys.exit(1)
    else:
        print("SUCCESS")
        sys.exit(0)


if __name__ == '__main__':
    main()