"""Errors the simulator reports to the operator."""

from __future__ import annotations


class SimulatorError(Exception):
    """A usage or payload error. ``exit_code`` is what the CLI returns."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class IngestError(SimulatorError):
    """The ingest POST did not succeed. Distinct from a bad invocation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=1)
