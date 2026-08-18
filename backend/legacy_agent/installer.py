from abc import ABC, abstractmethod
import subprocess
import time
from agent.job_listener import send_log, update_status
from agent.logger import get_logger

logger = get_logger("installer")

class BaseInstaller(ABC):
    @abstractmethod
    def install(self, job) -> bool:
        pass

class DebInstaller(BaseInstaller):
    def install(self, job) -> bool:
        job_id = job["job_id"]
        package_path = job.get("package_path", "")
        
        command_template = job.get("install_command", "sudo dpkg -i {package}")
        
        command = command_template.replace("{package}", package_path)
        send_log(job_id, f"Executing: {command}")
        update_status(job_id, "INSTALLING", "Installation", 70)
        
        try:
            process = subprocess.Popen(
                command, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in process.stdout:
                line = line.strip()
                if line:
                    send_log(job_id, line)
                    logger.info(f"[{job_id}] {line}")
            
            process.wait()
            
            if process.returncode != 0:
                send_log(job_id, f"Installation failed with exit code {process.returncode}")
                return False
                
            send_log(job_id, "Installation completed successfully.")
            return True
            
        except Exception as e:
            send_log(job_id, f"Failed to execute installer: {str(e)}")
            logger.error(f"Exception in installer: {e}")
            return False

def get_installer(installer_type: str) -> BaseInstaller:
    if installer_type == "deb" or installer_type == "apt":
        return DebInstaller()
    return DebInstaller()
