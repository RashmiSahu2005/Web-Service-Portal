from agent.system_info import get_system_info
from agent.logger import get_logger

logger = get_logger("validator")

def validate_system(job) -> bool:
    info = get_system_info()
    min_battery = job.get("minimum_battery", 0)
    
    logger.info(f"System Info: {info}")
    
    if info["battery_percent"] < min_battery:
        logger.error(f"Validation FAIL: Battery {info['battery_percent']}% is below minimum {min_battery}%.")
        return False
        
    logger.info("System Validation PASS")
    return True
