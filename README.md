# SonicMortise

**Trusted Sensor-Data Attestation using Ultrasonic Connectors**

SonicMortise is a physical-layer attestation mechanism that verifies the mechanical integrity and authentic seating of an IoT sensor connector assembly using challenge-response ultrasonic interrogation.

---

## Key Features

- **Ultrasonic Cavity Interrogation**: Drives a 40 kHz acoustic burst across the connector cavity and analyzes reflection reverberations.
- **Three-Tier Attestation Policy**:
  - `MATCH`: Connector physically authenticated -> Admitted to network data path.
  - `MISMATCH`: Displacement or foreign tampering detected -> Rejected and quarantined.
  - `INVALID / INDETERMINATE`: Poor signal quality or uncertainty zone -> Held for remeasurement.
- **Cryptographic Binding**: Binds physical attestation metadata with IoT sensor payload using HMAC-SHA256.
- **Real-Time Interface**: Minimal, uncluttered dashboard with live oscilloscope, feature metrics, and hardware simulation mode.

---

## Hardware Setup

### Bill of Materials
- ESP32-WROOM-32 DevKit V1
- 40 kHz bare ultrasonic transmitter transducer (40T)
- 40 kHz bare ultrasonic receiver transducer (40R)
- MCP6002 rail-to-rail dual operational amplifier (DIP-8)
- Resistors: 100 Ω, 1 kΩ, 4.7 kΩ, 10 kΩ, 100 kΩ
- Solderless breadboard & jumper wires

Detailed wiring pinout and schematics are documented in [`firmware/WIRING_GUIDE.md`](firmware/WIRING_GUIDE.md).

---

## Quick Start

### 1. ESP32 Firmware
Flash [`firmware/sonic_mortise_esp32.ino`](firmware/sonic_mortise_esp32.ino) to your ESP32 using the Arduino IDE.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Dashboard
```bash
python run.py
```
Or double-click `run.bat` on Windows. The application will launch and open the interface at `http://127.0.0.1:8000`.
