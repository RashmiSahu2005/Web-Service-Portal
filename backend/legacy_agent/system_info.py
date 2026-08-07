import platform
import psutil
import getpass
import shutil

def get_system_info():
    uname = platform.uname()
    total, used, free = shutil.disk_usage("/")
    
    battery = psutil.sensors_battery()
    battery_percent = battery.percent if battery else 100
    
    return {
        "username": getpass.getuser(),
        "hostname": uname.node,
        "os": uname.system,
        "kernel": uname.release,
        "architecture": uname.machine,
        "python_version": platform.python_version(),
        "free_disk_gb": round(free / (1024 ** 3), 2),
        "battery_percent": battery_percent
    }
