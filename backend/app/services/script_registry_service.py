import datetime
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.database.models.script_registry import ScriptRegistry

class ScriptRegistryService:

    @staticmethod
    def find_compatible_script(application_name: str, version: str, operating_system: str, architecture: str):
        db: Session = SessionLocal()
        try:
            script = db.query(ScriptRegistry).filter(
                ScriptRegistry.application_name == application_name,
                ScriptRegistry.version == version,
                ScriptRegistry.operating_system == operating_system,
                ScriptRegistry.architecture == architecture,
                ScriptRegistry.status == "ACTIVE"
            ).first()
            return script
        finally:
            db.close()

    @staticmethod
    def save_script(
        application_name: str,
        version: str,
        operating_system: str,
        architecture: str,
        fleet_script_id: str,
        script_hash: str,
        risk_score: int,
        risk_level: str,
        risk_reasons: list
    ):
        db: Session = SessionLocal()
        try:
            new_script = ScriptRegistry(
                application_name=application_name,
                version=version,
                operating_system=operating_system,
                architecture=architecture,
                fleet_script_id=fleet_script_id,
                script_hash=script_hash,
                risk_score=risk_score,
                risk_level=risk_level,
                risk_reasons=risk_reasons,
                status="ACTIVE"
            )
            db.add(new_script)
            db.commit()
            db.refresh(new_script)
            return new_script
        finally:
            db.close()

    @staticmethod
    def update_script_execution(registry_id: int, success: bool):
        db: Session = SessionLocal()
        try:
            script = db.query(ScriptRegistry).filter(ScriptRegistry.registry_id == registry_id).first()
            if script:
                now = datetime.datetime.utcnow()
                script.last_executed_at = now
                if success:
                    script.last_success_at = now
                else:
                    script.failure_count += 1
                db.commit()
        finally:
            db.close()

    @staticmethod
    def invalidate_script(registry_id: int):
        db: Session = SessionLocal()
        try:
            script = db.query(ScriptRegistry).filter(ScriptRegistry.registry_id == registry_id).first()
            if script:
                script.status = "INVALID"
                db.commit()
        finally:
            db.close()
