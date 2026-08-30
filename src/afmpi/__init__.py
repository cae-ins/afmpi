"""Public API for :mod:`afmpi`."""

from .estimation import estimate
from .pps import PPSDesign
from .results import EstimationResult
from .specification import Specification
from .survey_design import Stage, SurveyDesign
from .variance import DesignDegrees, LonelyPSUWarning

__all__ = [
    "DesignDegrees",
    "EstimationResult",
    "LonelyPSUWarning",
    "PPSDesign",
    "Specification",
    "Stage",
    "SurveyDesign",
    "estimate",
]
__version__ = "0.3.0"
