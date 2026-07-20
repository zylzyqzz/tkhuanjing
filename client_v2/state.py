from __future__ import annotations

from enum import StrEnum


class ClientState(StrEnum):
    SIGNED_OUT = "SIGNED_OUT"
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    CHECKED = "CHECKED"
    NEEDS_REPAIR = "NEEDS_REPAIR"
    REPAIRING = "REPAIRING"
    RECHECKING = "RECHECKING"
    READY = "READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


BUSY_STATES = {ClientState.CHECKING, ClientState.REPAIRING, ClientState.RECHECKING}


ALLOWED_TRANSITIONS = {
    ClientState.SIGNED_OUT: {ClientState.IDLE},
    ClientState.IDLE: {ClientState.CHECKING, ClientState.SIGNED_OUT},
    ClientState.CHECKING: {ClientState.CHECKED, ClientState.NEEDS_REPAIR, ClientState.READY, ClientState.FAILED, ClientState.CANCELLED},
    ClientState.CHECKED: {ClientState.CHECKING, ClientState.NEEDS_REPAIR, ClientState.READY},
    ClientState.NEEDS_REPAIR: {ClientState.REPAIRING, ClientState.CHECKING},
    ClientState.REPAIRING: {ClientState.RECHECKING, ClientState.FAILED, ClientState.CANCELLED},
    ClientState.RECHECKING: {ClientState.NEEDS_REPAIR, ClientState.READY, ClientState.FAILED, ClientState.CANCELLED},
    ClientState.READY: {ClientState.CHECKING, ClientState.SIGNED_OUT},
    ClientState.FAILED: {ClientState.IDLE, ClientState.CHECKING},
    ClientState.CANCELLED: {ClientState.IDLE, ClientState.CHECKING},
}


class StateMachine:
    def __init__(self, initial: ClientState = ClientState.IDLE):
        self.state = initial

    def transition(self, target: ClientState) -> None:
        if target == self.state:
            return
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid state transition: {self.state} -> {target}")
        self.state = target

    @property
    def busy(self) -> bool:
        return self.state in BUSY_STATES
