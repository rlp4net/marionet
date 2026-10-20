import math
from controlplane.controller_config import MAX_QUEUE_LENGTH, PACKET_DIFF_MAX

class PortInfo:
    def __init__(self,
                 packet_diff_count: int = 0,
                 last_known_queue: int = -1) -> None:
        self.packet_diff_count = packet_diff_count
        self.last_known_queue = last_known_queue

    def update_queue_length(self, new_length: int) -> None:
        self.packet_diff_count += 1
        length_clamped = min(new_length, MAX_QUEUE_LENGTH)
        self.last_known_queue = length_clamped

    def mark_missing_packet(self) -> None:
        if self.last_known_queue == -1:
            self.last_known_queue = MAX_QUEUE_LENGTH

    def has_reached_limit(self) -> bool:
        return self.packet_diff_count >= PACKET_DIFF_MAX

    def rescaled_queue_length(self, max_q_state: int) -> int:
        if max_q_state == 0:
            return 0
        ratio = float(MAX_QUEUE_LENGTH) / float(max_q_state)
        return math.ceil(self.last_known_queue / ratio)

    def reset_counters(self) -> None:
        self.packet_diff_count = 0
        self.last_known_queue = -1
