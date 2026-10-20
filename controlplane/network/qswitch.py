from typing import List

class QSwitch:
    def __init__(self,
                 sid: int,
                 switch_name: str,
                 grpc_port: int,
                 connection_id: int) -> None:
        self.sid = sid
        self.switch_name = switch_name
        self.grpc_port = grpc_port
        self.connection_id = connection_id
        self.nhop_dmac_map = {}
        self.ecmp_ports: List[int] = []
        self.ecmp_paths = {}

    def add_path(self, port_number: int, mri_path: List[int]) -> None:
        self.ecmp_paths[port_number] = mri_path


    def add_nhop_dmac(self, port_number: int, mac_address: str) -> None:
        self.nhop_dmac_map[port_number] = mac_address
        if port_number not in self.ecmp_ports:
            self.ecmp_ports.append(port_number)

    def get_ecmp_ports(self) -> List[int]:
        return self.ecmp_ports

    def identify_mri_path(self, full_path: List[int]) -> int:
        for port, path in self.ecmp_paths.items():
            if path == full_path:
                return port
        return -1
