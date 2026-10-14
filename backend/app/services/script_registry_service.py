import os
import datetime
from sqlalchemy.orm import Session
from app.database.database import SessionLocal
from app.database.models.script_registry import ScriptRegistry
from app.core.logger import logger

import re

class ScriptRegistryService:
    
    @staticmethod
    def normalize_application_name(application_name: str) -> str:
        """Convert 'Brave Browser' to 'brave_browser', remove unsafe characters."""
        s = str(application_name).strip().lower()
        s = re.sub(r'[^a-z0-9]+', '_', s)
        return s.strip('_')

    @staticmethod
    def _get_name_candidates(application_name: str) -> list:
        norm = ScriptRegistryService.normalize_application_name(application_name)
        candidates = {norm, norm.replace('_', ''), norm.replace('_', '-')}
        for suffix in ('_browser', '_desktop', '_stable', '_client', '_community'):
            if norm.endswith(suffix):
                candidates.add(norm[:-len(suffix)])
        for prefix in ('google_', 'mozilla_', 'microsoft_'):
            if norm.startswith(prefix):
                candidates.add(norm[len(prefix):])
        if 'code' in norm or 'visual_studio' in norm or 'vs' in norm:
            candidates.add('vscode')
            candidates.add('code')
        return [c for c in candidates if c]

    @staticmethod
    def get_canonical_name(application_name: str) -> str:
        """
        Resolves a user-provided application name to its normalized identity.
        """
        candidates = ScriptRegistryService._get_name_candidates(application_name)
        return candidates[0] if candidates else ScriptRegistryService.normalize_application_name(application_name)
        
    @staticmethod
    def generate_filename(application_name: str, version: str, script_type: str) -> str:
        """Generate a filesystem-safe filename like 'brave_1.82.165.sh'."""
        norm_app = ScriptRegistryService.normalize_application_name(application_name)
        norm_ver = re.sub(r'[^a-zA-Z0-9.\-_]+', '_', str(version))
        ext = script_type.lstrip('.')
        if not ext: ext = 'sh'
        return f"{norm_app}_{norm_ver}.{ext}"

    @staticmethod
    def _get_local_mirror_path(operating_system: str, normalized_app: str, filename: str) -> str:
        base_dir = os.path.join(os.getcwd(), "scripts")
        os_dir = os.path.join(base_dir, operating_system.lower())
        app_dir = os.path.join(os_dir, normalized_app)
        return os.path.join(app_dir, filename)

    @staticmethod
    def write_local_mirror(operating_system: str, normalized_app: str, filename: str, script_content: str):
        filepath = ScriptRegistryService._get_local_mirror_path(operating_system, normalized_app, filename)
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w') as f:
                f.write(script_content)
            # Make .sh files executable
            if filename.endswith('.sh'):
                os.chmod(filepath, 0o755)
            logger.info(f"[ScriptRegistry] Saved local mirror to: {filepath}")
        except Exception as e:
            logger.error(f"[ScriptRegistry] Failed to write local mirror at {filepath}: {e}")

    @staticmethod
    def remove_local_mirror(operating_system: str, normalized_app: str, filename: str):
        filepath = ScriptRegistryService._get_local_mirror_path(operating_system, normalized_app, filename)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"[ScriptRegistry] Removed local mirror: {filepath}")
        except Exception as e:
            logger.error(f"[ScriptRegistry] Failed to remove local mirror at {filepath}: {e}")

    @staticmethod
    def find_compatible_script(application_name: str, version: str, operating_system: str, architecture: str):
        """Exact-version lookup. Returns None if not found."""
        candidates = ScriptRegistryService._get_name_candidates(application_name)

        logger.info(
            f"[ScriptResolver] DB query: candidates IN {candidates}, "
            f"version={repr(version)}, os={repr(operating_system)}, arch={repr(architecture)}"
        )

        db: Session = SessionLocal()
        try:
            script = db.query(ScriptRegistry).filter(
                ScriptRegistry.normalized_application_name.in_(candidates),
                ScriptRegistry.version == version,
                ScriptRegistry.operating_system == operating_system,
                ScriptRegistry.architecture == architecture,
                ScriptRegistry.status == "ACTIVE"
            ).first()

            if script:
                logger.info(f"[ScriptResolver] Exact-version match: {script.filename} (ID={script.registry_id})")
            else:
                logger.info(f"[ScriptResolver] No exact-version match for {repr(version)}.")

            return script
        finally:
            db.close()

    @staticmethod
    def find_latest_compatible_script(application_name: str, operating_system: str, architecture: str):
        """Returns the newest ACTIVE script for the application regardless of version."""
        candidates = ScriptRegistryService._get_name_candidates(application_name)

        db: Session = SessionLocal()
        try:
            script = db.query(ScriptRegistry).filter(
                ScriptRegistry.normalized_application_name.in_(candidates),
                ScriptRegistry.operating_system == operating_system,
                ScriptRegistry.architecture == architecture,
                ScriptRegistry.status == "ACTIVE"
            ).order_by(ScriptRegistry.created_at.desc()).first()

            if script:
                logger.info(
                    f"[ScriptResolver] Latest-version match: {script.filename} "
                    f"(version={script.version}, ID={script.registry_id})"
                )
            else:
                logger.info(
                    f"[ScriptResolver] No ACTIVE script found for {candidates} "
                    f"on {operating_system}/{architecture}."
                )

            return script
        finally:
            db.close()

    @staticmethod
    def resolve_script(application_name: str, version: str, operating_system: str, architecture: str):
        """
        Authoritative script resolution for the current application.

        Resolution order:
        1. Exact version match in PostgreSQL.
        2. If version is 'latest' or falsy: newest ACTIVE script by created_at.

        Does NOT touch the local filesystem — only PostgreSQL + FleetDM script ID.
        """
        norm_app = ScriptRegistryService.normalize_application_name(application_name)
        canonical_name = ScriptRegistryService.get_canonical_name(application_name)

        logger.info(
            f"[ScriptResolver] Resolving: app={repr(application_name)} "
            f"canonical={repr(canonical_name)} version={repr(version)} "
            f"os={operating_system} arch={architecture}"
        )

        # Step 1: exact version match
        if version and version.lower() not in ("latest", ""):
            script = ScriptRegistryService.find_compatible_script(
                application_name, version, operating_system, architecture
            )
            if script:
                return script
            logger.info(f"[ScriptResolver] No compatible script in registry matching exact version {version}.")
            return None

        # Step 2: latest-version fallback (used when version='latest' or falsy)
        logger.info(f"[ScriptResolver] Falling back to latest-version lookup...")
        return ScriptRegistryService.find_latest_compatible_script(
            application_name, operating_system, architecture
        )

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
        risk_reasons: list,
        script_type: str,
        script_content: str
    ):
        normalized_app = ScriptRegistryService.get_canonical_name(application_name)
        filename = ScriptRegistryService.generate_filename(application_name, version, script_type)
        
        db: Session = SessionLocal()
        try:
            new_script = ScriptRegistry(
                application_name=application_name,
                normalized_application_name=normalized_app,
                version=version,
                operating_system=operating_system,
                architecture=architecture,
                filename=filename,
                script_type=script_type,
                script_content=script_content,
                fleet_script_id=fleet_script_id,
                script_hash=script_hash,
                risk_score=risk_score,
                risk_level=risk_level,
                risk_reasons=risk_reasons,
                status="ACTIVE",
                success_count=1
            )
            db.add(new_script)
            db.commit()
            db.refresh(new_script)
            
            # Write to local mirror
            ScriptRegistryService.write_local_mirror(operating_system, normalized_app, filename, script_content)
            
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
                    if script.success_count is None:
                        script.success_count = 0
                    script.success_count += 1
                else:
                    if script.failure_count is None:
                        script.failure_count = 0
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
                logger.info(f"[ScriptRegistry] Marked script {registry_id} ({script.filename}) as INVALID.")
                # Remove local mirror
                if script.filename and script.normalized_application_name:
                    ScriptRegistryService.remove_local_mirror(script.operating_system, script.normalized_application_name, script.filename)
        finally:
            db.close()


    @staticmethod
    def invalidate_old_versions(application_name: str, current_version: str, operating_system: str, architecture: str) -> list[int]:
        """
        NO-OP: Historical versioned scripts are preserved.

        Each version of a script (e.g., brave_browser_1.95.101.sh,
        brave_browser_1.96.xxx.sh) has its own ACTIVE DB row and can be
        independently reused for the matching version request.

        Deleting old scripts would destroy the ability to reinstall known-good
        versions. New version = new DB row. Old rows remain ACTIVE.
        """
        logger.info(
            f"[ScriptRegistry] invalidate_old_versions called for {application_name} "
            f"v{current_version} — SKIPPED (historical scripts are preserved)."
        )
        return []
