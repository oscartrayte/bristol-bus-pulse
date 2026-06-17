"""Configuration management for Bristol Bus Pulse."""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str
    db_echo: bool = False
    
    # BODS API
    bods_api_key: str
    gtfs_rt_feed_url: str
    naptan_feed_url: str
    gtfs_timetable_url: Optional[str] = None
    
    # Operators
    operator_codes: str = "FBUS"  # Space-separated
    
    # Ingestion
    ingestion_interval_seconds: int = 30
    snapshot_interval_seconds: int = 300
    historical_retention_days: int = 30
    
    # Processing
    delay_thresholds_seconds: str = "60,300,600"
    heatmap_cell_size_meters: int = 500
    heatmap_decay_hours: float = 2.0
    
    # Server
    environment: str = "development"
    log_level: str = "INFO"
    debug: bool = True
    
    # CORS
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"
    
    # Rate Limiting
    rate_limit_requests: int = 10000
    rate_limit_period_seconds: int = 3600
    
    # Performance
    max_workers: int = 4
    batch_size: int = 1000
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def get_operator_codes(self) -> list[str]:
        """Get parsed operator codes."""
        return [code.strip() for code in self.operator_codes.split(",")]
    
    @property
    def get_delay_thresholds(self) -> list[int]:
        """Get parsed delay thresholds in seconds."""
        return [int(t) for t in self.delay_thresholds_seconds.split(",")]
    
    @property
    def get_allowed_origins(self) -> list[str]:
        """Get parsed allowed origins."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]


settings = Settings()
