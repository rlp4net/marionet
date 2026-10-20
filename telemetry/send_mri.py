#!/usr/bin/env python3
import yaml
import sys
import send_lib as slib

from pathlib import Path

TELEMETRY_DIR = Path(__file__).resolve().parent
CONFIG_FILE = str(TELEMETRY_DIR / "telemetry_config.yaml")

def load_config():
    with open(CONFIG_FILE, "r") as file:
        return yaml.safe_load(file)

def main():
    if len(sys.argv) < 2:
        print("Usage: send_mri.py <host>")
        sys.exit(1)

    current_host = sys.argv[1]
    config = load_config()

    if current_host not in config["hosts"]:
        print(f"Error: Host {current_host} not found in config.")
        sys.exit(1)

    time_s = config["sending_time"]
    paths = config["hosts"][current_host]["paths"]

    slib.send_src_route_mri(time_s, *paths)

if __name__ == "__main__":
    main()
