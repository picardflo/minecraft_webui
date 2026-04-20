from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mc_host: str = "localhost"
    mc_port: int = 25565
    mc_log_path: str = "/logs/latest.log"
    host_proc: str | None = None
    settings_path: str = "/data/settings.json"
    admin_password: str = "changeme"
    secret_key: str = "change-me"

    model_config = {"env_file": ".env"}


settings = Settings()
