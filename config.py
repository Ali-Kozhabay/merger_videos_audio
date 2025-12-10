from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_ID: int
    API_HASH: str
    BOT_NAME: str
    BOT_TOKEN: str
    API_KEY: str
    RUNWAY_API_KEY: str | None = None
    RUNWAY_MODEL: str = "veo3.1_fast"
    RUNWAY_SIZE: str = "1280:720"
    RUNWAY_IMAGE_MODEL: str = "gen4_image_turbo"
    RUNWAY_SCENES: int = 9
    RUNWAY_SCENE_SECONDS: int = 10
    class Config:
        env_file = ".env"


settings = Settings()
