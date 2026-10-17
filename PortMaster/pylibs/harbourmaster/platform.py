# SPDX-License-Identifier: MIT
#
# NOT CODE: a marker for older spruce releases.
#
# The platform code is the harbourmaster/platform/ package; Python always imports
# that package over this file, so nothing here ever runs.
#
# spruce's App/PortMaster/launch.sh decides whether PortMaster knows about spruce
# with:
#
#   grep -q "PlatformSpruce" "$PM_DIR/pylibs/harbourmaster/platform.py"
#
# Without this file that check fails and spruce runs its own bundled copy of the
# old launcher. Remove it once spruce checks the package instead, eg:
#
#   grep -rqs "PlatformSpruce" "$PM_DIR/pylibs/harbourmaster/"
#
# PlatformSpruce
