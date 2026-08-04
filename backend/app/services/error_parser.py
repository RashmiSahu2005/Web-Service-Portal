from enum import Enum

class ErrorType(Enum):
    DISK_FULL = "DISK_FULL"
    PACKAGE_LOCK = "PACKAGE_LOCK"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CHECKSUM_FAILURE = "CHECKSUM_FAILURE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    PERMISSION_FAILURE = "PERMISSION_FAILURE"
    UNKNOWN = "UNKNOWN"

class ErrorParser:
    @staticmethod
    def parse(raw_error: str) -> ErrorType:
        raw_error_lower = raw_error.lower()
        if "no space left on device" in raw_error_lower:
            return ErrorType.DISK_FULL
        if "dpkg frontend lock" in raw_error_lower:
            return ErrorType.PACKAGE_LOCK
        if "connection timed out" in raw_error_lower or "network timeout" in raw_error_lower:
            return ErrorType.NETWORK_TIMEOUT
        if "checksum mismatch" in raw_error_lower:
            return ErrorType.CHECKSUM_FAILURE
        if "dependency not found" in raw_error_lower:
            return ErrorType.DEPENDENCY_FAILURE
        if "permission denied" in raw_error_lower:
            return ErrorType.PERMISSION_FAILURE
        
        return ErrorType.UNKNOWN
