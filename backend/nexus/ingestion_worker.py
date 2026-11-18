"""Dedicated intake worker: python -m nexus.ingestion_worker.
For production separation, set NEXUS_INGESTION_IN_ACTION_WORKER=0 on business
workers and deploy this process with reviewed memory/CPU/network controls.
"""
import time
from .config import Settings
from .db import database
from .ingestion import run_ingestion_once

def main():
    settings=Settings.from_env();settings.validate();engine,factory=database(settings.database_url)
    print('NEXUS document intake worker started. Private extraction requires review before publication.',flush=True)
    try:
        while True:
            try:
                if not run_ingestion_once(factory,settings):time.sleep(1)
            except KeyboardInterrupt:break
            except Exception:
                print('Intake worker unavailable; persisted jobs remain protected.',flush=True);time.sleep(3)
    finally:engine.dispose()

if __name__=='__main__':main()
