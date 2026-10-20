import os
import sys
import grpc
import numpy as np
from scapy.all import Ether, IP, Packet
from scapy.layers.inet import _IPOption_HDR
from scapy.all import Ether, IP, Packet, IPOption
from scapy.fields import (
    IntField,
    ShortField,
    FieldLenField,
    PacketListField
)

home_dir = os.path.expanduser('~')
p4_mininet_path = os.path.join(home_dir, 'p4-mininet')
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), p4_mininet_path))

import p4runtime_lib.bmv2
import p4runtime_lib.helper
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections

from typing import Optional, List
from controlplane.custom_objects.ecmp_weights import EcmpWeights
from .qswitch import QSwitch  

class SwitchTrace(Packet):
    fields_desc = [
        IntField("swid", 0),
        IntField("qdepth", 0)
    ]
    def extract_padding(self, p: bytes) -> (bytes, bytes):
        return b"", p

class IPOption_MRI(IPOption):
    name = "MRI"
    option = 31
    fields_desc = [
        _IPOption_HDR,
        FieldLenField("length", None, fmt="B",
                      length_of="swtraces",
                      adjust=lambda pkt, l: (l * 2) + 4),
        ShortField("count", 0),
        PacketListField("swtraces", [], SwitchTrace,
                        count_from=lambda pkt: (pkt.count * 1))
    ]

class NetworkInterpreter:
    def __init__(self, p4info_file: str, qswitch: QSwitch) -> None:
        self.p4info_file = p4info_file
        self.qswitch = qswitch
        self.p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file)

        self.sw_connection = p4runtime_lib.bmv2.Bmv2SwitchConnection(
            name=qswitch.switch_name,
            address='127.0.0.1:' + str(qswitch.grpc_port),
            device_id=qswitch.connection_id,
            proto_dump_file=f'logs/{qswitch.switch_name}-p4runtime-requests.txt'
        )
        self.sw_connection.MasterArbitrationUpdate()

    def extract_packet_mri(self, scapy_pkt: Packet) -> Optional[IPOption_MRI]:
        if IP in scapy_pkt and IPOption_MRI in scapy_pkt[IP]:
            return scapy_pkt[IP][IPOption_MRI]
        return None

    def extract_packet_path(self, mri_option: IPOption_MRI) -> List[int]:
        if mri_option is None:
            return []
        path_list = []
        for trace in mri_option.swtraces:
            path_list.append(trace.swid)
        return path_list

    def getqlength(self, mri_option: IPOption_MRI, switch_id: int) -> int:
        if mri_option is None:
            return -1
        for trace in mri_option.swtraces:
            if trace.swid == switch_id:
                return trace.qdepth
        return -1

    def init_two_ports_ecmp_table(self, qswitch_obj: QSwitch) -> None:
        ports = qswitch_obj.get_ecmp_ports()
        if len(ports) != 2:
            print("Only 2-port scenario is implemented here.")
            return
        for i in range(0, 50):
            self.create_ecmptable_entry(
                value=i,
                nhop_dmac=qswitch_obj.nhop_dmac[ports[0]],
                port=ports[0]
            )
        for i in range(50, 100):
            self.create_ecmptable_entry(
                value=i,
                nhop_dmac=qswitch_obj.nhop_dmac[ports[1]],
                port=ports[1]
            )

    def create_ecmptable_entry(self, value: int, nhop_dmac: str, port: int) -> None:
        table_entry = self.p4info_helper.buildTableEntry(
            table_name="MyIngress.ecmp_to_nhop",
            match_fields={"meta.ecmp_hash": value},
            action_name="MyIngress.set_nhop",
            action_params={
                "dstAddr": nhop_dmac,
                "port": port
            }
        )
        self.sw_connection.WriteTableEntry(table_entry)

    def read_table_rules(self) -> None:
        print(f"\n----- Reading table rules for {self.qswitch.switch_name} -----")
        for response in self.sw_connection.ReadTableEntries():
            for entity in response.entities:
                entry = entity.table_entry
                print(entry)
                print('-----')

    def push_two_ports_ecmp_weights(self,
                                    old_ecmp_weights: EcmpWeights,
                                    new_ecmp_weights: EcmpWeights) -> None:
        print("=== Pushing new ECMP weights (2 ports) ===")
        for port in self.qswitch.get_ecmp_ports():
            old_bounds = old_ecmp_weights.ecmp_data[port]
            new_bounds = new_ecmp_weights.ecmp_data[port]
            print(f"Port {port}")
            print(f" old: {old_bounds}")
            print(f" new: {new_bounds}")

        ports = self.qswitch.get_ecmp_ports()

        old_cut = old_ecmp_weights.ecmp_data[ports[1]][0]
        new_cut = new_ecmp_weights.ecmp_data[ports[1]][0]

        if new_cut > old_cut:
            for i in range(old_cut, new_cut):
                self.update_ecmptable_entry(value=i,
                                        port=ports[0],
                                        nhop_dmac=self.qswitch.nhop_dmac_map[ports[0]])
        elif new_cut < old_cut:
            for i in range(new_cut, old_cut):
                self.update_ecmptable_entry(value=i,
                                        port=ports[1],
                                        nhop_dmac=self.qswitch.nhop_dmac_map[ports[1]])

    def update_ecmptable_entry(self,
                               value: int,
                               port: int,
                               nhop_dmac: str) -> None:
        table_entry = self.p4info_helper.buildTableEntry(
            table_name="MyIngress.ecmp_to_nhop",
            match_fields={"meta.ecmp_hash": value},
            action_name="MyIngress.set_nhop",
            action_params={
                "dstAddr": nhop_dmac,
                "port": port
            }
        )
        self.sw_connection.ModifyTableEntry(table_entry)

    def receive_pkt(self) -> Optional[Packet]:
        try:
            packetin = self.sw_connection.StreamMessageIn()
            if packetin.WhichOneof('update') == 'packet':
                raw_packet = packetin.packet.payload
                scapy_packet = Ether(raw_packet)
                return scapy_packet
        except grpc.RpcError as e:
            printGrpcError(e)
        return None

    def push_ecmp_weights(self,
                          old_ecmp_weights: EcmpWeights,
                          new_ecmp_weights: EcmpWeights) -> None:
        if len(self.qswitch.get_ecmp_ports()) == 2:
            self.push_two_ports_ecmp_weights(old_ecmp_weights, new_ecmp_weights)
        else:
            print("ERROR: ECMP ports not equal to 2. Not implemented in original code.")
            # or handle N-port scenario if your original code does so

    def readTableRules(self) -> None:
        self.read_table_rules()
