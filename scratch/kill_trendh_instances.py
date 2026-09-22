import subprocess
import os

trendh_pids = [11960, 8992, 9864, 2336]
print("Cleaning up old TrendH instances (leaving cron3 PID 15256 untouched)...")

for pid in trendh_pids:
    try:
        subprocess.run(['taskkill', '/F', '/PID', str(pid)], check=False)
        print(f"Killed PID {pid}")
    except Exception as e:
        print(f"Error killing PID {pid}: {e}")

print("Done cleaning old TrendH instances.")
