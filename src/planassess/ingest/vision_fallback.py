"""Tier 2 vision-LLM fallback (optional, OFF by default).

Used only by the raster adapter for regions still unresolved after offline
Tier 1. Hard rules baked in:

* Disabled by default — the tool must run end to end with this off, in which case
  this module is a no-op and unresolved fields flow to the gap report.
* Never send the whole plan when a crop will do — callers pass cropped regions.
* The model is configurable (default ``claude-sonnet-4-6`` from settings).

This module constructs the request and parses the response; the network call is
isolated in ``_call`` so the offline/disabled paths are fully testable without
the Anthropic SDK installed.
"""

from __future__ import annotations

import base64
from typing import Any

import numpy as np

from ..config.models import Settings

_SCHEDULE_PROMPT = (
    "You are reading a cropped region of a residential building plan. Transcribe "
    "any window or door SCHEDULE rows you can see, one per line, verbatim, using "
    "pipe '|' separators between columns (id, room, orientation, size, frame, "
    "glazing, U-value, SHGC). If there is no schedule, reply with NONE. Do not "
    "invent values."
)


class VisionFallback:
    def __init__(self, settings: Settings):
        self.settings = settings.vision_llm

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def read_schedule(self, image_bgr: np.ndarray, region: tuple[int, int, int, int] | None = None) -> list[str]:
        """Return schedule text lines from a (cropped) region, or [] when disabled."""
        if not self.enabled:
            return []  # offline-first guarantee: no network, nothing auto-filled
        crop = self._crop(image_bgr, region)
        text = self._call(_SCHEDULE_PROMPT, crop)
        if not text or text.strip().upper() == "NONE":
            return []
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    # --- internals ----------------------------------------------------------

    @staticmethod
    def _crop(image: np.ndarray, region: tuple[int, int, int, int] | None) -> np.ndarray:
        if region is None:
            return image
        x0, y0, x1, y1 = region
        return image[y0:y1, x0:x1]

    @staticmethod
    def _png_b64(image: np.ndarray) -> str:
        import cv2

        ok, buf = cv2.imencode(".png", image)
        if not ok:  # pragma: no cover
            raise RuntimeError("Failed to encode crop to PNG.")
        return base64.standard_b64encode(buf.tobytes()).decode("ascii")

    def _client(self) -> Any:  # pragma: no cover - requires anthropic + network
        from anthropic import Anthropic

        return Anthropic()

    def _call(self, prompt: str, image: np.ndarray) -> str | None:  # pragma: no cover
        client = self._client()
        b64 = self._png_b64(image)
        msg = client.messages.create(
            model=self.settings.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": "image/png", "data": b64}},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        parts = [b.text for b in msg.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts) if parts else None
