"""Configuration applicative typée, chargée depuis le fichier .env.

La config est centralisée ici via pydantic-settings. En production, le service
systemd injectera les variables ; en dev, on lit /srv/nyris/config/.env (chemin
surchargeable via la variable d'environnement NYRIS_ENV_FILE).
"""

from __future__ import annotations

import os
from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("NYRIS_ENV_FILE", "/srv/nyris/config/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Nyris"
    app_env: str = "production"
    debug: bool = False
    log_level: str = "INFO"

    # Base de données (obligatoire)
    database_url: str

    # Frais par défaut (V1 = flat_rate)
    default_fee_model: str = "flat_rate"
    default_fee_currency: str = "EUR"
    default_entry_fee_rate: Decimal = Decimal("0.001")
    default_exit_fee_rate: Decimal = Decimal("0.001")


settings = Settings()
