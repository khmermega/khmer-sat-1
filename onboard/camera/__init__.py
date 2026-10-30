"""Optical payload: camera adapters, processing pipeline and capture scheduling."""

from .base import Camera, CameraConfig, CameraError, RawFrame
from .mock import MockCamera

__all__ = ["Camera", "CameraConfig", "CameraError", "MockCamera", "RawFrame"]
