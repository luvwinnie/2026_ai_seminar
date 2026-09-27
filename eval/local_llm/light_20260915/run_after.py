"""Wait off the interactive thread; never overlap Ollama inference workloads."""
import json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
deadline=time.monotonic()+10800
while time.monotonic()<deadline:
    meta=json.loads((HERE/'generation/metadata.json').read_text())
    if meta.get('finished_at'):break
    time.sleep(10)
else:raise RuntimeError('generation did not finish within 3 hours')
for script,log in [('run_embeddings.py','embeddings.log'),('diagnostics.py','diagnostics.log'),('report.py','report.log')]:
    print('START',script,flush=True)
    with (HERE/log).open('w') as f:
        subprocess.run([sys.executable,'-u',str(HERE/script)],stdout=f,stderr=subprocess.STDOUT,check=True)
    print('DONE',script,flush=True)
