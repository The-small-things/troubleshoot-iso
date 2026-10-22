#!/bin/bash
# Build the Hardware Troubleshooter ISO with Debian live-build.
#
# Needs root on Debian 13 (trixie) with live-build installed, or use:  ./build.sh --docker
# The finished image is written to dist/.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

if [[ "${1:-}" == "--docker" ]]; then
    exec docker run --rm --privileged -v "$PWD":/src -w /src debian:trixie \
        bash -c "apt-get update && apt-get install -y --no-install-recommends live-build ca-certificates cpio && ./build.sh"
fi

if [[ $EUID -ne 0 ]]; then
    echo "live-build needs root: run 'sudo ./build.sh' (or './build.sh --docker')." >&2
    exit 1
fi
command -v lb >/dev/null || { echo "Install live-build first: apt-get install live-build" >&2; exit 1; }

# Fresh working tree: live-build config + the app's Python package.
rm -rf build
mkdir -p build dist
cp -a live/. build/
pkg=build/config/includes.chroot/usr/lib/troubleshoot
mkdir -p "$pkg"
cp -a src/troubleshoot "$pkg/"
find "$pkg" -name __pycache__ -prune -exec rm -rf {} +

cd build
lb config
lb build

iso=$(ls -1 ./*.iso | head -n1)
version=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' ../src/troubleshoot/__init__.py)
out="../dist/troubleshoot-${version}-amd64.iso"
mv "$iso" "$out"
(cd ../dist && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
echo "Built $out"
