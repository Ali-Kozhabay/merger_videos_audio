from typing import Dict, List

user_videos: Dict[int, List] = {}
user_audios: Dict[int, str] = {}


def clear_user_data(user_id: int) -> None:
    user_videos.pop(user_id, None)
    user_audios.pop(user_id, None)
