import subprocess

cmd = ['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine']
try:
    out = subprocess.check_output(cmd, text=True, errors='ignore')
    print("=== WMIC PYTHON PROCESSES ===")
    for line in out.strip().split('\n'):
        if line.strip():
            print(line.strip())
except Exception as e:
    print(f"Error: {e}")
