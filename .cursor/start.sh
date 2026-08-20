#!/usr/bin/env bash
#
# Cloud Agent start script for Actions-OpenWrt.
#
# Runs on every boot. It only re-establishes the convenience symlink to the
# OpenWrt buildroot (which lives outside the git working tree); it is a no-op if
# the buildroot has not been prepared yet.
#
set -euo pipefail

OPENWRT_DIR="${OPENWRT_DIR:-/workdir/openwrt}"
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -d "${OPENWRT_DIR}" ]; then
  ln -sfn "${OPENWRT_DIR}" "${WORKSPACE_DIR}/openwrt"
fi
