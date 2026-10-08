import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.tasks.installation_tasks import resume_approved_update

def run():
    approval_id = "aaefeb37-60b1-4587-b34b-3489c12441a9"
    # Delay sending to celery worker
    task = resume_approved_update.delay(approval_id)
    print(f"Queued resume task: {task.id}")

if __name__ == "__main__":
    run()
