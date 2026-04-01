from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from json import JSONEncoder
from uuid import UUID

from yarl import URL


class Config(BaseSettings):
    sqlite_path: Path = Field(alias="SQLITE_PATH")
    bot_token: str = Field(alias="BOT_TOKEN")
    booking_base_url: URL = Field(alias="BOOKING_BASE_URL")

    @field_validator("booking_base_url", mode="before")
    def parse_url(cls, v):
        if isinstance(v, str):
            return URL(v)
        return v

    @field_validator("api_base_url", mode="before")
    def parse_url2(cls, v):
        if isinstance(v, str):
            return URL(v)
        return v

    model_config = SettingsConfigDict(env_file=".env")


old_default = JSONEncoder.default


def new_default(self, obj):
    if isinstance(obj, UUID):
        return str(obj)
    return old_default(self, obj)


JSONEncoder.default = new_default


config = Config()
