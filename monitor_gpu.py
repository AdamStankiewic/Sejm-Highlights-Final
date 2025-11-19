import subprocess
import time

while True:
    result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'], 
                          capture_output=True, text=True)
    print(f"{time.strftime('%H:%M:%S')} - GPU Memory: {result.stdout.strip()}")
    time.sleep(5)