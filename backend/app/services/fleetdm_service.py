import requests

from app.core.logger import logger
from app.core.config import settings


class FleetDMService:

    @staticmethod
    def _get_headers():
        return {
            "Authorization": f"Bearer {settings.FLEET_API_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def find_host(hostname: str):
        logger.info(f"FleetDMService: Finding host '{hostname}'")

        url = f"{settings.FLEET_BASE_URL}/api/v1/fleet/hosts?query={hostname}"

        try:
            response = requests.get(
                url,
                headers=FleetDMService._get_headers(),
                timeout=10,
            )

            logger.info(
                f"FleetDMService: GET {url} -> {response.status_code}"
            )

            logger.debug(response.text)

            response.raise_for_status()

            data = response.json()
            hosts = data.get("hosts", [])

            if not hosts:
                logger.warning(f"Host '{hostname}' not found.")
                return None

            host_id = hosts[0]["id"]

            logger.info(f"FleetDMService: Host ID = {host_id}")

            return host_id

        except requests.exceptions.RequestException:
            logger.exception("FleetDMService: Failed to find host.")
            return None

    @staticmethod
    def get_host_info(hostname: str):
        logger.info(f"FleetDMService: Getting host info for '{hostname}'")

        url = f"{settings.FLEET_BASE_URL}/api/v1/fleet/hosts?query={hostname}"

        try:
            response = requests.get(
                url,
                headers=FleetDMService._get_headers(),
                timeout=10,
            )

            logger.info(
                f"FleetDMService: GET {url} -> {response.status_code}"
            )

            response.raise_for_status()

            data = response.json()
            hosts = data.get("hosts", [])

            if not hosts:
                logger.warning(f"Host '{hostname}' not found.")
                return None

            host_info = hosts[0]
            logger.info(f"FleetDMService: Host Info retrieved for {host_info.get('id')}")

            return host_info

        except requests.exceptions.RequestException:
            logger.exception("FleetDMService: Failed to get host info.")
            return None

    @staticmethod
    def get_host_by_id(host_id: int):
        logger.info(f"FleetDMService: Getting host info for ID '{host_id}'")

        url = f"{settings.FLEET_BASE_URL}/api/v1/fleet/hosts/{host_id}"

        try:
            response = requests.get(
                url,
                headers=FleetDMService._get_headers(),
                timeout=10,
            )

            logger.info(
                f"FleetDMService: GET {url} -> {response.status_code}"
            )

            response.raise_for_status()

            data = response.json()
            host = data.get("host")

            if not host:
                logger.warning(f"Host ID '{host_id}' not found.")
                return None

            logger.info(f"FleetDMService: Host Info retrieved for {host.get('id')}")

            return host

        except requests.exceptions.RequestException:
            logger.exception("FleetDMService: Failed to get host info by ID.")
            return None

    @staticmethod
    def list_scripts():
        logger.info("FleetDMService: Listing scripts")

        url = f"{settings.FLEET_BASE_URL}/api/v1/fleet/scripts"

        try:
            response = requests.get(
                url,
                headers=FleetDMService._get_headers(),
                timeout=10,
            )

            logger.info(
                f"FleetDMService: GET {url} -> {response.status_code}"
            )

            response.raise_for_status()

            return response.json().get("scripts", [])

        except requests.exceptions.RequestException:
            logger.exception("FleetDMService: Failed to list scripts.")
            return []

    @staticmethod
    def upload_script(path: str):
        logger.info(f"Uploading script: {path}")

        url = f"{settings.FLEET_BASE_URL}/api/v1/fleet/scripts"

        headers = {
            "Authorization": f"Bearer {settings.FLEET_API_TOKEN}"
        }

        try:
            with open(path, "rb") as f:
                files = {
                    "script": f
                }

                response = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    timeout=30,
                )

            logger.info(
                f"FleetDMService: POST {url} -> {response.status_code}"
            )

            logger.debug(response.text)

            response.raise_for_status()

            return response.json()

        except Exception:
            logger.exception("FleetDMService: Failed to upload script.")
            return None

    @staticmethod
    def run_script(host_id, script_id):
        url = f"{settings.FLEET_BASE_URL}/api/v1/fleet/scripts/run"

        payload = {
            "host_id": int(host_id),
            "script_id": int(script_id),
        }

        logger.info("=" * 60)
        logger.info("FleetDM RUN SCRIPT")
        logger.info(f"URL: {url}")
        logger.info(f"Payload: {payload}")

        response = requests.post(
            url,
            headers=FleetDMService._get_headers(),
            json=payload,
            timeout=15,
        )

        logger.info(f"Status Code: {response.status_code}")
        logger.info(f"Response Body: {response.text}")
        logger.info("=" * 60)

        response.raise_for_status()

        return response.json()

    @staticmethod
    def get_script_result(execution_id: str):
        logger.info(
            f"FleetDMService: Getting result for {execution_id}"
        )

        url = (
            f"{settings.FLEET_BASE_URL}"
            f"/api/v1/fleet/scripts/results/{execution_id}"
        )

        try:
            response = requests.get(
                url,
                headers=FleetDMService._get_headers(),
                timeout=10,
            )

            logger.info(
                f"FleetDMService: GET {url} -> {response.status_code}"
            )

            logger.debug(response.text)

            response.raise_for_status()

            logger.info("=" * 60)
            logger.info(f"FleetDM Result: {response.json()}")
            logger.info("=" * 60)

            return response.json()

        except requests.exceptions.RequestException:
            logger.exception(
                "FleetDMService: Failed to fetch execution result."
            )

            return None

    @staticmethod
    def delete_script(script_id: int):
        logger.info(f"FleetDMService: Deleting script ID {script_id}")

        url = f"{settings.FLEET_BASE_URL}/api/v1/fleet/scripts/{script_id}"

        try:
            response = requests.delete(
                url,
                headers=FleetDMService._get_headers(),
                timeout=10,
            )

            logger.info(
                f"FleetDMService: DELETE {url} -> {response.status_code}"
            )

            # Handle success or acceptable already-deleted responses
            if response.status_code in [200, 202, 204, 404]:
                if response.status_code == 404:
                    logger.info(f"FleetDMService: Script ID {script_id} not found (already deleted?)")
                else:
                    logger.info(f"FleetDMService: Script ID {script_id} successfully deleted")
                return True

            logger.error(f"FleetDMService: Unexpected response deleting script ID {script_id}: {response.text}")
            response.raise_for_status()

        except requests.exceptions.RequestException as e:
            logger.exception(f"FleetDMService: Failed to delete script ID {script_id}: {e}")
            return False