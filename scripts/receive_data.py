import os
import csv
import signal
import sys
import threading
import time
from datetime import datetime
from scapy.all import sniff, UDP

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

total_packet_count = 0
# Shared counter and lock
packet_count = 0
lock = threading.Lock()

# Path to CSV log file
logs_dir = PROJECT_DIR / "logs_dataplane"
logs_dir.mkdir(parents=True, exist_ok=True)  # creates the folder if it doesn't exist
timestamp = datetime.now().strftime("%Y%m%d") # _%H%M%S
filename = f"{timestamp}_received_packets.csv"
csv_file_path = os.path.join(logs_dir, filename)

# Define a handler function for SIGINT
def handle_sigint(signum, frame):
    global total_packet_count
    global packet_count
    print("\nSIGINT received (CTRL+C pressed). Cleaning up before exit...")
    with open(csv_file_path, mode='a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        timestamp = datetime.now().isoformat()
        writer.writerow([timestamp, packet_count])
        total_packet_count += packet_count
        writer.writerow(["Total packets", total_packet_count])
    # print("Total packets received: %d" % total_packet_count)
    sys.exit(0)

def count_packets(packet):
    global packet_count
    # Cheking UDP and port is optional here as a filter was used in the sniff function
    #if UDP in packet and packet[UDP].dport == 12345:
    with lock:
        packet_count += 1

def log_stats(interval=60):
    global total_packet_count
    global packet_count
    # Write CSV header if the file is new
    with open(csv_file_path, mode='a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        csvfile.seek(0, 2)  # offset 0, 2 end of file
        if csvfile.tell() == 0:  # empty file
            writer.writerow(["timestamp", "packets_received"])

    while True:
        time.sleep(interval)
        with lock:
            timestamp = datetime.now().isoformat()
            count = packet_count
            packet_count = 0
        with open(csv_file_path, mode='a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([timestamp, count])
        total_packet_count += count

# Register the handler for SIGINT and SIGTERM
signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGTERM, handle_sigint)

# Start the logging thread
log_thread = threading.Thread(target=log_stats, args=(60,), daemon=True)
log_thread.start()

# Start sniffing
print("Starting sniffing...")
# sniff(iface="eth0", filter="udp and dst port 12345", prn=count_udp_packets, store=False)
sniff(iface="eth0", filter=None, prn=count_packets, store=False)
