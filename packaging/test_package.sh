#!/bin/sh
# Installs a CloutFox package in a clean container and checks that it starts:
# every bundled ELF file finds its libraries, and the app opens its panel and API.
#
#   podman run --rm -v "$PWD:/src:ro" debian:12 sh /src/packaging/test_package.sh /src/dist/cloutfox_3.0.0_amd64.deb
#   (for the tar.gz, pass the Arch dependency list as $2)
set -eu
pkg="$1"

case "$pkg" in
*.deb)
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$pkg" curl >/dev/null
    ;;
*.rpm)
    if command -v dnf >/dev/null; then
        dnf install -y -q "$pkg" curl util-linux findutils shadow-utils
    else
        zypper --non-interactive --no-gpg-checks install "$pkg" curl findutils shadow util-linux
    fi
    ;;
*.tar.gz)
    pacman -Sy --noconfirm --needed curl $2 >/dev/null
    mkdir -p /opt/cloutfox
    tar -xzf "$pkg" -C /opt/cloutfox --strip-components=1
    ln -sf /opt/cloutfox/cloutfox /usr/bin/cloutfox
    ;;
*)
    echo "unknown package: $pkg" >&2
    exit 2
    ;;
esac

echo "--- libraries"
missing=$(find /opt/cloutfox -type f \( -name '*.so' -o -name '*.so.*' -o -perm -u+x \) \
    -exec sh -c 'ldd "$1" 2>/dev/null | grep "not found" | sed "s|^|$1: |"' _ {} \;)
if [ -n "$missing" ]; then
    echo "$missing"
    exit 1
fi
echo "all found"

echo "--- start"
id tester >/dev/null 2>&1 || useradd -m tester
runuser -u tester -- env QT_QPA_PLATFORM=offscreen QTWEBENGINE_DISABLE_SANDBOX=1 \
    CLOUTFOX_HOME=/tmp/cloutfox-test timeout 120 cloutfox >/tmp/cloutfox.log 2>&1 &
for _ in $(seq 60); do
    if info=$(curl -sf http://127.0.0.1:8000/api/v1/info); then
        echo "$info"
        exit 0
    fi
    sleep 2
done
cat /tmp/cloutfox.log
exit 1
