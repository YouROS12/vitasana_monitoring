"""
Configuration loader for Vitasana Monitoring.
Uses YAML format for cleaner, more readable configuration.
"""

import yaml
import os
from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class Config:
    """Singleton configuration manager."""
    
    _instance: Optional['Config'] = None
    _data: dict = {}
    _project_root: Path = None
    
    def __new__(cls, config_path: Optional[str] = None) -> 'Config':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._project_root = Path(__file__).resolve().parent.parent.parent
            cls._instance._load(config_path)
        return cls._instance
    
    def _load(self, config_path: Optional[str] = None) -> None:
        """Load configuration from YAML file."""
        if config_path:
            path = Path(config_path)
        else:
            path = self._project_root / "config.yaml"
        
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            self._data = yaml.safe_load(f)
        
        # Validate required sections
        required = ['general', 'api', 'credentials', 'scraper']
        missing = [s for s in required if s not in self._data]
        if missing:
            raise ValueError(f"Missing required config sections: {missing}")
        
        logger.info(f"Configuration loaded from {path}")
    
    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get a nested config value using dot notation.
        Example: config.get('api', 'timeout') -> config['api']['timeout']
        """
        value = self._data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def get_int(self, *keys: str, default: int = 0) -> int:
        """Get integer value."""
        value = self.get(*keys, default=default)
        return int(value) if value is not None else default
    
    def get_float(self, *keys: str, default: float = 0.0) -> float:
        """Get float value."""
        value = self.get(*keys, default=default)
        return float(value) if value is not None else default
    
    def get_bool(self, *keys: str, default: bool = False) -> bool:
        """Get boolean value."""
        value = self.get(*keys, default=default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        return bool(value)
    
    def get_list(self, *keys: str, default: list = None) -> list:
        """Get list value."""
        value = self.get(*keys, default=default or [])
        return value if isinstance(value, list) else [value]
    
    @property
    def project_root(self) -> Path:
        """Get project root directory."""
        return self._project_root
    
    @property
    def data_dir(self) -> Path:
        """Get data directory path, creating if needed."""
        dir_name = self.get('general', 'data_dir', default='data')
        path = self._project_root / dir_name
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def db_path(self) -> Path:
        """Get database file path."""
        db_name = self.get('general', 'database', default='vitasana.db')
        return self.data_dir / db_name
    
    @property
    def log_path(self) -> Path:
        """Get log file path."""
        log_name = self.get('general', 'log_file', default='vitasana.log')
        return self._project_root / log_name


# Global config instance (initialized on first import)
def get_config() -> Config:
    """Get the global config instance."""
    return Config()
