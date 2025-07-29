"""
Configuration manager for upload settings
"""

import os
import json
from typing import Dict, Any
from config.settings import DEFAULT_NUM_WORKERS, DEFAULT_FILES_PER_WORKER


class UploadConfigManager:
    """Manages upload configuration persistence"""

    def __init__(self):
        """Initialize config manager"""
        self.config_file = os.path.join(os.path.expanduser('~'), '.zymtools_upload_config.json')
        self._default_config = {
            'num_workers': DEFAULT_NUM_WORKERS,
            'files_per_worker': DEFAULT_FILES_PER_WORKER,
            'use_existing_folders': True  # Default: use existing folders when found
        }

    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file

        Returns:
            Configuration dictionary
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                # Validate and merge with defaults
                validated_config = self._validate_config(config)
                return validated_config
            else:
                # Return default config if file doesn't exist
                return self._default_config.copy()

        except Exception as e:
            print(f"❌ Error loading upload config: {e}")
            return self._default_config.copy()

    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        Save configuration to file

        Args:
            config: Configuration dictionary to save

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate config before saving
            validated_config = self._validate_config(config)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(validated_config, f, indent=2)

            print(f"✅ Upload config saved: {validated_config}")
            return True

        except Exception as e:
            print(f"❌ Error saving upload config: {e}")
            return False

    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate configuration values

        Args:
            config: Configuration to validate

        Returns:
            Validated configuration
        """
        from config.settings import (MIN_NUM_WORKERS, MAX_NUM_WORKERS,
                                    MIN_FILES_PER_WORKER, MAX_FILES_PER_WORKER)

        validated = self._default_config.copy()

        # Validate num_workers
        if 'num_workers' in config:
            num_workers = config['num_workers']
            if isinstance(num_workers, int) and MIN_NUM_WORKERS <= num_workers <= MAX_NUM_WORKERS:
                validated['num_workers'] = num_workers

        # Validate files_per_worker
        if 'files_per_worker' in config:
            files_per_worker = config['files_per_worker']
            if isinstance(files_per_worker, int) and MIN_FILES_PER_WORKER <= files_per_worker <= MAX_FILES_PER_WORKER:
                validated['files_per_worker'] = files_per_worker

        # Validate use_existing_folders (boolean)
        if 'use_existing_folders' in config:
            use_existing_folders = config['use_existing_folders']
            if isinstance(use_existing_folders, bool):
                validated['use_existing_folders'] = use_existing_folders

        return validated

    def get_num_workers(self) -> int:
        """Get configured number of workers"""
        config = self.load_config()
        return config.get('num_workers', DEFAULT_NUM_WORKERS)

    def get_files_per_worker(self) -> int:
        """Get configured files per worker"""
        config = self.load_config()
        return config.get('files_per_worker', DEFAULT_FILES_PER_WORKER)

    def get_use_existing_folders(self) -> bool:
        """Get configured folder conflict handling behavior"""
        config = self.load_config()
        return config.get('use_existing_folders', True)

    def set_use_existing_folders(self, use_existing: bool) -> bool:
        """
        Set folder conflict handling behavior

        Args:
            use_existing: True to use existing folders, False to create new ones

        Returns:
            True if successful
        """
        config = self.load_config()
        config['use_existing_folders'] = use_existing
        return self.save_config(config)

    def update_workers_config(self, num_workers: int, files_per_worker: int) -> bool:
        """
        Update workers configuration

        Args:
            num_workers: Number of workers
            files_per_worker: Files per worker

        Returns:
            True if successful
        """
        config = self.load_config()
        config.update({
            'num_workers': num_workers,
            'files_per_worker': files_per_worker
        })
        return self.save_config(config)

    def reset_to_defaults(self) -> bool:
        """Reset configuration to defaults"""
        return self.save_config(self._default_config.copy())


# Global instance
upload_config_manager = UploadConfigManager()
