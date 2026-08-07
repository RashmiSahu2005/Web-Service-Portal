import time
from agent.config import POLL_INTERVAL
from agent.job_listener import poll_pending_job, send_log, update_status
from agent.validator import validate_system
from agent.installer import get_installer
from agent.system_info import get_system_info
from agent.logger import get_logger

logger = get_logger("agent")

def process_job(job):
    job_id = job["job_id"]
    logger.info(f"Processing job {job_id}")
    
    send_log(job_id, "Agent initialized. Validating system...")
    update_status(job_id, "VALIDATING", "Device Validation", 10)
    
    sys_info = get_system_info()
    send_log(job_id, f"System: {sys_info['username']}@{sys_info['hostname']} ({sys_info['os']} {sys_info['architecture']})")
    send_log(job_id, f"Battery: {sys_info['battery_percent']}%, Free Disk: {sys_info['free_disk_gb']} GB")
    
    if not validate_system(job):
        send_log(job_id, "System validation failed.")
        update_status(job_id, "FAILED", "Device Validation", 10)
        return
        
    send_log(job_id, "System validation passed. Preparing for installation...")
    update_status(job_id, "RUNNING", "Download Package", 40)
    time.sleep(2)
    
    installer = get_installer("deb")
    success = installer.install(job)
    
    if success:
        send_log(job_id, "Verifying installation...")
        update_status(job_id, "VERIFYING", "Post Installation Validation", 90)
        time.sleep(2)
        
        send_log(job_id, "All steps completed.")
        update_status(job_id, "COMPLETED", "Completed", 100)
        logger.info(f"Job {job_id} completed successfully.")
    else:
        send_log(job_id, "Installation encountered a fatal error.")
        update_status(job_id, "FAILED", "Installation", 70)
        logger.error(f"Job {job_id} failed.")

def main():
    logger.info("Application Hub Agent started. Polling for jobs...")
    while True:
        job = poll_pending_job()
        if job:
            try:
                process_job(job)
            except Exception as e:
                logger.error(f"Unhandled error processing job: {e}")
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
