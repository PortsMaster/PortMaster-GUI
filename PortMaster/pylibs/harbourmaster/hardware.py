# SPDX-License-Identifier: MIT
# ==============================================================================
# PortMaster Hardware Provider (Shell-Backed Engine with Safe Fallback)
# ==============================================================================
from __future__ import annotations

import copy
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Global in-memory memoization cache
_CACHED_DICT: Optional[Dict[str, Any]] = None


def _clean_str(val: Any) -> str:
    """Strips null bytes, carriage returns, leading/trailing whitespace, and quotes."""
    if val is None:
        return ""
    return str(val).replace("\x00", "").strip("\"' \r\n\t")


def _safe_int(val: Any, default: int = 0) -> int:
    """Safely converts values to int, returning default on failure or empty string."""
    if val is None:
        return default
    try:
        val_str = _clean_str(val)
        return int(val_str) if val_str else default
    except (ValueError, TypeError):
        return default


def _script_version(script: Path) -> Optional[str]:
    """DEVICE_INFO_VERSION as device_info.txt sets it, or None."""
    try:
        with open(script, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                match = re.match(r'\s*(?:export\s+)?DEVICE_INFO_VERSION="?([^"\s]+)"?', line)
                if match:
                    return match.group(1)
    except Exception:
        pass
    return None


def _read_env_file(env_path: Path) -> Dict[str, str]:
    """Reads key-value pairs from a POSIX shell env file safely."""
    res: Dict[str, str] = {}
    if not env_path.is_file():
        return res
    try:
        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.replace("\x00", "").strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                res[_clean_str(k).lower()] = _clean_str(v)
    except Exception:
        pass
    return res


def _normalize_glibc(raw: str) -> str:
    raw = _clean_str(raw)
    if not raw or raw.lower() in ("unknown", "none", "0"):
        return "0.0.0"  # Prevent version_parse crashes in HarbourMaster
    if "." in raw or not raw.isdigit():
        return raw
    if len(raw) == 3:
        return f"{raw[0]}.{raw[1:]}"
    return raw


def _find_control_dir() -> Path:
    if os.environ.get("controlfolder"):
        return Path(_clean_str(os.environ["controlfolder"]))
    if os.environ.get("PORTMASTER_HOME"):
        return Path(_clean_str(os.environ["PORTMASTER_HOME"]))

    file_path = Path(__file__).resolve()
    for p in file_path.parents:
        if (p / "version").is_file() or p.name.lower() == "portmaster":
            return p
    if len(file_path.parents) >= 3:
        return file_path.parents[2]
    return file_path.parent


class HardwareDetector:
    """Consumes hardware and capabilities exported by device_info shell script."""

    def __init__(self, control_dir: Optional[Union[str, Path]] = None):
        self.control_dir = Path(control_dir) if control_dir else _find_control_dir()
        self.env_is_stale = False

    def _quick_probe_identity(self) -> Tuple[str, str]:
        """Fast helper to resolve the exact device_info_<cfw>_<device>.env filename."""
        cfw_name = "unknown"
        dev_name = "unknown"

        # 1. Host CFW Resolution
        if Path("/app/bin/retrodeck").is_file() or os.environ.get("FLATPAK_ID") == "net.retrodeck.retrodeck":
            cfw_name = "retrodeck"
        elif Path("/etc/rocknix-release").is_file() or Path("/storage/.config/rocknix").is_file():
            cfw_name = "rocknix"
        elif Path("/etc/jelos-release").is_file() or Path("/storage/.config/jelos").is_file():
            cfw_name = "jelos"
        elif Path("/opt/muos").is_dir() or Path("/opt/muos/config/system/version").is_file():
            cfw_name = "muos"
        elif Path("/boot/boot/knulli.board").is_file() or Path("/etc/knulli.version").is_file():
            cfw_name = "knulli"
        elif Path("/etc/arkos_version").is_file() or Path("/etc/darkos_version").is_file():
            cfw_name = "arkos"
        elif Path("/usr/share/plymouth/themes/text.plymouth").is_file():
            try:
                txt = Path("/usr/share/plymouth/themes/text.plymouth").read_text(encoding="utf-8", errors="ignore").lower()
                if "darkos" in txt:
                    cfw_name = "darkos"
                elif "thera" in txt:
                    cfw_name = "thera"
                elif "arkos" in txt:
                    cfw_name = "arkos"
            except Exception:
                pass

        # 2. Host Device Resolution (Includes ArkOS, muOS, knulli, etc.)
        home = Path.home()
        device_files = [
            Path("/opt/muos/device/config/board/name"),
            Path("/boot/boot/knulli.board"),
            Path("/userdata/system/knulli.board"),
            Path("/userdata/system/.DEVICE"),
            Path("/userdata/system/.CUSTOM_DEVICE"),
            home / ".config/.CUSTOM_DEVICE",
            home / ".config/.DEVICE",
            home / ".config/.OS_ARCH",
            Path("/etc/device_model"),
            Path("/etc/board"),
            Path("/proc/device-tree/model"),
        ]

        for b in device_files:
            if b.is_file():
                try:
                    txt = _clean_str(b.read_text(encoding="utf-8", errors="ignore")).splitlines()[0]
                    if txt:
                        dev_name = txt
                        break
                except Exception:
                    pass

        if dev_name == "unknown" and Path("/sys/devices/virtual/dmi/id/product_name").is_file():
            try:
                txt = _clean_str(Path("/sys/devices/virtual/dmi/id/product_name").read_text(encoding="utf-8", errors="ignore"))
                if txt:
                    dev_name = txt
            except Exception:
                pass

        # Match device_info.txt: lower case, spaces and slashes ("Debian GNU/Linux") to _
        safe_cfw = _clean_str(cfw_name).lower().replace(" ", "_").replace("/", "_")
        safe_dev = _clean_str(dev_name).lower().replace(" ", "_").replace("/", "_")
        return safe_cfw, safe_dev

    def _device_info_script(self) -> Optional[Path]:
        for script_name in ["device_info.txt", "device_info.sh", "PortMaster/device_info.txt", "PortMaster/device_info.sh"]:
            sh_script = self.control_dir / script_name
            if sh_script.is_file():
                return sh_script

        return None

    def _load_raw_data(self, force_refresh: bool = False) -> Dict[str, str]:
        ## Some CFWs replace control.txt with their own that never sources device_info.txt
        ## (ROCKNIX 20250517), so nothing else replaces a cache an older version wrote.
        script = self._device_info_script()
        wanted = _script_version(script) if script is not None else None

        # Priority 1: In-memory environment (Zero Disk I/O)
        self.env_is_stale = False
        if not force_refresh:
            if os.environ.get("DEVICE_NAME") or os.environ.get("DEVICE_CPU") or os.environ.get("CFW_NAME"):
                ## Only what this device_info.txt exported. Another version's (older or newer)
                ## is left over: PortMaster updated itself and restarted under the launcher
                ## that was running, and 0.1.x has no DEVICE_CAPABILITIES, so every port was
                ## "incompatible". With no version at all, only variables set by hand to
                ## pretend to be a device, which have DEVICE_CAPABILITIES (a CFW's own
                ## control.txt may export CFW_NAME and nothing else).
                env_version = _clean_str(os.environ.get("DEVICE_INFO_VERSION", ""))
                if env_version == "":
                    trusted = _clean_str(os.environ.get("DEVICE_CAPABILITIES", "")) != ""
                else:
                    trusted = wanted is None or env_version == wanted

                if trusted:
                    return {_clean_str(k).lower(): _clean_str(v) for k, v in os.environ.items()}

                self.env_is_stale = True

        safe_cfw, safe_dev = self._quick_probe_identity()
        target_file = self.control_dir / f"device_info_{safe_cfw}_{safe_dev}.env"

        def current(env_file: Path) -> bool:
            if wanted is None:
                return True

            return _read_env_file(env_file).get("device_info_version") == wanted

        def usable(env_file: Path) -> bool:
            return env_file.is_file() and env_file.stat().st_size > 30

        stale = None

        # Priority 2: Named cache matching active hardware
        if not force_refresh and usable(target_file):
            if current(target_file):
                return _read_env_file(target_file)

            stale = target_file

        # Priority 3: Fallback check for any valid device_info_*.env in the folder
        if not force_refresh:
            candidates = [p for p in self.control_dir.glob("device_info_*.env") if usable(p)]
            if candidates:
                newest = max(candidates, key=lambda p: p.stat().st_mtime)
                if current(newest):
                    return _read_env_file(newest)

                stale = stale or newest

        # Priority 4: Run device_info.txt to probe hardware and generate env. A full
        # probe takes 10-15 s on some devices (Miyoo Flip, TrimUI Brick Pro).
        if script is not None:
            try:
                run_env = {
                    **os.environ,
                    "controlfolder": str(self.control_dir),
                    "NO_SDL_RESOLUTION": "1",
                }
                subprocess.run(
                    ["bash", str(script), "-f"],
                    cwd=str(self.control_dir),
                    env=run_env,
                    timeout=60,
                    check=False,
                )
                if usable(target_file) and current(target_file):
                    return _read_env_file(target_file)

                # Return whichever cache file was updated by the script
                candidates = [p for p in self.control_dir.glob("device_info_*.env") if usable(p)]
                if candidates:
                    newest = max(candidates, key=lambda p: p.stat().st_mtime)
                    if current(newest):
                        return _read_env_file(newest)
            except Exception:
                pass

        # An out of date cache beats nothing.
        if stale is not None:
            return _read_env_file(stale)

        return {}

    def get_info(self, force_refresh: bool = False) -> Dict[str, Any]:
        global _CACHED_DICT
        if not force_refresh and _CACHED_DICT is not None:
            return _CACHED_DICT

        raw_env = self._load_raw_data(force_refresh)

        ## Nor anything an older device_info.txt left in the environment.
        env = {} if self.env_is_stale else os.environ

        def get_val(key: str, default: Any) -> Any:
            val = raw_env.get(key.lower(), env.get(key.upper(), default))
            if val is None or (isinstance(val, str) and not _clean_str(val)):
                return default
            return _clean_str(val) if isinstance(val, str) else val

        w = _safe_int(get_val("display_width", 640), 640)
        h = _safe_int(get_val("display_height", 480), 480)

        ram_mb_val = get_val("device_ram_mb", None)
        if ram_mb_val is not None:
            ram_mb = _safe_int(ram_mb_val, 1024)
        else:
            ram_mb = _safe_int(get_val("device_ram", 1), 1) * 1024

        sticks = _safe_int(get_val("analog_sticks", 0), 0)
        cfw = str(get_val("cfw_name", "Unknown")).lower()
        dev_slug = str(get_val("device_slug", get_val("device_name", "unknown"))).lower()
        has_touch = str(get_val("device_touch", get_val("has_touch", "N"))).upper()
        has_rumble = str(get_val("device_has_rumble", "N")).upper()

        caps_raw = str(get_val("device_capabilities", "")).strip()
        capabilities = caps_raw.split() if caps_raw else []

        info: Dict[str, Any] = {
            "name": cfw,
            "version": str(get_val("cfw_version", "Unknown")),
            "kernel_version": str(get_val("device_kernel_version", "Unknown")),
            "device": dev_slug,
            "model": str(get_val("device_name", "Unknown")),
            "resolution": (w, h),
            "refresh_rate": _safe_int(get_val("device_refresh_rate", 60), 60),
            "orientation": _safe_int(get_val("display_orientation", 0), 0),
            "analogsticks": sticks,
            "analogtriggers": str(get_val("analog_triggers", "N")),
            "touch": has_touch,
            "rumble": has_rumble,
            "gpu_driver": str(get_val("gpu_driver", "Unknown")),
            "gpu_driver_version": str(get_val("gpu_driver_version", "Unknown")),
            "has_swap": str(get_val("device_has_swap", "N")),
            "has_zram": str(get_val("device_has_zram", "N")),
            "cpu": str(get_val("device_cpu", "Unknown")),
            "capabilities": capabilities,
            "primary_arch": str(get_val("device_arch", "aarch64")),
            "ram": ram_mb,
            "glibc": _normalize_glibc(get_val("cfw_glibc", "0.0.0")),
        }

        _CACHED_DICT = info
        return info


# ==============================================================================
# HarbourMaster & Pugwash API Endpoints and Compatibility Shims
# ==============================================================================
HW_INFO: Dict[str, Any] = {}
DEVICES: Dict[str, Any] = {}


def device_info(config: Any = None) -> Dict[str, Any]:
    return HardwareDetector().get_info()


def hardware_info() -> Dict[str, Any]:
    return HardwareDetector().get_info()


def find_device_by_resolution(resolution: Tuple[int, int]) -> str:
    info = HardwareDetector().get_info()
    if info.get("resolution") == resolution:
        return info.get("device", "default")
    return "default"


def expand_info(
    info: Dict[str, Any],
    override_resolution: Optional[Tuple[int, int]] = None,
    override_ram: Optional[int] = None,
    use_old_cpu_info: bool = False,
) -> Dict[str, Any]:
    base_info = HardwareDetector().get_info()
    if not isinstance(info, dict):
        info = copy.deepcopy(base_info)
    else:
        for k, v in base_info.items():
            info.setdefault(k, v)

    if override_resolution:
        w, h = override_resolution
        info["resolution"] = (w, h)
        caps = [c for c in info.get("capabilities", []) if not ("x" in c and c.replace("x", "").isdigit())]
        caps.append(f"{w}x{h}")
        info["capabilities"] = caps

    if override_ram:
        info["ram"] = override_ram

    return info


__all__ = [
    "device_info",
    "hardware_info",
    "expand_info",
    "find_device_by_resolution",
    "DEVICES",
    "HW_INFO",
]
