from enum import Enum

class Bound(Enum):
    LOWER_BOUND = 0
    UPPER_BOUND = 1

class PortAction(Enum):
    INCREASE = 0
    DECREASE = 1
    UNCHANGED = 2

class TwoPortsActions(Enum):
    ACTION_INCREASE_DECREASE = 0
    ACTION_DECREASE_INCREASE = 1
    ACTION_NO_CHANGE = 2
