#!/usr/bin/env python3
# kill_port.py — kill any process listening on port 8080
# TODO: replace with fuser -k 8080/tcp once iproute2+psmisc are in runner image
import os, signal, socket

PORT_HEX = format(8080, '04X')  # 1F90

try:
    socket.create_connection(('127.0.0.1', 8080), timeout=1).close()
except ConnectionRefusedError:
    print('Port 8080 free')
    raise SystemExit(0)

killed = []
for pid in os.listdir('/proc'):
    if not pid.isdigit():
        continue
    try:
        with open(f'/proc/{pid}/net/tcp') as f:
            for line in f:
                if PORT_HEX in line.upper():
                    os.kill(int(pid), signal.SIGKILL)
                    killed.append(pid)
                    break
    except Exception:
        pass

if killed:
    print(f'Killed PID(s): {", ".join(killed)}')
else:
    print('No process found on port 8080')
