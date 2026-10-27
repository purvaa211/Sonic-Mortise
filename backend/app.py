import os
import sys
import json
import time
import math
import random
import hmac
import hashlib
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

import serial
import serial.tools.list_ports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

HMAC_SECRET_KEY = b"SonicMortiseSecretKeyVITPune"

app = FastAPI(title="SonicMortise Attestation Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SystemState:
    def __init__(self):
        self.mode = "SIMULATION"
        self.serial_port: Optional[str] = None
        self.serial_conn: Optional[serial.Serial] = None
        self.is_connected = False
        self.continuous_mode = True
        
        self.is_enrolled = True
        self.enrolled_challenge = 5
        self.enrolled_features = {
            "peak_amp": 1420.0,
            "energy": 845000.0,
            "onset_idx": 42,
            "dc_offset": 2048.0
        }
        self.enrolled_wave = self._generate_waveform(challenge_code=5, condition="SEATED")
        
        self.sim_condition = "SEATED"
        self.sequence_counter = 100
        self.active_challenge = 5
        
        self.latest_result: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "seq": 100,
            "challenge": 5,
            "state": "MATCH",
            "reason": "Acoustic reflection profile matches enrolled reference baseline.",
            "score": 97.2,
            "dc_offset": 2048.0,
            "peak_amp": 1410.0,
            "energy": 839000.0,
            "onset_idx": 38,
            "sensor": {"temp": 26.4, "pressure": 101.32},
            "hmac": "",
            "policy_action": "ADMITTED_TO_DATA_PATH",
            "wave": self.enrolled_wave,
            "enrolled_wave": self.enrolled_wave
        }
        self.connected_websockets: List[WebSocket] = []

    def _generate_waveform(self, challenge_code: int, condition: str = "SEATED") -> List[int]:
        points = 100
        wave = []
        dc = 2048
        
        if condition == "SEATED":
            amp = 1400.0
            onset = 38 + (challenge_code % 3) * 2
            damping = 0.08
            noise_level = 15
        elif condition == "LOOSE":
            amp = 780.0
            onset = 44 + (challenge_code % 3) * 2
            damping = 0.12
            noise_level = 25
        elif condition == "DISPLACED":
            amp = 320.0
            onset = 52
            damping = 0.18
            noise_level = 35
        elif condition == "NOISE":
            amp = 200.0
            onset = 20
            damping = 0.05
            noise_level = 400
        else:
            amp = 1400.0
            onset = 40
            damping = 0.08
            noise_level = 20

        freq = 0.45 + (challenge_code % 4) * 0.05
        
        for i in range(points):
            val = dc + random.randint(-noise_level, noise_level)
            if i >= onset:
                decay = math.exp(-damping * (i - onset))
                burst = amp * decay * math.sin(freq * (i - onset))
                val += burst
            val = max(10, min(4085, int(val)))
            wave.append(val)
        return wave

    def generate_simulated_packet(self) -> Dict[str, Any]:
        self.sequence_counter += 1
        if self.continuous_mode:
            self.active_challenge = (self.active_challenge % 8) + 1
            
        wave = self._generate_waveform(self.active_challenge, self.sim_condition)
        
        dc_baseline = sum(wave[:20]) / 20.0
        max_dev = max(abs(x - dc_baseline) for x in wave)
        energy = sum((x - dc_baseline)**2 for x in wave)
        
        quality_pass = True
        reason = "Acoustic reflection profile matches enrolled reference baseline."
        if self.sim_condition == "NOISE":
            quality_pass = False
            reason = "Signal SNR below threshold. Excessive baseline noise."
            state = "INVALID_INDETERMINATE"
            score = 32.0
            policy_action = "QUARANTINED_HOLD_FOR_REMEASURE"
        elif not self.is_enrolled:
            state = "INVALID_INDETERMINATE"
            reason = "No enrolled baseline reference found."
            score = 0.0
            policy_action = "QUARANTINED_HOLD_FOR_REMEASURE"
        else:
            e_wave = self.enrolled_wave
            e_dc = self.enrolled_features["dc_offset"]
            dot = sum((wave[i] - dc_baseline) * (e_wave[i] - e_dc) for i in range(len(wave)))
            norm1 = math.sqrt(sum((wave[i] - dc_baseline)**2 for i in range(len(wave))))
            norm2 = math.sqrt(sum((e_wave[i] - e_dc)**2 for i in range(len(e_wave))))
            
            corr = (dot / (norm1 * norm2)) if (norm1 * norm2 > 0) else 0.0
            
            if self.sim_condition == "SEATED":
                score = min(99.2, max(88.0, corr * 100.0 + random.uniform(-1.0, 1.5)))
                state = "MATCH"
                policy_action = "ADMITTED_TO_DATA_PATH"
                reason = "Acoustic reflection matches enrolled connector profile."
            elif self.sim_condition == "LOOSE":
                score = min(73.0, max(52.0, corr * 85.0 + random.uniform(-2, 2)))
                state = "INVALID_INDETERMINATE"
                policy_action = "QUARANTINED_HOLD_FOR_REMEASURE"
                reason = "Correlation within uncertainty zone. Connector may be loose."
            elif self.sim_condition == "DISPLACED":
                score = min(46.0, max(12.0, corr * 50.0 + random.uniform(-3, 3)))
                state = "MISMATCH"
                policy_action = "REJECTED_UNTRUSTED_DATA_PATH"
                reason = "Acoustic path altered. Cavity geometry mismatch or connector displaced."
            else:
                score = 40.0
                state = "MISMATCH"
                policy_action = "REJECTED_UNTRUSTED_DATA_PATH"
                reason = "Physical anomaly detected."

        temp = round(25.4 + math.sin(self.sequence_counter * 0.15) * 1.5 + random.uniform(-0.1, 0.1), 2)
        pressure = round(101.32 + math.cos(self.sequence_counter * 0.08) * 0.3 + random.uniform(-0.04, 0.04), 2)
        
        msg_str = f"{self.sequence_counter}:{self.active_challenge}:{state}:{temp}:{pressure}"
        signature = hmac.new(HMAC_SECRET_KEY, msg_str.encode('utf-8'), hashlib.sha256).hexdigest()

        packet = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "seq": self.sequence_counter,
            "challenge": self.active_challenge,
            "state": state,
            "reason": reason,
            "score": round(score, 1),
            "dc_offset": round(dc_baseline, 1),
            "peak_amp": round(max_dev, 1),
            "energy": round(energy, 0),
            "onset_idx": 38 if state == "MATCH" else 48,
            "sensor": {"temp": temp, "pressure": pressure},
            "hmac": signature,
            "policy_action": policy_action,
            "wave": wave,
            "enrolled_wave": self.enrolled_wave
        }
        self.latest_result = packet
        return packet

state_mgr = SystemState()

def read_serial_worker():
    while True:
        if state_mgr.mode == "LIVE" and state_mgr.serial_conn and state_mgr.serial_conn.is_open:
            try:
                line = state_mgr.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                if line and line.startswith("{"):
                    data = json.loads(line)
                    if data.get("type") == "ATTESTATION":
                        st = data.get("state", "INVALID_INDETERMINATE")
                        if st == "MATCH":
                            action = "ADMITTED_TO_DATA_PATH"
                        elif st == "MISMATCH":
                            action = "REJECTED_UNTRUSTED_DATA_PATH"
                        else:
                            action = "QUARANTINED_HOLD_FOR_REMEASURE"

                        packet = {
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "seq": data.get("seq", 0),
                            "challenge": data.get("challenge", 0),
                            "state": st,
                            "reason": data.get("reason", "OK"),
                            "score": data.get("score", 0.0),
                            "dc_offset": data.get("dc_offset", 2048.0),
                            "peak_amp": data.get("peak_amp", 0.0),
                            "energy": data.get("energy", 0.0),
                            "onset_idx": data.get("onset_idx", 0),
                            "sensor": data.get("sensor", {"temp": 25.0, "pressure": 101.3}),
                            "hmac": data.get("hmac", ""),
                            "policy_action": action,
                            "wave": data.get("wave", []),
                            "enrolled_wave": state_mgr.enrolled_wave
                        }
                        if st == "ENROLLED":
                            state_mgr.is_enrolled = True
                            state_mgr.enrolled_wave = packet["wave"]
                            packet["state"] = "MATCH"
                            packet["reason"] = "Baseline profile enrolled successfully."

                        state_mgr.latest_result = packet
            except Exception as e:
                time.sleep(0.5)
        time.sleep(0.01)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state_mgr.connected_websockets.append(websocket)
    try:
        await websocket.send_json(state_mgr.latest_result)
        while True:
            if state_mgr.mode == "SIMULATION" and state_mgr.continuous_mode:
                pkt = state_mgr.generate_simulated_packet()
                await websocket.send_json(pkt)
                await asyncio.sleep(1.2)
            elif state_mgr.mode == "LIVE":
                await websocket.send_json(state_mgr.latest_result)
                await asyncio.sleep(0.8)
            else:
                await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        state_mgr.connected_websockets.remove(websocket)
    except Exception:
        if websocket in state_mgr.connected_websockets:
            state_mgr.connected_websockets.remove(websocket)

@app.get("/api/ports")
def get_available_ports():
    ports = serial.tools.list_ports.comports()
    port_list = [{"port": p.device, "desc": p.description} for p in ports]
    return {"ports": port_list, "current_mode": state_mgr.mode, "connected_port": state_mgr.serial_port}

@app.post("/api/connect")
async def connect_port(payload: Dict[str, str]):
    port = payload.get("port")
    if not port or port == "SIMULATION":
        if state_mgr.serial_conn and state_mgr.serial_conn.is_open:
            state_mgr.serial_conn.close()
        state_mgr.mode = "SIMULATION"
        state_mgr.serial_port = None
        state_mgr.is_connected = True
        return {"status": "success", "mode": "SIMULATION"}
    
    try:
        if state_mgr.serial_conn and state_mgr.serial_conn.is_open:
            state_mgr.serial_conn.close()
        conn = serial.Serial(port, 115200, timeout=1)
        state_mgr.serial_conn = conn
        state_mgr.serial_port = port
        state_mgr.mode = "LIVE"
        state_mgr.is_connected = True
        return {"status": "success", "mode": "LIVE", "port": port}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/enroll")
async def enroll_baseline(payload: Optional[Dict[str, Any]] = None):
    challenge = payload.get("challenge", 5) if payload else 5
    if state_mgr.mode == "LIVE" and state_mgr.serial_conn and state_mgr.serial_conn.is_open:
        cmd = f"ENROLL {challenge}\n"
        state_mgr.serial_conn.write(cmd.encode('utf-8'))
        return {"status": "enrolling_hardware", "challenge": challenge}
    else:
        state_mgr.is_enrolled = True
        state_mgr.enrolled_challenge = challenge
        state_mgr.enrolled_wave = state_mgr._generate_waveform(challenge, "SEATED")
        state_mgr.sim_condition = "SEATED"
        pkt = state_mgr.generate_simulated_packet()
        return {"status": "enrolled_simulation", "packet": pkt}

@app.post("/api/verify")
async def verify_now(payload: Optional[Dict[str, Any]] = None):
    challenge = payload.get("challenge", state_mgr.active_challenge) if payload else state_mgr.active_challenge
    if state_mgr.mode == "LIVE" and state_mgr.serial_conn and state_mgr.serial_conn.is_open:
        cmd = f"VERIFY {challenge}\n"
        state_mgr.serial_conn.write(cmd.encode('utf-8'))
        return {"status": "verifying_hardware", "challenge": challenge}
    else:
        pkt = state_mgr.generate_simulated_packet()
        return {"status": "verified_simulation", "packet": pkt}

@app.post("/api/set_condition")
def set_sim_condition(payload: Dict[str, str]):
    cond = payload.get("condition", "SEATED")
    if cond in ["SEATED", "LOOSE", "DISPLACED", "NOISE"]:
        state_mgr.sim_condition = cond
        return {"status": "success", "condition": cond}
    raise HTTPException(status_code=400, detail="Invalid condition")

@app.post("/api/toggle_continuous")
def toggle_continuous(payload: Dict[str, bool]):
    state_mgr.continuous_mode = payload.get("continuous", True)
    return {"status": "success", "continuous": state_mgr.continuous_mode}

frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

@app.get("/")
def get_index():
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Frontend Not Found</h2>")

if __name__ == "__main__":
    import threading
    t = threading.Thread(target=read_serial_worker, daemon=True)
    t.start()
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
