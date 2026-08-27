import psutil
import time
import threading
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Metric

def background_collector():
    while True:
        try:
            db = SessionLocal()
            
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            timestamp = int(time.time())
            
            new_metric = Metric(
                timestamp=timestamp,
                cpu_percent=cpu,
                ram_percent=ram
            )
            db.add(new_metric)
            db.commit()
            
            # Prune logic: Keep only the last 1440 records
            record_count = db.query(Metric).count()
            if record_count > 1440:
                # Find the ID of the 1440th newest record
                oldest_allowed = db.query(Metric).order_by(Metric.timestamp.desc()).offset(1440).limit(1).first()
                if oldest_allowed:
                    db.query(Metric).filter(Metric.timestamp <= oldest_allowed.timestamp).delete()
                    db.commit()
                    
        except Exception as e:
            print(f"Error in background collector: {e}")
        finally:
            db.close()
            
        time.sleep(60)

def start_history_collector():
    thread = threading.Thread(target=background_collector, daemon=True)
    thread.start()

def get_history(db: Session):
    return db.query(Metric).order_by(Metric.timestamp.asc()).all()
