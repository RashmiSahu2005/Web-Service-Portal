from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, BackgroundTasks
from typing import Dict, List, Any, Optional
import uuid
from sqlalchemy.orm import Session
from app.schemas.installation import InstallationStatusResponse
from app.database.database import get_db, SessionLocal
from app.services.application_service import ApplicationService
from app.database.repositories.job_repository import job_repo, log_repo
from app.database.models.job import InstallationJob, InstallationLog
from app.services.fleetdm_service import FleetDMService
from app.services.email_service import EmailService
from pydantic import BaseModel
import asyncio
from datetime import datetime
from app.core.config import settings
from app.core.logger import logger
import socket

router = APIRouter()

class InstallResponse(BaseModel):
    installation_id: str

class LogPayload(BaseModel):
    message: str

class StatusPayload(BaseModel):
    status: str
    step: str
    percentage: int

class IdentifyHostRequest(BaseModel):
    ip_address: str

class IdentifyHostResponse(BaseModel):
    host_id: int
    hostname: str
    ip_address: str
    operating_system: str
    os_version: str
    architecture: str

class StartInstallRequest(BaseModel):
    host_id: Optional[str] = None

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str):
        if job_id in self.active_connections:
            self.active_connections[job_id].remove(websocket)

    async def broadcast_log(self, job_id: str, log_line: str):
        if job_id in self.active_connections:
            for connection in self.active_connections[job_id]:
                await connection.send_json({"type": "log", "message": log_line})

    async def broadcast_status(self, job_id: str, status: str, step: str, percentage: int):
        if job_id in self.active_connections:
            for connection in self.active_connections[job_id]:
                await connection.send_json({
                    "type": "status",
                    "status": status,
                    "step": step,
                    "percentage": percentage
                })

ws_manager = ConnectionManager()
readiness_cache: Dict[str, dict] = {}

async def simulate_installation_progress(job_id: str):
    await asyncio.sleep(1)
    db = SessionLocal()
    try:
        job = job_repo.get(db, job_id)
        if job:
            job_repo.update(db, db_obj=job, obj_in={"status": "RUNNING"})

        app_name = "Unknown Application"
        recipient_email = "rashmi.sahu@ap2l.ai" # Default for testing
        if job:
            app = ApplicationService.get_application(db, job.application_id)
            if app:
                app_name = app.name

        # List of all UI steps
        steps = [
            'Request Received',
            'User Validation',
            'Device Validation',
            'Battery Validation',
            'Disk Validation',
            'Dependency Validation',
            'Package Validation',
            'Download Package',
            'Verify Checksum',
            'Installation',
            'Post Installation Validation'
        ]

        total_steps = len(steps) + 2 # +2 for Email and Completed

        for i, step in enumerate(steps):
            percentage = int(((i + 1) / total_steps) * 100)
            await ws_manager.broadcast_status(job_id, "RUNNING", step, percentage)
            await ws_manager.broadcast_log(job_id, f"Executing: {step}...")
            await asyncio.sleep(0.5)

        # Email Notification Step
        step = 'Email Notification'
        percentage = int(((len(steps) + 1) / total_steps) * 100)
        await ws_manager.broadcast_status(job_id, "RUNNING", step, percentage)
        await ws_manager.broadcast_log(job_id, f"Executing: {step}...")
        
        email_success, email_msg = EmailService.send_installation_success(
            recipient_email=recipient_email,
            application_name=app_name,
            status="COMPLETED",
            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            hostname="local"
        )
        await ws_manager.broadcast_log(job_id, email_msg)
        
        await asyncio.sleep(0.5)

        # Completed Step
        if job:
            job_repo.update(db, db_obj=job, obj_in={"status": "COMPLETED"})
        await ws_manager.broadcast_status(job_id, "COMPLETED", "Completed", 100)
        await ws_manager.broadcast_log(job_id, "Installation completed successfully.")
        log_repo.create(db, obj_in={"job_id": job_id, "message": "Installation completed successfully."})
        
        
        # Clean up cache
        if job_id in readiness_cache:
            del readiness_cache[job_id]
            
    finally:
        db.close()

async def fleetdm_polling_progress(job_id: str, execution_id: str, app_name: str, recipient_email: str, hostname: str):
    db = SessionLocal()
    try:
        job = job_repo.get(db, job_id)
        if job:
            job_repo.update(db, db_obj=job, obj_in={"status": "RUNNING"})
            
        await ws_manager.broadcast_status(job_id, "RUNNING", "Installation", 50)
        await ws_manager.broadcast_log(job_id, f"Polling FleetDM for execution {execution_id}...")
        
        while True:
            await asyncio.sleep(settings.POLLING_INTERVAL)
            result = FleetDMService.get_script_result(execution_id)
            
            if not result:
                await ws_manager.broadcast_log(job_id, "Failed to get script result from FleetDM.")
                if job: job_repo.update(db, db_obj=job, obj_in={"status": "FAILED"})
                await ws_manager.broadcast_status(job_id, "FAILED", "Completed", 100)
                break
                
            exit_code = result.get("exit_code")
            output = result.get("output", "")
            
            # Broadcast output if not empty
            if output:
                await ws_manager.broadcast_log(job_id, output)
                
            if exit_code is not None or result.get("host_timeout"):
                if exit_code == 0:
                    status = "COMPLETED"
                else:
                    status = "FAILED"
                    
                if job: job_repo.update(db, db_obj=job, obj_in={"status": status})
                
                await ws_manager.broadcast_status(job_id, status, "Completed", 100)
                await ws_manager.broadcast_log(job_id, f"Script execution finished with exit code {exit_code}.")
                log_repo.create(db, obj_in={"job_id": job_id, "message": f"Execution finished with exit code {exit_code}. Output: {output}"})
                
                step = 'Email Notification'
                await ws_manager.broadcast_status(job_id, status, step, 100)
                await ws_manager.broadcast_log(job_id, f"Executing: {step}...")
                
                if status == "COMPLETED":
                    email_success, email_msg = EmailService.send_installation_success(
                        recipient_email=recipient_email,
                        application_name=app_name,
                        status="COMPLETED",
                        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                        hostname=hostname
                    )
                else:
                    email_success, email_msg = EmailService.send_installation_failure(
                        recipient_email=recipient_email,
                        application_name=app_name,
                        status="FAILED",
                        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                        hostname=hostname,
                        reason=f"Exit code: {exit_code}"
                    )
                await ws_manager.broadcast_log(job_id, email_msg)
                break
                
    except Exception as e:
        logger.error(f"Error in fleetdm_polling_progress: {e}")
    finally:
        # Clean up cache
        if job_id in readiness_cache:
            del readiness_cache[job_id]
        db.close()

@router.post("/hosts/identify", response_model=IdentifyHostResponse)
async def identify_host(req: IdentifyHostRequest):
    if not settings.USE_FLEETDM:
        return IdentifyHostResponse(
            host_id=191,
            hostname="mocked-host",
            ip_address=req.ip_address,
            operating_system="Windows",
            os_version="11",
            architecture="x64"
        )
        
    host_info = FleetDMService.get_host_info(req.ip_address)
    if not host_info:
        raise HTTPException(status_code=404, detail=f"Host with IP {req.ip_address} not found in FleetDM.")
        
    platform = host_info.get("platform", "unknown")
    cpu_type = host_info.get("cpu_type", "unknown")
    
    if cpu_type in ["x86_64", "amd64"]:
        arch = "amd64"
    elif cpu_type in ["arm64", "aarch64"]:
        arch = "arm64"
    else:
        arch = cpu_type
        
    if platform == "ubuntu" or platform == "debian":
        os_name = "Ubuntu"
    elif platform == "windows":
        os_name = "Windows"
        arch = "x64" if arch == "amd64" else arch
    elif platform == "darwin":
        os_name = "macOS"
    else:
        os_name = platform.capitalize()

    return IdentifyHostResponse(
        host_id=host_info.get("id"),
        hostname=host_info.get("hostname", "unknown"),
        ip_address=req.ip_address,
        operating_system=os_name,
        os_version=host_info.get("os_version", "unknown"),
        architecture=arch
    )

@router.post("/install/{application_id}", response_model=InstallResponse)
async def request_installation(application_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    app = ApplicationService.get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    job_id = f"job_{str(uuid.uuid4())[:8]}"
    
    if settings.USE_FLEETDM:
        hostname = socket.gethostname()
        host_info = FleetDMService.get_host_info(hostname)
        if not host_info:
            raise HTTPException(status_code=500, detail=f"FleetDM Host '{hostname}' not found.")
            
        host_id = host_info.get("id")
        
        battery_level = 100
        if "batteries" in host_info and host_info["batteries"]:
            battery_level = host_info["batteries"][0].get("percent", 100)
            
        min_battery = app.minimum_battery_percentage or 30
        
        device_readiness = {
            "battery": battery_level,
            "network": "Connected" if host_info.get("status") == "online" else "Offline",
            "minimum_battery": min_battery
        }
        
        readiness_cache[job_id] = device_readiness
        
        if battery_level < min_battery:
            job_data = {
                "id": job_id,
                "application_id": application_id,
                "host_id": str(host_id),
                "status": "FAILED"
            }
            job_repo.create(db, obj_in=job_data)
            log_repo.create(db, obj_in={"job_id": job_id, "message": f"Battery level is below the required threshold."})
    job_data = {
        "id": job_id,
        "application_id": application_id,
        "host_id": "dynamic" if settings.USE_FLEETDM else "local",
        "status": "PENDING"
    }
    job_repo.create(db, obj_in=job_data)
    
    return InstallResponse(installation_id=job_id)

from app.services.queue_service import QueueService

@router.post("/install/{job_id}/start")
async def start_installation(job_id: str, request: StartInstallRequest = None, db: Session = Depends(get_db)):
    job = job_repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status != "PENDING":
        return {"status": "Already started or cancelled"}
        
    app = ApplicationService.get_application(db, job.application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    # Change state to QUEUED and update host_id if explicitly requested
    update_data = {"status": "QUEUED"}
    if request and request.host_id:
        update_data["host_id"] = request.host_id
        
    job_repo.update(db, db_obj=job, obj_in=update_data)
    
    # Refresh job to ensure we have the latest host_id
    job = job_repo.get(db, job_id)
    
    # Start the Celery execution
    QueueService.enqueue_installation(
        job_id=job_id,
        application_name=app.name,
        version=app.version or "Latest",
        host_ids=[1] # simplified
    )
    
    return {"status": "QUEUED", "job_id": job_id, "message": "Installation job queued successfully"}

@router.post("/install/{job_id}/cancel")
async def cancel_installation(job_id: str, db: Session = Depends(get_db)):
    job = job_repo.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status not in ["COMPLETED", "FAILED"]:
        job_repo.update(db, db_obj=job, obj_in={"status": "CANCELLED"})
        log_repo.create(db, obj_in={"job_id": job_id, "message": "Installation cancelled by user."})
        return {"status": "cancelled"}
    return {"status": "too_late"}

@router.get("/install/{installation_id}", response_model=InstallationStatusResponse)
def get_installation_status(installation_id: str, db: Session = Depends(get_db)):
    job = job_repo.get(db, installation_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    logs = log_repo.get_by_job_id(db, installation_id)
    log_messages = [log.message for log in logs]
    
    device_readiness = readiness_cache.get(installation_id)
    
    return InstallationStatusResponse(
        step="Installation",
        status=job.status,
        percentage=0 if job.status == "PENDING" else 100,
        message=f"Job is {job.status}",
        logs=log_messages,
        estimated_time="Unknown",
        device_readiness=device_readiness
    )

# ----------------------------------------------------
# Agent Endpoints
# ----------------------------------------------------
@router.get("/jobs/pending")
def get_pending_job(db: Session = Depends(get_db)):
    jobs = job_repo.get_all(db)
    pending = [j for j in jobs if j.status == "PENDING"]
    if not pending:
        raise HTTPException(status_code=404, detail="No pending jobs")
    job = pending[0]
    app = ApplicationService.get_application(db, job.application_id)
    return {
        "job_id": job.id,
        "application_id": job.application_id,
        "install_command": app.install_command if app else "",
        "package_path": app.package_path if app else "",
        "minimum_battery": app.minimum_battery_percentage if app else 0
    }

@router.post("/jobs/{job_id}/logs")
async def append_job_log(job_id: str, payload: LogPayload, db: Session = Depends(get_db)):
    log_repo.create(db, obj_in={"job_id": job_id, "message": payload.message})
    await ws_manager.broadcast_log(job_id, payload.message)
    return {"status": "success"}

@router.post("/jobs/{job_id}/status")
async def update_job_status(job_id: str, payload: StatusPayload, db: Session = Depends(get_db)):
    job = job_repo.get(db, job_id)
    if job:
        job_repo.update(db, db_obj=job, obj_in={"status": payload.status})
    await ws_manager.broadcast_status(job_id, payload.status, payload.step, payload.percentage)
    return {"status": "success"}

@router.get("/jobs/{job_id}", response_model=InstallationStatusResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    return get_installation_status(job_id, db)

# ----------------------------------------------------
# WebSocket Endpoint
# ----------------------------------------------------
@router.websocket("/ws/installation/{job_id}")
async def websocket_installation_endpoint(websocket: WebSocket, job_id: str):
    await ws_manager.connect(websocket, job_id)
    
    import redis.asyncio as aioredis
    import json
    
    redis_client = await aioredis.from_url("redis://localhost:6379/0")
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"installation_{job_id}")
    
    async def redis_reader():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"].decode("utf-8")
                    # Send to this specific connection
                    try:
                        await websocket.send_text(data)
                    except Exception:
                        break
        except Exception as e:
            logger.error(f"Redis reader error: {e}")

    task = asyncio.create_task(redis_reader())
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, job_id)
        task.cancel()
        await pubsub.unsubscribe(f"installation_{job_id}")
        await redis_client.close()
