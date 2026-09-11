"""Declarative, side-effect-free ingestion Profile compilation and selection."""

from .compiler import CompiledProfileSet, ProfileCompiler, ResolvedPlan, evaluate_condition
from .contracts import AXES, ProfileSet, ResolutionRequest
from .errors import ProfileError, ProfileErrorCode
from .parser import ProfileParser
from .resolver import ProfileResolver, ResolutionRecord

__all__ = ["AXES", "CompiledProfileSet", "ProfileCompiler", "ProfileError", "ProfileErrorCode", "ProfileParser", "ProfileResolver", "ProfileSet", "ResolvedPlan", "ResolutionRecord", "ResolutionRequest", "evaluate_condition"]
