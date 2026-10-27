import os
import sys
import time
import webbrowser
import threading
import uvicorn

def open_browser():
    time.sleep(1.2)
    url = "http://127.0.0.1:8000"
    print(f"\n[*] Opening SonicMortise Interface: {url}\n")
    webbrowser.open(url)

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(base_dir, "backend")
    sys.path.insert(0, backend_dir)

    print("=" * 60)
    print("  SonicMortise - Ultrasonic Attestation System")
    print("=" * 60)

    threading.Thread(target=open_browser, daemon=True).start()

    from app import app, read_serial_worker
    threading.Thread(target=read_serial_worker, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
