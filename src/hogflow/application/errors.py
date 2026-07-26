"""Expected failures at the operator application boundary."""

from hogflow.core import HogFlowError


class OperatorInputError(HogFlowError):
    """Raised when operator-entered presentation data cannot form a command."""


ExpectedOperatorError = HogFlowError

__all__ = ["ExpectedOperatorError", "OperatorInputError"]
