from queue import Queue, Empty

class TelemetryBuffers:
    """This class manages the buffers that hold telemetry information (queue length) for a switch.

    There if one buffer per port (the buffer is managed as a FIFO queue).
    Each time a new telemetry information arrives, it is added at the end of the queue by the receive telemetry thread.
    The queue is drained periodically by the learner thread.
    The standard Python data strucuture "Queue" is thread-safe.
    """

    """Holds one FIFO buffer (implemented as a queue) per port."""
    def __init__(self, sid: int, num_ports: int):
        self.switch_id = sid
        # index 0 is unused to let us use 1-based indexing
        self.buffers = [None] + [Queue() for _ in range(num_ports)]

    def put(self, port: int, value: int):
        """Add one telemetry value (queue length) in the port's buffer"""
        self.buffers[port].put(value)

    def drain_all(self, port: int):
        """Drain the entire buffer for a port (FIFO) and return a list of ints."""
        q = self.buffers[port]
        items = []
        while True:
            try:
                items.append(q.get_nowait())
            except Empty:
                break
        return items
