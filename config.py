from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_ID: int
    API_HASH: str
    BOT_NAME: str
    BOT_TOKEN: str

    class Config:
        env_file = ".env"


settings = Settings()