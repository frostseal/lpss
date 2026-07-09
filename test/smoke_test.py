#!/usr/bin/env python3
# @file test/smoke_test.py
"""
Smoke test for LPSS.

Runs a full cycle in an isolated directory (no real devices needed).
Creates a mock grub-install, sets up minimal rootfs, and exercises
lpss_install, lpss_import, lpss_ctl.

Usage:
  sudo ./test/smoke_test.py --dir /tmp/lpss-test
"""
import argparse
import os
import shutil
import subprocess
import sys
import textwrap

# Determine project root relative to this test file
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def check_file(path, description):
    if os.path.exists(path):
        print(f"  [PASS] {description} ({path})")
    else:
        print(f"  [FAIL] {description} ({path}) missing")

def check_file_contains(path, substring, description):
    try:
        with open(path) as f:
            content = f.read()
        if substring in content:
            print(f"  [PASS] {description} ({path})")
        else:
            print(f"  [FAIL] {description}: '{substring}' not found in {path}")
    except FileNotFoundError:
        print(f"  [FAIL] {description}: file {path} not found")

def check_flag_exists(flags_dir, entry, flag):
    path = os.path.join(flags_dir, entry, flag)
    check_file(path, f"flag {entry}/{flag}")

def run(cmd, **kwargs):
    print(f"  Running: {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', required=True, help='Working directory for the test')
    args = parser.parse_args()

    base = os.path.abspath(args.dir)
    lpss_dir = os.path.join(base, 'lpss')
    esp_dir = os.path.join(base, 'esp')
    rootfs_dir = os.path.join(base, 'rootfs')
    bin_dir = os.path.join(base, 'bin')

    # Clean up any previous run
    for sub in ['lpss', 'esp', 'rootfs', 'bin']:
        path = os.path.join(base, sub)
        if os.path.exists(path):
            shutil.rmtree(path)

    os.makedirs(lpss_dir, exist_ok=True)
    os.makedirs(esp_dir, exist_ok=True)
    os.makedirs(rootfs_dir + '/boot', exist_ok=True)
    os.makedirs(bin_dir, exist_ok=True)

    # Absolute paths to LPSS tools
    lpss_install = os.path.join(PROJECT_DIR, 'lpss_install.py')
    lpss_import = os.path.join(PROJECT_DIR, 'lpss_import.py')
    lpss_ctl = os.path.join(PROJECT_DIR, 'lpss_ctl.py')

    for tool in (lpss_install, lpss_import, lpss_ctl):
        if not os.path.exists(tool):
            print(f"Error: LPSS tool not found: {tool}", file=sys.stderr)
            sys.exit(1)

    # Check for real grub-editenv
    real_editenv = None
    for candidate in ['grub2-editenv', 'grub-editenv']:
        if shutil.which(candidate):
            real_editenv = candidate
            break
    if not real_editenv:
        print("Warning: grub-editenv not found, trial boot tests will be skipped.")

    # Mock grub-install: creates stub .efi and grubenv
    grub_install_script = textwrap.dedent(f"""\
        #!/bin/bash
        set -e
        boot_dir=""
        efi_dir=""
        bootloader_id=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --boot-directory)
                    boot_dir="$2"
                    shift 2
                    ;;
                --efi-directory)
                    efi_dir="$2"
                    shift 2
                    ;;
                --bootloader-id)
                    bootloader_id="$2"
                    shift 2
                    ;;
                *)
                    shift
                    ;;
            esac
        done
        mkdir -p "$efi_dir/EFI/$bootloader_id"
        touch "$efi_dir/EFI/$bootloader_id/grubx64.efi"
        mkdir -p "$boot_dir/grub/x86_64-efi"
        if command -v {real_editenv or 'grub2-editenv'} &>/dev/null; then
            {real_editenv or 'grub2-editenv'} "$boot_dir/grubenv" create
        else
            touch "$boot_dir/grubenv"
        fi
        exit 0
    """)
    grub_install_path = os.path.join(bin_dir, 'grub-install')
    with open(grub_install_path, 'w') as f:
        f.write(grub_install_script)
    os.chmod(grub_install_path, 0o755)

    grub2_install_path = os.path.join(bin_dir, 'grub2-install')
    if not os.path.exists(grub2_install_path):
        os.symlink(grub_install_path, grub2_install_path)

    # Environment with mock in PATH
    env = os.environ.copy()
    env['PATH'] = bin_dir + ':' + env.get('PATH', '/usr/bin:/bin')

    # 1. Install LPSS
    print("=== 1. lpss_install ===")
    fake_uuid = 'fake-uuid-1234-abcd'
    run([lpss_install,
         '--lpss-dir', lpss_dir,
         '--esp-dir', esp_dir,
         '--lpss-uuid', fake_uuid,
         '--bootloader-id', 'LPSS',
         '--grub-install-extra=--no-nvram'],
        env=env, check=True)

    check_file(os.path.join(lpss_dir, 'lpss.conf'), 'lpss.conf')
    check_file_contains(os.path.join(lpss_dir, 'lpss.conf'), fake_uuid, 'UUID in lpss.conf')
    check_file(os.path.join(lpss_dir, 'flags'), 'flags directory')
    check_file(os.path.join(lpss_dir, 'grub.cfg'), 'grub.cfg (main)')
    check_file(os.path.join(lpss_dir, 'grubenv'), 'grubenv')
    check_file(os.path.join(esp_dir, 'EFI/LPSS/grubx64.efi'), 'grubx64.efi')
    check_file_contains(os.path.join(esp_dir, 'EFI/LPSS/grub.cfg'), 'search --fs-uuid', 'ESP bootstrap config')

    # Prepare fake rootfs
    kernel_path = os.path.join(rootfs_dir, 'boot/vmlinuz-5.10.0')
    initrd_path = os.path.join(rootfs_dir, 'boot/initrd.img-5.10.0')
    open(kernel_path, 'w').close()
    open(initrd_path, 'w').close()

    # 2. Import entry
    print("\n=== 2. lpss_import ===")
    run([lpss_import,
         '--lpss-dir', lpss_dir,
         '--root', rootfs_dir,
         '--id', 'testlinux',
         '--locator', 'partlabel:root.test'],
        env=env, check=True)

    check_file_contains(os.path.join(lpss_dir, 'lpss.conf'), '[entry.testlinux]', 'entry added')
    check_file_contains(os.path.join(lpss_dir, 'grub.cfg'), 'menuentry "testlinux"', 'grub.cfg updated')

    # 3. Enable, activate, apply
    print("\n=== 3. lpss_ctl enable + activate + apply ===")
    run([lpss_ctl, '--lpss-dir', lpss_dir, 'enable', 'testlinux'], env=env, check=True)
    run([lpss_ctl, '--lpss-dir', lpss_dir, 'activate', 'testlinux'], env=env, check=True)
    run([lpss_ctl, '--lpss-dir', lpss_dir, 'apply'], env=env, check=True)

    flags_dir = os.path.join(lpss_dir, 'flags')
    check_flag_exists(flags_dir, 'testlinux', 'enabled')
    check_flag_exists(flags_dir, 'testlinux', 'active')

    # 4. Trial boot
    if real_editenv:
        print("\n=== 4. lpss_ctl boot (trial) ===")
        run([lpss_ctl, '--lpss-dir', lpss_dir, 'boot', 'testlinux'], env=env, check=True)
        check_file_contains(os.path.join(lpss_dir, 'grubenv'), 'next_entry=entry_testlinux', 'grubenv trial set')

        print("\n=== 5. lpss_ctl confirm ===")
        fake_cmdline = os.path.join(base, 'fake_cmdline')
        with open(fake_cmdline, 'w') as f:
            f.write('lpss_entry=testlinux lpss_trial=1 quiet')
        env['LPSS_CMDLINE_FILE'] = fake_cmdline
        run([lpss_ctl, '--lpss-dir', lpss_dir, 'confirm'], env=env, check=True)
        check_flag_exists(flags_dir, 'testlinux', 'active')
        print("  [INFO] confirm with trial succeeded.")

        # Negative test: missing trial flag
        with open(fake_cmdline, 'w') as f:
            f.write('lpss_entry=testlinux quiet')
        result = run([lpss_ctl, '--lpss-dir', lpss_dir, 'confirm'],
                     env=env, capture_output=True, text=True)
        if result.returncode != 0 and 'not a trial' in result.stderr:
            print("  [PASS] confirm with missing trial flag correctly rejected")
        else:
            print("  [FAIL] confirm should have rejected missing trial flag")
    else:
        print("\n=== Trial boot tests skipped (no grub-editenv) ===")

    print("\n=== Smoke test summary ===")
    print("Check the output above for PASS/FAIL lines.")


if __name__ == '__main__':
    main()