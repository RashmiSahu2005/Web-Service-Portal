import datetime
import hashlib
import json
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.database.models.application_strategy import ApplicationStrategy

class ApplicationStrategyService:
    @staticmethod
    def get_strategy(application_name: str, operating_system: str, os_version: str, architecture: str):
        db: Session = SessionLocal()
        try:
            # We look for a strategy matching app, os, arch. os_version can be a fuzzy match or exact, 
            # for now let's just match os and arch for broader compatibility if os_version varies slightly,
            # or match exactly if required.
            strategy = db.query(ApplicationStrategy).filter(
                ApplicationStrategy.application_name == application_name,
                ApplicationStrategy.operating_system == operating_system,
                ApplicationStrategy.architecture == architecture,
                ApplicationStrategy.strategy_status == "ACTIVE"
            ).first()
            return strategy
        finally:
            db.close()

    @staticmethod
    def save_strategy(
        application_name: str,
        operating_system: str,
        os_version: str,
        architecture: str,
        package_manager: str,
        package_name: str,
        installation_method: str,
        installed_version_command: list,
        latest_version_command: list,
        latest_version_source: str,
        verification_command: list
    ):
        db: Session = SessionLocal()
        try:
            # Generate a hash for the strategy based on key attributes to avoid duplicates
            hash_input = json.dumps({
                "app": application_name,
                "os": operating_system,
                "arch": architecture,
                "pkg_mgr": package_manager,
                "install_method": installation_method,
                "installed_cmd": installed_version_command,
                "latest_cmd": latest_version_command
            }, sort_keys=True)
            strategy_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            # Check if this strategy hash already exists
            existing = db.query(ApplicationStrategy).filter(
                ApplicationStrategy.strategy_hash == strategy_hash
            ).first()
            
            if existing:
                return existing

            new_strategy = ApplicationStrategy(
                application_name=application_name,
                operating_system=operating_system,
                os_version=os_version,
                architecture=architecture,
                package_manager=package_manager,
                package_name=package_name,
                installation_method=installation_method,
                installed_version_command=installed_version_command,
                latest_version_command=latest_version_command,
                latest_version_source=latest_version_source,
                verification_command=verification_command,
                strategy_status="ACTIVE",
                strategy_hash=strategy_hash,
                last_validated_at=datetime.datetime.utcnow()
            )
            db.add(new_strategy)
            db.commit()
            db.refresh(new_strategy)
            return new_strategy
        finally:
            db.close()
            
    @staticmethod
    def record_failure(strategy_id: int):
        db: Session = SessionLocal()
        try:
            strategy = db.query(ApplicationStrategy).filter(ApplicationStrategy.strategy_id == strategy_id).first()
            if strategy:
                strategy.failure_count += 1
                if strategy.failure_count >= 3:
                    strategy.strategy_status = "INVALID"
                db.commit()
        finally:
            db.close()
