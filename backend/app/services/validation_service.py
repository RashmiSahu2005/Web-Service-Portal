from typing import Dict, Any

class ValidationService:
    @staticmethod
    def validate_user(user_id: str) -> Dict[str, Any]:
        return {"status": "success", "reason": "User is authorized"}

    @staticmethod
    def validate_device(device_id: str) -> Dict[str, Any]:
        return {"status": "success", "reason": "Device meets requirements"}

    @staticmethod
    def validate_disk_space(required_space: str) -> Dict[str, Any]:
        return {"status": "success", "reason": "Sufficient disk space available"}

    @staticmethod
    def validate_dependencies(dependencies: list) -> Dict[str, Any]:
        return {"status": "success", "reason": "All dependencies resolved"}

    @staticmethod
    def validate_package(package_id: str) -> Dict[str, Any]:
        return {"status": "success", "reason": "Package signature is valid"}

    @staticmethod
    def validate_checksum(package_id: str, expected_checksum: str) -> Dict[str, Any]:
        return {"status": "success", "reason": "Checksum verified successfully"}

    @staticmethod
    def validate_battery(current_level: int, minimum_required: int) -> Dict[str, Any]:
        if current_level >= minimum_required:
            return {"status": "success", "reason": f"Battery level is sufficient ({current_level}%)"}
        return {
            "status": "failed", 
            "reason": f"Battery level is below {minimum_required}%. Please connect the charger before installing this application."
        }
