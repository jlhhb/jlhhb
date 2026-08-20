#!/usr/bin/env bash
#
# Cloud Agent install script for Actions-OpenWrt.
#
# Prepares a ready-to-compile OpenWrt (coolsnowwolf/lede) buildroot that mirrors
# the steps performed by .github/workflows/openwrt-builder.yml, so a Cloud Agent
# can iterate on the DIY scripts / .config and run `make` without any manual
# bootstrapping. The script is idempotent and safe to re-run.
#
set -euo pipefail

# These mirror the env block of the OpenWrt Builder workflow. Override them via
# environment variables if you build from a different source or branch.
REPO_URL="${REPO_URL:-https://github.com/coolsnowwolf/lede}"
REPO_BRANCH="${REPO_BRANCH:-master}"
FEEDS_CONF="${FEEDS_CONF:-feeds.conf.default}"
CONFIG_FILE="${CONFIG_FILE:-.config}"
DIY_P1_SH="${DIY_P1_SH:-diy-part1.sh}"
DIY_P2_SH="${DIY_P2_SH:-diy-part2.sh}"

# The OpenWrt tree is large, so it lives outside the git working tree and is
# symlinked in for convenience (mirrors the CI layout).
OPENWRT_DIR="${OPENWRT_DIR:-/workdir/openwrt}"
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing OpenWrt build dependencies"
export DEBIAN_FRONTEND=noninteractive
sudo -E apt-get update -qq
# Package list mirrors the ubuntu-22.04 GitHub Actions runner. python2.7 is
# intentionally omitted: it is no longer packaged for Ubuntu 24.04 and modern
# OpenWrt builds with python3.
sudo -E apt-get install -y --no-install-recommends \
  ack antlr3 asciidoc autoconf automake autopoint binutils bison build-essential \
  bzip2 ccache cmake cpio curl device-tree-compiler fastjar flex gawk gettext \
  gcc-multilib g++-multilib git gperf haveged help2man intltool libc6-dev-i386 \
  libelf-dev libfuse-dev libglib2.0-dev libgmp3-dev libltdl-dev libmpc-dev \
  libmpfr-dev libncurses5-dev libncursesw5-dev libpython3-dev libreadline-dev \
  libssl-dev libtool lrzsz mkisofs msmtp ninja-build p7zip p7zip-full patch \
  pkgconf python3 python3-pyelftools python3-setuptools qemu-utils rsync scons \
  squashfs-tools subversion swig texinfo uglifyjs upx-ucl unzip vim wget xmlto \
  xxd zlib1g-dev
sudo -E apt-get clean

# The base image defaults `cc`/`c++` to clang, but OpenWrt's host build expects
# GCC (the CI runner uses GCC). clang fails to link -lstdc++ for host tools such
# as elfutils, so pin the alternatives to GCC.
if update-alternatives --list cc 2>/dev/null | grep -q '/usr/bin/gcc'; then
  sudo update-alternatives --set cc /usr/bin/gcc
fi
if update-alternatives --list c++ 2>/dev/null | grep -q '/usr/bin/g++'; then
  sudo update-alternatives --set c++ /usr/bin/g++
fi

echo "==> Preparing OpenWrt source tree at ${OPENWRT_DIR}"
sudo mkdir -p "$(dirname "${OPENWRT_DIR}")"
sudo chown "$(id -un)":"$(id -gn)" "$(dirname "${OPENWRT_DIR}")"
if [ ! -d "${OPENWRT_DIR}/.git" ]; then
  git clone --depth 1 "${REPO_URL}" -b "${REPO_BRANCH}" "${OPENWRT_DIR}"
else
  echo "    Source already present; fast-forwarding."
  git -C "${OPENWRT_DIR}" pull --ff-only || true
fi

ln -sfn "${OPENWRT_DIR}" "${WORKSPACE_DIR}/openwrt"

echo "==> Loading custom feeds (${DIY_P1_SH})"
# Restore the pristine feeds config so re-runs do not append duplicate entries.
git -C "${OPENWRT_DIR}" checkout -- feeds.conf.default 2>/dev/null || true
if [ -e "${WORKSPACE_DIR}/${FEEDS_CONF}" ]; then
  cp "${WORKSPACE_DIR}/${FEEDS_CONF}" "${OPENWRT_DIR}/feeds.conf.default"
fi
chmod +x "${WORKSPACE_DIR}/${DIY_P1_SH}"
( cd "${OPENWRT_DIR}" && "${WORKSPACE_DIR}/${DIY_P1_SH}" )

echo "==> Updating and installing feeds"
( cd "${OPENWRT_DIR}" && ./scripts/feeds update -a && ./scripts/feeds install -a )

echo "==> Loading custom configuration (${DIY_P2_SH})"
if [ -e "${WORKSPACE_DIR}/files" ]; then
  rm -rf "${OPENWRT_DIR}/files"
  cp -r "${WORKSPACE_DIR}/files" "${OPENWRT_DIR}/files"
fi
if [ -s "${WORKSPACE_DIR}/${CONFIG_FILE}" ]; then
  cp "${WORKSPACE_DIR}/${CONFIG_FILE}" "${OPENWRT_DIR}/.config"
fi
chmod +x "${WORKSPACE_DIR}/${DIY_P2_SH}"
( cd "${OPENWRT_DIR}" && "${WORKSPACE_DIR}/${DIY_P2_SH}" )

echo "==> Expanding configuration (make defconfig)"
( cd "${OPENWRT_DIR}" && make defconfig )

echo "==> Install complete. OpenWrt buildroot is ready at ${OPENWRT_DIR}"
echo "    Run 'cd openwrt && make -j\$(nproc)' to build the firmware."
