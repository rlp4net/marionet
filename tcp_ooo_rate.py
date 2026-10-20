#!/usr/bin/env python3
"""
Compute rate of out-of-order TCP segments in a pcap, using Scapy.

Usage:
    python tcp_ooo_rate.py input.pcap

Requires:
    pip install scapy
"""

from scapy.all import PcapReader, TCP, IP, IPv6

from collections import defaultdict
import argparse
import dpkt
import socket

def _ip_to_str(b: bytes) -> str:
    if len(b) == 4:
        return socket.inet_ntoa(b)
    if len(b) == 16:
        return socket.inet_ntop(socket.AF_INET6, b)
    return str(b)

class FlowStats:
    def __init__(self):
        # Highest sequence number (seq + payload_len) seen so far in this direction
        self.max_seq_seen = None

        # Total TCP segments (in this direction)
        self.total_segments = 0

        # Out-of-order segments (in this direction)
        self.ooo_segments = 0

        # For basic duplicate detection: (seq, payload_len) pairs
        self.seen_segments = set()

    def update(self, seq, payload_len):
        """
        Update flow stats with a new TCP segment defined by its
        starting seq and payload length.
        """
        self.total_segments += 1

        seg_key = (seq, payload_len)

        # Ignore exact duplicates (same seq and payload length)
        if seg_key in self.seen_segments:
            return

        # First segment we see
        if self.max_seq_seen is None:
            self.max_seq_seen = seq + payload_len
            self.seen_segments.add(seg_key)
            return

        # Out-of-order heuristic:
        # if seq < max_seq_seen and this is not a duplicate, we count it as OOO
        if seq < self.max_seq_seen:
            self.ooo_segments += 1

        # Advance max_seq_seen if this segment extends the right edge
        if seq + payload_len > self.max_seq_seen:
            self.max_seq_seen = seq + payload_len

        self.seen_segments.add(seg_key)


def get_flow_key(pkt):
    """
    Return a tuple identifying the flow + direction.
    We separate directions, so:
    (src_ip, src_port, dst_ip, dst_port) and
    (dst_ip, dst_port, src_ip, src_port)
    are treated as different flows.
    """
    ip_layer = pkt.getlayer(IP) or pkt.getlayer(IPv6)
    tcp = pkt[TCP]

    src_ip = ip_layer.src
    dst_ip = ip_layer.dst
    sport = tcp.sport
    dport = tcp.dport

    return (src_ip, sport, dst_ip, dport)


def get_seq_and_payload_len(pkt):
    """
    Returns (seq, payload_len) using IP/TCP header length fields.
    Works even when payload bytes are missing (anonymized capture).

    Supports both IPv4 and IPv6.
    """

    tcp = pkt[TCP]
    seq = tcp.seq

    # TCP header length in bytes
    tcp_hlen = tcp.dataofs * 4 if tcp.dataofs else 20  # Fallback: minimal TCP header

    # IPv4
    if pkt.haslayer(IP):
        ip = pkt[IP]

        # IP header length (IHL * 4)
        ip_hlen = ip.ihl * 4 if ip.ihl else 20  # Fallback: minimal IPv4 header

        # Total IP length includes: IP header + TCP header + payload
        if ip.len is not None:
            payload_len = ip.len - ip_hlen - tcp_hlen
        else:
            payload_len = 0  # Should not happen, but safe fallback

        # Corrupted or anonymized header inconsistencies
        if payload_len < 0:
            payload_len = 0

        return seq, payload_len
    # IPv6
    elif pkt.haslayer(IPv6):
        ip6 = pkt[IPv6]

        # IPv6 has fixed 40-byte header + extension headers (Scapy puts ext hdrs as layers)
        # The IPv6 "plen" field is *payload length*, including TCP header + TCP payload.
        plen = ip6.plen if ip6.plen is not None else 0

        # IPv6 payload length = TCP header + TCP payload
        payload_len = plen - tcp_hlen

        # Corrupted or anonymized header inconsistencies
        if payload_len < 0:
            payload_len = 0

        return seq, payload_len
    else:
        # Should not happen
        return seq, 0


def analyze_pcap(pcap_path):
    flows = defaultdict(FlowStats)

    with open(pcap_path, "rb") as f:
        pcap = dpkt.pcap.Reader(f)

        for ts, buf in pcap:
            # Parse L2 (Ethernet). Si ce n’est pas Ethernet, on skip.
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                pkt = eth.data
            except Exception:
                continue

            ip = None
            ip_ver = None

            if isinstance(pkt, dpkt.ip.IP):
                ip = pkt
                ip_ver = 4
            elif isinstance(pkt, dpkt.ip6.IP6):
                ip = pkt
                ip_ver = 6
            else:
                continue

            # TCP only
            tcp = ip.data
            if not isinstance(tcp, dpkt.tcp.TCP):
                continue

            seq = tcp.seq

            # TCP header length (bytes)
            tcp_hlen = (tcp.off * 4) if getattr(tcp, "off", 0) else 20

            if ip_ver == 4:
                # IPv4 header length (bytes)
                ip_hlen = (ip.hl * 4) if getattr(ip, "hl", 0) else 20
                ip_len = ip.len if ip.len is not None else 0

                payload_len = ip_len - ip_hlen - tcp_hlen
                if payload_len < 0:
                    payload_len = 0
            else:
                # IPv6 plen = payload length including TCP header + TCP payload (comme Scapy)
                plen = ip.plen if ip.plen is not None else 0
                payload_len = plen - tcp_hlen
                if payload_len < 0:
                    payload_len = 0

            # Ignore pure ACKs / 0 payload
            if payload_len == 0:
                continue

            src_ip = _ip_to_str(ip.src)
            dst_ip = _ip_to_str(ip.dst)
            sport = tcp.sport
            dport = tcp.dport
            flow_key = (src_ip, sport, dst_ip, dport)

            flows[flow_key].update(seq, payload_len)

    return flows


def print_stats(flows):
    """
    Print global out-of-order statistics.
    """
    global_total = 0
    global_ooo = 0

    for flow_key, stats in flows.items():
        src_ip, sport, dst_ip, dport = flow_key
        total = stats.total_segments
        ooo = stats.ooo_segments
        # rate = (ooo / total * 100) if total > 0 else 0.0
        global_total += total
        global_ooo += ooo

    print("Global stats:")
    print(f"  Total segments:      {global_total}")
    print(f"  Out-of-order:        {global_ooo}")
    if global_total > 0:
        print(f"  Overall OOO rate:    {global_ooo / global_total * 100:.3f}%")
    else:
        print("  Overall OOO rate:    N/A (no TCP segments)")


def main():
    parser = argparse.ArgumentParser(description="Compute out-of-order TCP segment rate from a pcap.")
    parser.add_argument("pcap", help="Input pcap file.")
    args = parser.parse_args()

    flows = analyze_pcap(args.pcap)
    print_stats(flows)


if __name__ == "__main__":
    main()
