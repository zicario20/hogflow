"""Phase 10.1 bounded local runtime health and supervision foundation."""

from hogflow.runtime.errors import (
    ProductionRuntimeConfigurationError,
    ProductionRuntimeError,
    ProductionRuntimeLifecycleError,
    RuntimeRestartLimitError,
    UnsafeRuntimeRestartError,
)
from hogflow.runtime.health import RuntimeHealthManager
from hogflow.runtime.memory import StandardProcessMemoryProbe
from hogflow.runtime.models import (
    ComponentHealth,
    ComponentHealthState,
    ProcessMemorySnapshot,
    ProductionRuntimeConfiguration,
    RuntimeComponent,
    RuntimeDiagnosticsSnapshot,
    RuntimeHealthState,
    RuntimeHeartbeat,
    RuntimeIssue,
    RuntimeIssueCategory,
    RuntimeIssueDisposition,
    RuntimeWorkerState,
)
from hogflow.runtime.ports import (
    ProcessMemoryProbe,
    SupervisedCountingPipeline,
    SupervisedRuntimeAccess,
)
from hogflow.runtime.supervisor import ProductionRuntimeSupervisor

__all__ = [
    "ComponentHealth",
    "ComponentHealthState",
    "ProcessMemoryProbe",
    "ProcessMemorySnapshot",
    "ProductionRuntimeConfiguration",
    "ProductionRuntimeConfigurationError",
    "ProductionRuntimeError",
    "ProductionRuntimeLifecycleError",
    "ProductionRuntimeSupervisor",
    "RuntimeComponent",
    "RuntimeDiagnosticsSnapshot",
    "RuntimeHealthManager",
    "RuntimeHealthState",
    "RuntimeHeartbeat",
    "RuntimeIssue",
    "RuntimeIssueCategory",
    "RuntimeIssueDisposition",
    "RuntimeRestartLimitError",
    "RuntimeWorkerState",
    "StandardProcessMemoryProbe",
    "SupervisedCountingPipeline",
    "SupervisedRuntimeAccess",
    "UnsafeRuntimeRestartError",
]
