from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_ID: int
    API_HASH: str
    PHONE_NUMBER: str
    BOT_NAME: str

    class Config:
        env_file = ".env"


settings = Settings