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

@router.post("/hosts/identify", response_model=IdentifyHostResponse)
async def identify_host(req: IdentifyHostRequest):
    if not settings.USE_FLEETDM:
        return IdentifyHostResponse(
            host_id=settings.MOCK_HOST_ID,
            hostname="mocked-host",
            ip_address=req.ip_address,
            operating_system=settings.MOCK_HOST_OS,
            os_version=settings.MOCK_HOST_VERSION,
            architecture=settings.MOCK_HOST_ARCH
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
async def request_installation(application_id: str, background_tasks: BackgroundTasks, host: Optional[str] = None, db: Session = Depends(get_db)):
    app = ApplicationService.get_application(db, application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    job_id = f"job_{str(uuid.uuid4())[:8]}"
    
    if settings.USE_FLEETDM:
        if not host:
            raise HTTPException(status_code=400, detail="Target host must be specified when FleetDM is enabled.")
        host_info = FleetDMService.verify_host_enrolled(host)
        if not host_info:
            raise HTTPException(status_code=400, detail=f"FleetDM Host '{host}' not found or not enrolled.")
            
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

    # Resolve target host strictly
    target_host = request.host_id if request and request.host_id else (job.host_id if job.host_id and job.host_id not in ("dynamic", "local", "none", "null") else None)
    if not target_host and not settings.USE_FLEETDM:
        target_host = str(settings.MOCK_HOST_ID)

    if not target_host:
        raise HTTPException(status_code=400, detail="Missing required host_id. A target host must be specified.")

    # Create and queue the Celery execution via reusable service method
    from app.services.installation_service import InstallationService
    InstallationService.create_and_start_installation(
        db=db,
        application_id=app.id,
        application_name=app.name,
        host_id=target_host,
        version=app.version or "Latest",
        job_id=job_id
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

@router.get("/jobs/{job_id}/events")
async def get_job_events(job_id: str):
    import redis.asyncio as aioredis
    import json
    
    try:
        redis_client = await aioredis.from_url(settings.REDIS_URL)
        events_bytes = await redis_client.lrange(f"installation_history_{job_id}", 0, -1)
        events = [json.loads(e.decode('utf-8')) for e in events_bytes]
        await redis_client.close()
        return {"events": events}
    except Exception as e:
        logger.error(f"Error fetching history for {job_id}: {e}")
        return {"events": []}

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
    
    redis_client = await aioredis.from_url(settings.REDIS_URL)
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
