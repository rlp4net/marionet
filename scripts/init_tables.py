#!/usr/bin/env python3
import argparse
import sys
from time import sleep

import grpc

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
LOGS_DIR = PROJECT_DIR / "logs"

# Import P4Runtime lib
p4_mininet_path = Path.home() / "p4-mininet"
sys.path.append(str(p4_mininet_path))

import p4runtime_lib.bmv2
import p4runtime_lib.helper
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections


def write_qtable_entry(p4info_helper, ingress_sw, value, nhop_dmac, port):
    # Create table entry
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ecmp_to_nhop",
        match_fields={
            "meta.ecmp_hash": (value),
        },
        action_name="MyIngress.set_nhop",
        action_params={
            "dstAddr": nhop_dmac,
            "port": port,
        })
    # print("value: %d, nhop_dmac: %s, port: %d" % (value, nhop_dmac, port))
    ingress_sw.WriteTableEntry(table_entry)

def init_qtable(p4info_helper, ingress_sw, nhop_dmacs, ports):
    print("Adding 50-50 output entries on switch %s (table ecmp_to_nhop)" % ingress_sw.name)
    for i in range(0, 50):
        write_qtable_entry(p4info_helper, ingress_sw=ingress_sw, value=i,
            nhop_dmac=nhop_dmacs[0], port=ports[0])
    for i in range(50, 100):
        write_qtable_entry(p4info_helper, ingress_sw=ingress_sw, value=i,
            nhop_dmac=nhop_dmacs[1], port=ports[1])

def readTableRules(p4info_helper, sw):
    """
    Reads the table entries from all tables on the switch.
    :param p4info_helper: the P4Info helper
    :param sw: the switch connection
    """
    print('\n----- Reading tables rules for %s -----' % sw.name)
    for response in sw.ReadTableEntries():
        for entity in response.entities:
            entry = entity.table_entry
            print(entry)
            print('-----')


# ================
#  Main function 
# ================
def main(p4info_file):
    
    print('Using P4Info file %s' % p4info_file)    
    # Instantiate a P4Runtime helper from the p4info file
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file)
    
    # Switches to monitor (name, gRPC port, device id)
    sw_list = [('s1', 50051, 0)]

    sw_connections = []
                  
    # Create a switch connection object for each switch
    for i, val in enumerate(sw_list):
        sw_connections.append(
            p4runtime_lib.bmv2.Bmv2SwitchConnection(
                name = val[0],
                address = '127.0.0.1:'+str(val[1]),
                device_id = val[2],
                proto_dump_file=str(LOGS_DIR / "s3-p4runtime-requests.txt"))
        )
     
        # Waiting for packetIn packets from the switch(s)
        sw = sw_connections[-1]
        # Send master arbitration update message to establish this controller as
        # master (required by P4Runtime before performing any write or stream operation)
        sw.MasterArbitrationUpdate()
        
    # s1 ECMP next-hop MACs, ordered consistently with ports below.
    nhop_dmacs = ["00:00:00:00:01:04", "00:00:00:00:01:05"]
    ports = [2, 3]
    init_qtable(p4info_helper, sw_connections[0], nhop_dmacs, ports)

    #readTableRules(p4info_helper, sw_connections[0])
    ShutdownAllSwitchConnections()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Monitor/Initializes Qlearning tables')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default=str(PROJECT_DIR / "build/switch.p4.p4info.txt"))
    args = parser.parse_args()
    main(args.p4info)
