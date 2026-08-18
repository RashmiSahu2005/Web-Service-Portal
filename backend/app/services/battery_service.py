import random

class BatteryService:
    @staticmethod
    def get_current_battery_level() -> int:
        # Simulate reading battery level from OS
        # Hardcoded to 100% for MVP so it doesn't randomly fail installations
        return 100
