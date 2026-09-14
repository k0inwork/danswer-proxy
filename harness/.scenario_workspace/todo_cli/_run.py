import subprocess, sys, os
result = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), '_fix.py')], capture_output=True, text=True)
print(result.stdout)
print(result.stderr, file=sys.stderr)
