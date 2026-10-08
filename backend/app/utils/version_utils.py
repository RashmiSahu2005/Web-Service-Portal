import re
from typing import Tuple, Optional

def parse_version_tuple(version_str: str) -> Tuple[int, ...]:
    """
    Extract all numerical components from a version string.
    Example: 'v1.94.121-beta' -> (1, 94, 121)
    """
    if not version_str:
        return ()
    clean_str = str(version_str).strip().lstrip('vV')
    nums = re.findall(r'\d+', clean_str)
    return tuple(int(x) for x in nums)

def clean_version_string(version_str: str) -> Optional[str]:
    """
    Returns a cleaned version string (e.g. '1.94.121') or None.
    """
    if not version_str or version_str.strip().lower() in ("null", "none", "unknown"):
        return None
    match = re.search(r'\d+(\.\d+)+', str(version_str).strip())
    if match:
        return match.group(0)
    # Fallback to pure numbers if no dots
    nums = re.findall(r'\d+', str(version_str).strip())
    if nums:
        return ".".join(nums)
    return None

def canonicalize_version(
    binary_version: Optional[str],
    package_version: Optional[str],
    package_manager: Optional[str] = None
) -> Tuple[Optional[str], str]:
    """
    Determines the canonical version string and source for an installed application.
    
    Handles cases like Brave Browser where binary reports Chromium base '152.1.94.121'
    and package manager (APT) reports '1.94.121'.
    
    Returns:
        (canonical_version, source_name)
    """
    bin_clean = clean_version_string(binary_version)
    pkg_clean = clean_version_string(package_version)
    
    source = package_manager.upper() if package_manager else "PACKAGE_MANAGER"
    
    if bin_clean and pkg_clean:
        bin_tup = parse_version_tuple(bin_clean)
        pkg_tup = parse_version_tuple(pkg_clean)
        
        # Check if package version is a suffix of binary version (e.g. 152.1.94.121 vs 1.94.121)
        if len(bin_tup) > len(pkg_tup) and bin_tup[-len(pkg_tup):] == pkg_tup:
            return pkg_clean, source
            
        # Check if binary version is a suffix of package version
        if len(pkg_tup) > len(bin_tup) and pkg_tup[-len(bin_tup):] == bin_tup:
            return bin_clean, "BINARY"
            
        # Default when both exist: Package manager version is primary for update/pkg operations
        return pkg_clean, source
        
    if pkg_clean:
        return pkg_clean, source
        
    if bin_clean:
        return bin_clean, "BINARY"
        
    return None, "UNKNOWN"

def compare_canonical_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings v1 and v2.
    Returns:
         1 if v1 > v2
         0 if v1 == v2
        -1 if v1 < v2
        
    Handles suffix matching for binary vs package formats if needed.
    """
    if not v1 or not v2:
        raise ValueError(f"Cannot compare empty versions: v1={v1}, v2={v2}")
        
    c1 = clean_version_string(v1) or v1.strip()
    c2 = clean_version_string(v2) or v2.strip()
    
    if c1 == c2:
        return 0
        
    t1 = parse_version_tuple(c1)
    t2 = parse_version_tuple(c2)
    
    # Check suffix matching if lengths differ (e.g. Chromium base 152.1.94.121 vs 1.94.121 or 1.96.61)
    if len(t1) > len(t2) and t1[0] >= 100 and t2[0] < 100:
        t1 = t1[-len(t2):]
    elif len(t2) > len(t1) and t2[0] >= 100 and t1[0] < 100:
        t2 = t2[-len(t1):]
    elif len(t1) > len(t2) and t1[-len(t2):] == t2:
        return 0
    elif len(t2) > len(t1) and t2[-len(t1):] == t1:
        return 0

    if t1 > t2:
        return 1
    elif t1 < t2:
        return -1
    else:
        return 0

def is_newer_version(candidate: str, current: str) -> bool:
    """
    Returns True if candidate version is strictly newer than current version.
    """
    return compare_canonical_versions(candidate, current) > 0


def app_matches(name1: Optional[str], name2: Optional[str]) -> bool:
    """
    Check if two application name references refer to the same application,
    handling spaces vs dashes vs underscores, vendor prefixes ('google-chrome' vs 'chrome'),
    and canonical registry names.
    """
    if not name1 or not name2:
        return False
        
    s1 = str(name1).strip().lower()
    s2 = str(name2).strip().lower()
    if s1 == s2:
        return True
        
    n1 = s1.replace("_", " ").replace("-", " ")
    n2 = s2.replace("_", " ").replace("-", " ")
    if n1 == n2:
        return True
        
    # Check canonical name from ScriptRegistryService
    try:
        from app.services.script_registry_service import ScriptRegistryService
        c1 = ScriptRegistryService.get_canonical_name(s1)
        c2 = ScriptRegistryService.get_canonical_name(s2)
        if c1 and c2 and c1 == c2:
            return True
    except Exception:
        pass
        
    # Check ApplicationProvider matching
    try:
        from app.providers import ApplicationProviderRegistry
        p1 = ApplicationProviderRegistry.get_provider(s1)
        if p1 and p1.matches(s2):
            return True
        p2 = ApplicationProviderRegistry.get_provider(s2)
        if p2 and p2.matches(s1):
            return True
    except Exception:
        pass
        
    return False

