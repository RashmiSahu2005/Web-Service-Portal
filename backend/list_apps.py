import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.database import SessionLocal
from app.database.models import Application

db = SessionLocal()
apps = db.query(Application).all()
for app in apps:
    print(f"{app.id} | {app.name}")
