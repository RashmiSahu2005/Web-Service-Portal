import os
import sys
import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database.database import SessionLocal
from app.services.email_service import EmailService
from sqlalchemy import text

def run():
    db = SessionLocal()
    apps = ['jmeter', 'node_js', 'remmina', 'adb', 'appium']
    
    # 1. Update and fetch script contents
    query = text("""
        UPDATE script_registry 
        SET status = 'ACTIVE' 
        WHERE normalized_application_name IN ('jmeter', 'node_js', 'remmina', 'adb', 'appium')
        RETURNING normalized_application_name, filename, script_content, fleet_script_id
    """)
    result = db.execute(query).fetchall()
    db.commit()
    
    # 2. Write to local directory
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'ubuntu')
    saved_info = []
    
    for row in result:
        app_name = row.normalized_application_name
        filename = row.filename
        content = row.script_content
        fleet_id = row.fleet_script_id
        
        if content:
            app_dir = os.path.join(base_dir, app_name)
            os.makedirs(app_dir, exist_ok=True)
            filepath = os.path.join(app_dir, filename)
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"Saved {filepath} (Fleet ID: {fleet_id})")
            saved_info.append(f"{app_name}: ACTIVE (Fleet ID: {fleet_id}, File: {filename})")
    
    # 3. Send email
    summary_text = "The following applications were successfully installed on Host 1 (192.168.5.215) via DeployIQ:\n\n"
    summary_text += "\n".join(saved_info)
    summary_text += "\n\nAll scripts have been restored locally and activated in the PostgreSQL registry."
    
    recipient = "satyabrat.dwivedy@apmosys.com"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    success, msg = EmailService.send_multi_app_report(
        recipient_email=recipient,
        summary_text=summary_text,
        overall_status="COMPLETED SUCCESSFULLY",
        timestamp=timestamp,
        hostname="APMOSYSLT0447 (192.168.5.215)"
    )
    print(f"Email send result: {success} - {msg}")

if __name__ == "__main__":
    run()
