#!/usr/bin/env python3
"""Boot the ISO in QEMU (UEFI and BIOS) and take screenshots along the way.

    python3 tools/boot_test.py dist/troubleshoot-*.iso screenshots/ [--print-base64]

Screenshots show the boot menu, the boot splash and the app's welcome screen. With
--print-base64 they're also written to stdout between markers (handy when the CI artifact
can't be downloaded). Uses KVM when /dev/kvm is accessible, plain emulation otherwise.
"""

from __future__ import annotations

import argparse
import base64
import glob
import os
import shutil
import socket
import subprocess
import tempfile
import time

OVMF_CODE = ["/usr/share/OVMF/OVMF_CODE_4M.fd", "/usr/share/OVMF/OVMF_CODE.fd"]
OVMF_VARS = ["/usr/share/OVMF/OVMF_VARS_4M.fd", "/usr/share/OVMF/OVMF_VARS.fd"]


def first(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    raise SystemExit(f"none of {paths} found (install ovmf)")


def boot(iso: str, out: str, mode: str, shots: list[int]) -> list[str]:
    tmp = tempfile.mkdtemp()
    sock = os.path.join(tmp, "monitor.sock")
    cmd = ["qemu-system-x86_64", "-m", "3072", "-smp", "2", "-vga", "std", "-display", "none",
           "-cdrom", iso, "-boot", "d", "-monitor", f"unix:{sock},server,nowait",
           "-serial", f"file:{os.path.join(out, mode + '-serial.log')}"]
    kvm = os.access("/dev/kvm", os.R_OK | os.W_OK)
    if kvm:
        cmd += ["-enable-kvm", "-cpu", "host"]
    if mode == "uefi":
        vars_copy = os.path.join(tmp, "vars.fd")
        shutil.copy(first(OVMF_VARS), vars_copy)
        cmd += ["-drive", f"if=pflash,format=raw,readonly=on,file={first(OVMF_CODE)}",
                "-drive", f"if=pflash,format=raw,file={vars_copy}"]
    scale = 1 if kvm else 4  # emulation is much slower
    print(f"[{mode}] starting QEMU ({'KVM' if kvm else 'emulation'})", flush=True)
    proc = subprocess.Popen(cmd)
    start = time.monotonic()
    taken = []
    try:
        for i in range(50):
            if os.path.exists(sock):
                break
            time.sleep(0.1)
        mon = socket.socket(socket.AF_UNIX)
        mon.connect(sock)
        for t in shots:
            wait = start + t * scale - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            if proc.poll() is not None:
                print(f"[{mode}] QEMU exited early ({proc.returncode})")
                break
            path = os.path.join(out, f"{mode}-{t:03d}s.png")
            mon.sendall(f"screendump {path} -f png\n".encode())
            time.sleep(1.0)
            if os.path.exists(path):
                taken.append(path)
                print(f"[{mode}] {path}", flush=True)
    finally:
        proc.kill()
        proc.wait()
    return taken


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("iso")
    ap.add_argument("out")
    ap.add_argument("--print-base64", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    shots = boot(a.iso, a.out, "uefi", [3, 6, 12, 20, 30, 45, 60, 80, 100, 130])
    shots += boot(a.iso, a.out, "bios", [3, 30, 60, 90])
    if a.print_base64:
        for p in shots:
            data = base64.b64encode(open(p, "rb").read()).decode()
            print(f"=====PNG {os.path.basename(p)} {len(data)}=====")
            for i in range(0, len(data), 4000):
                print(data[i:i + 4000])
            print("=====END=====")
    print(f"{len(shots)} screenshots in {a.out}")


if __name__ == "__main__":
    main()
