import asyncio
import logging
import os
import tempfile
from typing import Optional

import requests
from runwayml import RunwayML

logger = logging.getLogger(__name__)


class RunwayError(RuntimeError):
    pass


def _ensure_api_secret(api_key: str) -> None:
    os.environ["RUNWAYML_API_SECRET"] = api_key


def _extract_video_url(task) -> Optional[str]:
    outputs = getattr(task, "output", None) or getattr(task, "outputs", None)

    # Case 1: list of strings
    if isinstance(outputs, list) and outputs:
        if isinstance(outputs[0], str):
            return outputs[0]

        if isinstance(outputs[0], dict):
            return (
                outputs[0].get("url") or
                outputs[0].get("video") or
                outputs[0].get("video_url")
            )

    # Case 2: dict
    if isinstance(outputs, dict):
        return (
            outputs.get("url") or
            outputs.get("video") or
            outputs.get("video_url")
        )

    # Case 3: fallback to model_dump
    if hasattr(task, "model_dump"):
        data = task.model_dump()
        result = data.get("result") or data.get("output") or data.get("outputs")

        if isinstance(result, list) and result:
            if isinstance(result[0], str):
                return result[0]
            if isinstance(result[0], dict):
                return (
                    result[0].get("url") or
                    result[0].get("video") or
                    result[0].get("video_url")
                )

        if isinstance(result, dict):
            return (
                result.get("url") or
                result.get("video") or
                result.get("video_url")
            )

    return None


def _create_and_wait(api_key: str, prompt: str, duration: int, model: str, ratio: str):
    _ensure_api_secret(api_key)
    client = RunwayML()
    task = client.text_to_video.create(
        model=model,
        prompt_text=prompt,
        ratio=ratio,
        duration=duration,
    ).wait_for_task_output()
    return task


def _download_video(url: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    path = tmp.name
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                tmp.write(chunk)
    tmp.close()
    return path


async def generate_runway_video(
    *,
    api_key: str,
    prompt: str,
    duration: int,
    model: str,
    ratio: str,
    download: bool = True,
) -> tuple[str, Optional[str]]:
    """
    Returns (video_path_or_url, ratio_if_known).
    If download=False, returns the remote URL only.
    """
    task = await asyncio.to_thread(_create_and_wait, api_key, prompt, duration, model, ratio)
    video_url = _extract_video_url(task)
    if not video_url:
        raise RunwayError(f"Runway task completed without video URL: {task}")

    if not download:
        return video_url, ratio

    path = await asyncio.to_thread(_download_video, video_url)
    return path, ratio
