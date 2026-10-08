from app.core.config import settings

class BatteryService:
    @staticmethod
    def get_current_battery_level() -> int:
        return settings.MOCK_BATTERY_LEVEL
