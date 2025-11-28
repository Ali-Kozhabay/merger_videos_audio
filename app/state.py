from typing import Dict, List

user_videos: Dict[int, List] = {}
user_audios: Dict[int, str] = {}
user_transcripts: Dict[int, str] = {}
user_paraphrases: Dict[int, str] = {}
pending_video_from_text: Dict[int, bool] = {}


def clear_user_data(user_id: int) -> None:
    user_videos.pop(user_id, None)
    user_audios.pop(user_id, None)
    user_paraphrases.pop(user_id, None)
    pending_video_from_text.pop(user_id, None)


def clear_user_videos(user_id: int) -> None:
    user_videos.pop(user_id, None)


def clear_user_audio(user_id: int) -> None:
    user_audios.pop(user_id, None)


def clear_user_paraphrase(user_id: int) -> None:
    user_paraphrases.pop(user_id, None)


def clear_pending_video_from_text(user_id: int) -> None:
    pending_video_from_text.pop(user_id, None)
