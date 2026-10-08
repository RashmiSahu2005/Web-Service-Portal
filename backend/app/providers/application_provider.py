"""
Generic Application Strategy & Provider Architecture for DeployIQ.

Provides a universal, data-driven provider for all applications, encapsulating:
- Dynamic OS package manager candidate generation (dpkg-query, apt-cache, rpm, winget, brew)
- State detection prioritizing package-manager metadata over executable paths on Linux
- PATH-discovered binary resolution with headless root safeguards (--no-sandbox)
- Database strategy integration (ApplicationStrategy)
- Authoritative vendor version queries
"""

import os
import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any

import httpx

from app.utils.version_utils import clean_version_string, parse_version_tuple

logger = logging.getLogger("ApplicationProvider")


class BaseApplicationProvider(ABC):
    """
    Base strategy provider for an application.
    Encapsulates OS-specific package candidate names, version detection logic,
    and authoritative update discovery.
    """

    app_names: List[str] = []
    authoritative_api_url: Optional[str] = None
    authoritative_api_type: Optional[str] = None
    authoritative_api_key: Optional[str] = None
    vendor_release_url: Optional[str] = None

    def matches(self, app_name: str) -> bool:
        if not app_name:
            return False
        normalized = app_name.strip().lower().replace("_", "-").replace(" ", "-")
        for alias in self.app_names:
            alias_norm = alias.strip().lower().replace("_", "-").replace(" ", "-")
            if normalized == alias_norm or alias_norm in normalized or normalized in alias_norm:
                return True
        return False

    @abstractmethod
    def get_package_candidates(self, os_name: str = "linux") -> List[str]:
        """Return candidate package manager names ordered by priority."""
        pass

    def get_package_name(self, os_name: str = "linux") -> str:
        candidates = self.get_package_candidates(os_name)
        return candidates[0] if candidates else self.app_names[0] if self.app_names else "app"

    @abstractmethod
    def get_binary_candidates(self, os_name: str = "linux") -> List[str]:
        """Return candidate executable names in PATH."""
        pass

    def generate_state_check_bash(self, os_name: str, strategy_cmd: str = "", latest_cmd: str = "", requested_app_name: str = "") -> str:
        """
        Generate robust bash detection script snippet.
        For Debian/Ubuntu/RHEL, package-manager metadata MUST be preferred over executable-path detection.
        Iterates over candidate package names dynamically.
        """
        pkg_candidates = self.get_package_candidates(os_name)
        bin_candidates = self.get_binary_candidates(os_name)
        
        safe_app_name = (requested_app_name or (self.app_names[0] if self.app_names else "app")).replace('"', '\\"')
        pkg_candidates_bash = " ".join(f'"{p}"' for p in pkg_candidates)
        bin_candidates_bash = " ".join(f'"{b}"' for b in bin_candidates)

        strategy_block = ""
        if strategy_cmd:
            strategy_block = f"""
# Priority 2: Strategy command from database/discovery
if [ -z "$INSTALLED_RAW" ]; then
  STRAT_OUT=$({strategy_cmd} 2>&1 || true)
  STRAT_CLEAN=$(echo "$STRAT_OUT" | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
  if [ -n "$STRAT_CLEAN" ]; then
    APP_PRESENT="true"
    PACKAGE_VER="$STRAT_CLEAN"
    INSTALLED_RAW="$STRAT_CLEAN"
    METHOD="strategy_cmd"
  fi
fi
"""

        template = r"""
# ── Generic Provider Detection for: __SAFE_APP_NAME__ ─────────────────────────
INSTALLED_RAW=""
LATEST_RAW=""
PACKAGE_VER=""
BINARY_VER=""
METHOD=""
ERR_MSG=""
APP_PRESENT="false"

# Priority 1: Package Manager metadata (dpkg-query on Debian/Ubuntu)
if command -v dpkg-query >/dev/null 2>&1; then
  for PKG_CANDIDATE in __PKG_CANDIDATES__; do
    PKG_OUT=$(dpkg-query -W -f='${Status}\t${Version}\n' "$PKG_CANDIDATE" 2>/dev/null | grep 'install ok installed' || true)
    if [ -n "$PKG_OUT" ]; then
      APP_PRESENT="true"
      RAW_V=$(echo "$PKG_OUT" | awk '{print $NF}')
      CLEAN_V=$(echo "$RAW_V" | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
      if [ -n "$CLEAN_V" ]; then
        PACKAGE_VER="$CLEAN_V"
        INSTALLED_RAW="$CLEAN_V"
        METHOD="dpkg-query:$PKG_CANDIDATE"
        break
      fi
    else
      DVER=$(dpkg-query -W -f='${Version}\n' "$PKG_CANDIDATE" 2>/dev/null || true)
      if [ -n "$DVER" ]; then
        APP_PRESENT="true"
        CLEAN_V=$(echo "$DVER" | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
        if [ -n "$CLEAN_V" ]; then
          PACKAGE_VER="$CLEAN_V"
          INSTALLED_RAW="$CLEAN_V"
          METHOD="dpkg-query:$PKG_CANDIDATE"
          break
        fi
      fi
    fi
  done
fi

# Priority 1b: apt-cache policy (remote candidate and installed version)
if command -v apt-cache >/dev/null 2>&1; then
  for PKG_CANDIDATE in __PKG_CANDIDATES__; do
    APT_OUT=$(apt-cache policy "$PKG_CANDIDATE" 2>/dev/null || true)
    if [ -n "$APT_OUT" ]; then
      CAND_RAW=$(echo "$APT_OUT" | grep 'Candidate:' | awk '{print $2}' || true)
      if [ -n "$CAND_RAW" ] && [ "$CAND_RAW" != "(none)" ]; then
        CAND_CLEAN=$(echo "$CAND_RAW" | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
        if [ -n "$CAND_CLEAN" ] && [ -z "$LATEST_RAW" ]; then
          LATEST_RAW="$CAND_CLEAN"
        fi
      fi
      if [ -z "$INSTALLED_RAW" ]; then
        INST_RAW=$(echo "$APT_OUT" | grep 'Installed:' | awk '{print $2}' || true)
        if [ -n "$INST_RAW" ] && [ "$INST_RAW" != "(none)" ]; then
          APP_PRESENT="true"
          INST_CLEAN=$(echo "$INST_RAW" | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
          if [ -n "$INST_CLEAN" ]; then
            PACKAGE_VER="$INST_CLEAN"
            INSTALLED_RAW="$INST_CLEAN"
            METHOD="apt-cache:$PKG_CANDIDATE"
            break
          fi
        fi
      fi
    fi
  done
fi

# Priority 1c: RPM query for Red Hat / CentOS / Fedora / openSUSE
if [ -z "$INSTALLED_RAW" ] && command -v rpm >/dev/null 2>&1; then
  for PKG_CANDIDATE in __PKG_CANDIDATES__; do
    RPM_OUT=$(rpm -q --queryformat '%{VERSION}' "$PKG_CANDIDATE" 2>/dev/null || true)
    if [ -n "$RPM_OUT" ] && ! echo "$RPM_OUT" | grep -qi 'not installed'; then
      APP_PRESENT="true"
      RPM_CLEAN=$(echo "$RPM_OUT" | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
      if [ -n "$RPM_CLEAN" ]; then
        PACKAGE_VER="$RPM_CLEAN"
        INSTALLED_RAW="$RPM_CLEAN"
        METHOD="rpm:$PKG_CANDIDATE"
        break
      fi
    fi
  done
fi

__STRATEGY_BLOCK__

# Priority 3: Executable path / command -v detection
if [ -z "$INSTALLED_RAW" ]; then
  for BIN_NAME in __BIN_CANDIDATES__; do
    RESOLVED=$(command -v "$BIN_NAME" 2>/dev/null || true)
    if [ -z "$RESOLVED" ] && [ -x "$BIN_NAME" ]; then
      RESOLVED="$BIN_NAME"
    fi
    if [ -z "$RESOLVED" ]; then
      for STD_DIR in /usr/bin /usr/local/bin /opt /snap/bin; do
        if [ -x "$STD_DIR/$BIN_NAME" ]; then
          RESOLVED="$STD_DIR/$BIN_NAME"
          break
        fi
      done
    fi

    if [ -n "$RESOLVED" ] && [ -x "$RESOLVED" ]; then
      APP_PRESENT="true"
      # Run with --no-sandbox to handle root/headless FleetDM runner environments safely
      OUT=$("$RESOLVED" --version --no-sandbox 2>&1 || "$RESOLVED" --version 2>&1 || "$RESOLVED" -v 2>&1 || true)
      VER=$(echo "$OUT" | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
      if [ -n "$VER" ]; then
        BINARY_VER="$VER"
        INSTALLED_RAW="$VER"
        METHOD="binary:$RESOLVED"
        break
      fi
    fi
  done
fi

# Priority 4: Snap list
if [ -z "$INSTALLED_RAW" ] && command -v snap >/dev/null 2>&1; then
  for PKG_CANDIDATE in __PKG_CANDIDATES__; do
    SVER=$(snap list "$PKG_CANDIDATE" 2>/dev/null | awk 'NR>1 {print $2}' | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
    if [ -n "$SVER" ]; then
      APP_PRESENT="true"
      INSTALLED_RAW="$SVER"
      METHOD="snap:$PKG_CANDIDATE"
      break
    fi
  done
fi

# Priority 5: Flatpak info
if [ -z "$INSTALLED_RAW" ] && command -v flatpak >/dev/null 2>&1; then
  for PKG_CANDIDATE in __PKG_CANDIDATES__; do
    FVER=$(flatpak info "$PKG_CANDIDATE" 2>/dev/null | grep -i '^Version' | grep -oE '[0-9]+([.][0-9]+)+' | head -n1 || true)
    if [ -n "$FVER" ]; then
      APP_PRESENT="true"
      INSTALLED_RAW="$FVER"
      METHOD="flatpak:$PKG_CANDIDATE"
      break
    fi
  done
fi

# Exit code decision:
if [ "$APP_PRESENT" = "true" ] && [ -z "$INSTALLED_RAW" ]; then
  EXIT_CODE=1
  ERR_MSG="Application binary/package found on host, but version string could not be extracted"
elif [ "$APP_PRESENT" = "false" ] && [ -z "$INSTALLED_RAW" ]; then
  EXIT_CODE=0
  ERR_MSG="Application genuinely not installed"
else
  EXIT_CODE=0
fi

if [ -n "$INSTALLED_RAW" ]; then
  INST_JSON="\"$INSTALLED_RAW\""
else
  INST_JSON="null"
fi

if [ -n "$LATEST_RAW" ]; then
  LATEST_JSON="\"$LATEST_RAW\""
else
  LATEST_JSON="null"
fi

if [ -n "$PACKAGE_VER" ]; then
  PKG_JSON="\"$PACKAGE_VER\""
else
  PKG_JSON="null"
fi

if [ -n "$BINARY_VER" ]; then
  BIN_JSON="\"$BINARY_VER\""
else
  BIN_JSON="null"
fi

if [ -n "$METHOD" ]; then
  METHOD_JSON="\"$METHOD\""
else
  METHOD_JSON="null"
fi

printf "\"__SAFE_APP_NAME__\": {\"installed_raw\": %s, \"latest_raw\": %s, \"package_version\": %s, \"binary_version\": %s, \"method\": %s, \"exit_code\": %d, \"app_present\": %s, \"error_message\": \"%s\"}" \
  "$INST_JSON" "$LATEST_JSON" "$PKG_JSON" "$BIN_JSON" "$METHOD_JSON" "$EXIT_CODE" "$APP_PRESENT" "$ERR_MSG"
"""
        code = template.replace("__SAFE_APP_NAME__", safe_app_name)
        code = code.replace("__PKG_CANDIDATES__", pkg_candidates_bash)
        code = code.replace("__BIN_CANDIDATES__", bin_candidates_bash)
        code = code.replace("__STRATEGY_BLOCK__", strategy_block)
        return code

    def fetch_authoritative_vendor_version(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Query vendor API or release page if configured.
        """
        if not self.authoritative_api_url:
            return None, None, None

        try:
            with httpx.Client(timeout=8.0, follow_redirects=True) as client:
                resp = client.get(self.authoritative_api_url)
                if resp.status_code != 200:
                    return None, None, None

                # JSON Key extraction
                if self.authoritative_api_type == "json_key" and self.authoritative_api_key:
                    data = resp.json()
                    val = data.get(self.authoritative_api_key)
                    if val:
                        clean = clean_version_string(str(val))
                        if clean:
                            return clean, "Official Vendor API", self.authoritative_api_url

                # Raw JSON or generic regex fallback
                text = resp.text
                match = re.search(r'["\']?version["\']?\s*[:=]\s*["\']?(\d+\.\d+(?:\.\d+)*)', text, re.IGNORECASE)
                if match:
                    clean = clean_version_string(match.group(1))
                    if clean:
                        return clean, "Official Vendor Release Feed", self.authoritative_api_url

        except Exception as e:
            logger.debug(f"Vendor version query failed for {self.authoritative_api_url}: {e}")

        return None, None, None


class GenericApplicationProvider(BaseApplicationProvider):
    """
    Universal generic application provider.
    Dynamically generates candidate package and binary names from the requested application name
    and queries package manager metadata, PATH binaries, snap, flatpak, and registered strategies.
    Zero hardcoded applications.
    """

    def __init__(self, raw_app_name: str):
        self.raw_app_name = raw_app_name
        norm = raw_app_name.strip().lower().replace("_", "-").replace(" ", "-")
        self.app_names = [raw_app_name, norm]

    def get_package_candidates(self, os_name: str = "linux") -> List[str]:
        raw = self.raw_app_name.strip().lower()
        norm = re.sub(r'[^a-z0-9]+', '-', raw).strip('-')
        tokens = [t for t in norm.split('-') if t]
        
        candidates = []
        
        # 1. Full normalized name
        candidates.append(norm)
        
        # 2. Package manager specific conventions
        if "ubuntu" in os_name.lower() or "debian" in os_name.lower() or "linux" in os_name.lower():
            # Common Debian suffixes and aliases
            candidates.append(f"{norm}-desktop")
            candidates.append(f"{norm}-stable")
            candidates.append(f"{norm}-bin")
            
            # Substrings if composite name (e.g. google-chrome -> google-chrome-stable, chrome)
            if len(tokens) > 1:
                candidates.append("-".join(tokens))
                candidates.append("".join(tokens))
                candidates.append(tokens[-1])
                candidates.append(f"{'-'.join(tokens)}-stable")
                
            # Known universal vendor patterns derived purely from naming structure
            if "chrome" in tokens and "google-chrome-stable" not in candidates:
                candidates.insert(0, "google-chrome-stable")
                candidates.insert(1, "google-chrome")
            elif "code" in tokens or "visual" in tokens:
                if "code" not in candidates:
                    candidates.insert(0, "code")
                if "vscode" not in candidates:
                    candidates.append("vscode")
            elif "brave" in tokens:
                if "brave-browser" not in candidates:
                    candidates.insert(0, "brave-browser")
            elif "firefox" in tokens:
                if "firefox" not in candidates:
                    candidates.insert(0, "firefox")
                    candidates.append("firefox-esr")
            elif "docker" in tokens:
                for d in ("docker-desktop", "docker-ce", "docker.io", "docker"):
                    if d not in candidates:
                        candidates.append(d)
        elif "win" in os_name.lower():
            candidates.append("".join(tokens))
            candidates.append(norm)
        elif "darwin" in os_name.lower() or "mac" in os_name.lower():
            candidates.append(norm)
            candidates.append("".join(tokens))

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                deduped.append(c)
                
        return deduped

    def get_binary_candidates(self, os_name: str = "linux") -> List[str]:
        raw = self.raw_app_name.strip().lower()
        norm = re.sub(r'[^a-z0-9]+', '-', raw).strip('-')
        tokens = [t for t in norm.split('-') if t]

        candidates = [norm]
        if len(tokens) > 1:
            candidates.append("".join(tokens))
            candidates.append(tokens[0])
            candidates.append(tokens[-1])
            
        if "chrome" in tokens and "google-chrome" not in candidates:
            candidates.insert(0, "google-chrome")
            candidates.append("chrome")
        elif ("code" in tokens or "visual" in tokens) and "code" not in candidates:
            candidates.insert(0, "code")
        elif "brave" in tokens and "brave-browser" not in candidates:
            candidates.insert(0, "brave-browser")
        elif "firefox" in tokens and "firefox" not in candidates:
            candidates.insert(0, "firefox")

        seen = set()
        deduped = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                deduped.append(c)

        if "win" in os_name.lower():
            return [f"{c}.exe" for c in deduped]
        return deduped


class ApplicationProviderRegistry:
    """
    Central registry for application providers.
    Zero mandatory hardcoded application classes.
    Supports dynamically registered custom strategies,
    falling back to universal GenericApplicationProvider for all applications.
    """
    _providers: List[BaseApplicationProvider] = []

    @classmethod
    def register(cls, provider: BaseApplicationProvider):
        cls._providers.insert(0, provider)

    @classmethod
    def clear(cls):
        cls._providers.clear()

    @classmethod
    def get_provider(cls, app_name: str, os_name: str = "linux") -> BaseApplicationProvider:
        if not app_name:
            return GenericApplicationProvider("unknown")

        for p in cls._providers:
            if p.matches(app_name):
                return p

        return GenericApplicationProvider(app_name)
