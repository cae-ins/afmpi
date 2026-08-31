"""Public API for :mod:`afmpi`."""

from .census_design import CensusDesign
from .design_base import Design
from .estimation import LazyEstimation, estimate
from .execution_config import ExecutionConfig
from .hadamard import sylvester
from .io import ParquetSource, from_parquet, to_parquet, to_stata
from .missing import MissingReport
from .pps import PPSDesign
from .replicate_design import ReplicateDesign
from .results import EstimationResult
from .specification import Specification
from .survey_design import Stage, SurveyDesign
from .testing import HypothesisTest
from .variance import DesignDegrees, LonelyPSUWarning

__all__ = [
    "CensusDesign",
    "Design",
    "DesignDegrees",
    "EstimationResult",
    "ExecutionConfig",
    "HypothesisTest",
    "LazyEstimation",
    "LonelyPSUWarning",
    "MissingReport",
    "PPSDesign",
    "ParquetSource",
    "ReplicateDesign",
    "Specification",
    "Stage",
    "SurveyDesign",
    "estimate",
    "from_parquet",
    "sylvester",
    "to_parquet",
    "to_stata",
]
__version__ = "1.0.1"
