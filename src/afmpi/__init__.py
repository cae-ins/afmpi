"""Public API for :mod:`afmpi`."""

from .design_base import Design
from .estimation import estimate
from .hadamard import sylvester
from .pps import PPSDesign
from .replicate_design import ReplicateDesign
from .results import EstimationResult
from .specification import Specification
from .survey_design import Stage, SurveyDesign
from .testing import HypothesisTest
from .variance import DesignDegrees, LonelyPSUWarning

__all__ = [
    "Design",
    "DesignDegrees",
    "EstimationResult",
    "HypothesisTest",
    "LonelyPSUWarning",
    "PPSDesign",
    "ReplicateDesign",
    "Specification",
    "Stage",
    "SurveyDesign",
    "estimate",
    "sylvester",
]
__version__ = "0.3.0"
