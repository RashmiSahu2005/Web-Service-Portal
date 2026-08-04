from app.services.error_parser import ErrorType

class RemediationService:
    @staticmethod
    def remediate(error_type: ErrorType) -> str:
        if error_type == ErrorType.DISK_FULL:
            return "Clean Temp Files"
        if error_type == ErrorType.PACKAGE_LOCK:
            return "Wait"
        if error_type == ErrorType.NETWORK_TIMEOUT:
            return "Retry Download"
        if error_type == ErrorType.CHECKSUM_FAILURE:
            return "Download Package Again"
        if error_type == ErrorType.DEPENDENCY_FAILURE:
            return "Install Missing Dependency"
        if error_type == ErrorType.PERMISSION_FAILURE:
            return "Cannot Remediate"
            
        return "Manual Intervention Required"
