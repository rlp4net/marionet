import pandas as pd
import matplotlib.pyplot as plt

LOGS_DP_DIR="testing/packets_emission/logs_dataplane/"

# Configure the log folders to compare before running this script.
SENT_PACKETS = LOGS_DP_DIR + "sent_packets.csv"
RECEIVED_PACKETS_ECMP = LOGS_DP_DIR + "received_packets_ECMP.csv"
RECEIVED_PACKETS_MARIONET_WL = LOGS_DP_DIR + "received_packets_MARIONET_w_learn.csv"
RECEIVED_PACKETS_MARIONET_UDL = LOGS_DP_DIR + "received_packets_MARIONET_ud_learn.csv"
# RECEIVED_PACKETS_MARIONET_B2 = LOGS_DP_DIR + "received_packets_MARIONET_b2.csv"
# RECEIVED_PACKETS_MARIONET_B4 = LOGS_DP_DIR + "received_packets_MARIONET_b4.csv"
# RECEIVED_PACKETS_MARIONET_B8 = LOGS_DP_DIR + "received_packets_MARIONET_b8.csv"

# Load the CSV files
sent_df = pd.read_csv(SENT_PACKETS, parse_dates=["timestamp"])
#recv_df_ecmp = pd.read_csv(RECEIVED_PACKETS_ECMP, parse_dates=["timestamp"])
recv_df_marionet_wl = pd.read_csv(RECEIVED_PACKETS_MARIONET_WL, parse_dates=["timestamp"])
recv_df_marionet_udl = pd.read_csv(RECEIVED_PACKETS_MARIONET_UDL, parse_dates=["timestamp"])
#recv_df_marionet_b2 = pd.read_csv(RECEIVED_PACKETS_MARIONET_B2, parse_dates=["timestamp"])
#recv_df_marionet_b4 = pd.read_csv(RECEIVED_PACKETS_MARIONET_B4, parse_dates=["timestamp"])
#recv_df_marionet_b8 = pd.read_csv(RECEIVED_PACKETS_MARIONET_B8, parse_dates=["timestamp"])

# Compute time intervals (we suppose a fixed time interval between entries)
interval_seconds = round((sent_df["timestamp"][1] - sent_df["timestamp"][0]).total_seconds())
x_seconds = [i * interval_seconds for i in range(len(sent_df))]

# Plot
# plt.figure(figsize=(10, 6))

# Plot sent packets
plt.plot(x_seconds, sent_df["packets_sent"], 
         linestyle='None', marker='x', label='Packets sent')

# Plot received packets ECMP
# plt.plot(x_seconds, recv_df_ecmp["packets_received"], 
#          linestyle='None', marker='o', label='Packets received ECMP')

# Plot received packets MARIONET
plt.plot(x_seconds, recv_df_marionet_wl["packets_received"], 
         linestyle='None', marker='.', label='Packets received MARIONET weight learner')

plt.plot(x_seconds, recv_df_marionet_udl["packets_received"], 
         linestyle='None', marker='*', label='Packets received MARIONET up down learner (batch 2)')

# plt.plot(x_seconds, recv_df_marionet_b2["packets_received"], 
#          linestyle='None', marker='+', label='Packets received MARIONET (batch 2, w in S)')

# plt.plot(x_seconds, recv_df_marionet_b2_no_w["packets_received"], 
#          linestyle='None', marker='*', label='Packets received MARIONET (batch 2, no w in S)')

# plt.plot(x_seconds, recv_df_marionet_b8["packets_received"], 
#          linestyle='None', marker='-', label='Packets received MARIONET (batch 8)')


# Formatting
plt.xlabel("Time since start (seconds)")
plt.ylabel("Number of Packets")
plt.title("Sent vs. Received Packets Over Time (Relative)")
# bbox_to_anchor(x, y) places the corner of the legend specified by loc at x, y
plt.legend(fontsize='x-small', loc='upper left', bbox_to_anchor=(0.38, 0.18)) 
plt.grid(True)
plt.tight_layout()

# Save the plot
plt.savefig("packets_plot.png", dpi=300)

# Show the plot
# plt.show()
