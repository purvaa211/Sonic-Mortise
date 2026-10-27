# Hardware Wiring & Connection Guide

### 1. Power Rails
- **ESP32 3V3** -> Breadboard Red (+) Rail
- **ESP32 GND** -> Breadboard Blue (-) Ground Rail

---

### 2. Transmitter (40 kHz Bare Piezo 'T' / 40T)
- **Terminal 1** -> 100 Ω Resistor -> **ESP32 GPIO 18**
- **Terminal 2** -> 100 Ω Resistor -> **ESP32 GPIO 19**

---

### 3. Virtual Ground Generator (Vref ≈ 1.65V)
- **10 kΩ Resistor**: from +3.3V rail to an open row (`Row VREF`)
- **10 kΩ Resistor**: from `Row VREF` to GND rail

---

### 4. MCP6002 Op-Amp (Dual Rail-to-Rail DIP-8)

```
                 MCP6002 DIP-8 Pinout
                     +---v---+
      (VOUTA) Pin 1 -| 1   8 |- Pin 8 (VDD -> +3.3V)
      (VINA-) Pin 2 -| 2   7 |- Pin 7 (VOUTB -> GPIO 34)
      (VINA+) Pin 3 -| 3   6 |- Pin 6 (VINB-)
       (GND)  Pin 4 -| 4   5 |- Pin 5 (VINB+ -> VREF)
                     +-------+
```

#### Power:
- **Pin 4 (VSS)** -> GND Rail
- **Pin 8 (VDD)** -> +3.3V Rail

#### Stage 1 (Gain ≈ 22x):
- **Pin 3 (VINA+)** -> Receiver (40R) Terminal 1
- **Pin 3 (VINA+)** -> 100 kΩ Resistor -> `Row VREF`
- **Receiver (40R) Terminal 2** -> `Row VREF`
- **Pin 2 (VINA-)** -> 4.7 kΩ Resistor -> `Row VREF`
- **Pin 2 (VINA-)** -> 100 kΩ Resistor -> **Pin 1 (VOUTA)**

#### Stage 2 (Gain ≈ 10x):
- **Pin 5 (VINB+)** -> `Row VREF`
- **Pin 6 (VINB-)** -> 10 kΩ Resistor -> **Pin 1 (VOUTA)**
- **Pin 6 (VINB-)** -> 100 kΩ Resistor -> **Pin 7 (VOUTB)**
- **Pin 7 (VOUTB)** -> 1 kΩ Resistor -> **ESP32 GPIO 34**

---

### 5. Acoustic Cavity Fixture
- Position the bare 40T transmitter and 40R receiver inside a 4 cm to 8 cm tube or collar enclosing the sensor connector.
- Seating the connector produces the authentic acoustic reverberation signature. Pulling or replacing the connector alters the acoustic path and trips the attestation alarm.
