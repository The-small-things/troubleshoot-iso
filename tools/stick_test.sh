#!/bin/sh
# Make a USB stick image from the ISO (as Etcher/dd would, on a 4 GB stick) and let the app add its
# REPORTS partition and save a file there, using the same code as on a real stick.
#
#     sudo tools/stick_test.sh dist/troubleshoot-*.iso stick.img
#
# Then boot it (tools/boot_test.py --usb-image stick.img) to check the stick still boots.
set -eu
iso=$1
img=$2
here=$(cd "$(dirname "$0")/.." && pwd)
cp "$iso" "$img"
truncate -s 4G "$img"
loop=$(losetup -fP --show "$img")
trap 'losetup -d "$loop"' EXIT
PYTHONPATH="$here/src" python3 - "$(basename "$loop")" <<'PY'
import sys
from troubleshoot import bootstick

disk = sys.argv[1]
part = bootstick.create_partition(disk)
print("created", part)
print("wrote", bootstick._write_partition(part, "vfat", {"hardware-report-test.txt": "saved by stick_test.sh\n"}))
PY
sfdisk -d "$loop"
blkid "$loop" "${loop}p3"
cmp -n "$(( $(stat -c %s "$iso") - 512 ))" -i 512 "$iso" "$img" && echo "ISO contents after the partition table are unchanged"
