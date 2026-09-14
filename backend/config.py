import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/roadwatch.db")
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))
    api_key: str = os.getenv("API_KEY", "")
    demo_enabled: bool = os.getenv("DEMO_ENABLED", "true").lower() == "true"
    detector_url: str = os.getenv("DETECTOR_URL", "http://127.0.0.1:8011")
    cooldown: int = int(os.getenv("EVENT_COOLDOWN_SECONDS", "120"))
    lease_seconds: int = int(os.getenv("JOB_LEASE_SECONDS", "180"))
    redis_url: str = os.getenv("REDIS_URL", "")
    mqtt_broker: str = os.getenv("MQTT_BROKER", "")
    mqtt_topic: str = os.getenv("MQTT_TOPIC", "roadwatch/metrics")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
    llm_model: str = os.getenv("LLM_MODEL", "qwen2.5:7b")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")


settings = Settings()
