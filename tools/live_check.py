"""Bounded integration check against the running local single-player game."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from beast_pick.backend import Client

events=[]
def receive(e):
    events.append(e)
    print(json.dumps(e,ensure_ascii=False),flush=True)

duration=float(sys.argv[1]) if len(sys.argv)>1 else 15
path=Path(__file__).resolve().parents[1]/'artifacts'/'live-check.json'
try:
    with Client(receive) as client:
        receive({'event':'connected',**client.connect()})
        client.configure(radius=8,corpses=True,items=True,enabled=True)
        deadline=time.monotonic()+duration
        while time.monotonic()<deadline:
            time.sleep(1)
            receive({'event':'poll',**client.heartbeat()})
        client.stop()
        receive({'event':'stopped',**client.heartbeat()})
finally:
    path.write_text(json.dumps(events,indent=2,ensure_ascii=False),encoding='utf-8')
