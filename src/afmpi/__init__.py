"""Public API for :mod:`afmpi`."""

from .estimation import estimate
from .results import EstimationResult
from .specification import Specification
from .survey_design import SurveyDesign
from .variance import DesignDegrees

__all__ = [
    "DesignDegrees",
    "EstimationResult",
    "Specification",
    "SurveyDesign",
    "estimate",
]
__version__ = "0.2.0"
