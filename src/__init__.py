"""
__init__.py
===========
Initialize the simulation package.
"""

from .opendsss_interface import OpenDSSInterface
from .hybrid_metering import HybridMeteringSystem, Meter, MeterType
from .load_profiles import (
    HybridGridLoadManager, 
    LoadProfileGenerator, 
    NodeLoadProfile,
    CustomerType
)
from .ntl_injection import NTLInjectionEngine, NTLType, NTLEvent
from .simulation_engine import HybridGridDigitalTwin, SimulationConfig
from .data_sources import (
    DataSourcePaths,
    UtilityDataBundle,
    UtilityDataLoader,
    load_optional_utility_data,
)
from .data_quality import DataQualityManager, DataQualityIssue, DataQualityReport
from .physics_informed import FeederPhysicsValidator, PhysicsCheckResult
from .federated_learning import (
    ClientModelState,
    FederatedAveragingAggregator,
    FederatedClient,
    FederatedLearningConfig,
    FederatedLearningReport,
)
from .explainability import ExplainabilityEngine, ExplainabilityReport, FeatureImpact
from .deployment_readiness import (
    DeploymentReadinessCheck,
    DeploymentReadinessEvaluator,
    DeploymentReadinessReport,
)

__all__ = [
    'OpenDSSInterface',
    'HybridMeteringSystem',
    'Meter',
    'MeterType',
    'HybridGridLoadManager',
    'LoadProfileGenerator',
    'NodeLoadProfile',
    'CustomerType',
    'NTLInjectionEngine',
    'NTLType',
    'NTLEvent',
    'HybridGridDigitalTwin',
    'SimulationConfig',
    'DataSourcePaths',
    'UtilityDataBundle',
    'UtilityDataLoader',
    'load_optional_utility_data',
    'DataQualityManager',
    'DataQualityIssue',
    'DataQualityReport',
    'FeederPhysicsValidator',
    'PhysicsCheckResult',
    'ClientModelState',
    'FederatedAveragingAggregator',
    'FederatedClient',
    'FederatedLearningConfig',
    'FederatedLearningReport',
    'ExplainabilityEngine',
    'ExplainabilityReport',
    'FeatureImpact',
    'DeploymentReadinessCheck',
    'DeploymentReadinessEvaluator',
    'DeploymentReadinessReport',
]

__version__ = "1.1.0"
