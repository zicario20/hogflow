from hogflow.core import (
    ConfigurationError,
    DependencyUnavailableError,
    HogFlowError,
    InputDataError,
)


def test_hogflow_error_inherits_from_exception() -> None:
    assert issubclass(HogFlowError, Exception)


def test_expected_application_errors_inherit_from_hogflow_error() -> None:
    expected_errors = (
        ConfigurationError,
        DependencyUnavailableError,
        InputDataError,
    )

    assert all(issubclass(error_type, HogFlowError) for error_type in expected_errors)
