"""RequestProfiler - Indian Language Request Profiling Module"""

__version__ = "1.0.0"
__author__ = "Akshansh247"

from .profiler import RequestProfiler
from .schemas import RequestProfile, LanguageDetection

__all__ = ["RequestProfiler", "RequestProfile", "LanguageDetection"]
