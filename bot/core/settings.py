import os
import json
import yaml
import asyncio
from copy import deepcopy

class SettingsManager:
    def __init__(self, config_path: str, override_path: str):
        self.config_path = config_path
        self.override_path = override_path
        self._lock = asyncio.Lock()
        self._base = {}
        self._override = {}
        self._merged = {}
        self._override_mtime = 0.0

    async def load(self):
        async with self._lock:
            self._base = self._load_yaml(self.config_path)
            self._override = self._load_json(self.override_path)
            self._merged = self._merge(deepcopy(self._base), deepcopy(self._override))
            self._override_mtime = self._get_mtime(self.override_path)

    async def reload_if_changed(self) -> bool:
        mtime = self._get_mtime(self.override_path)
        if mtime <= 0:
            return False
        if mtime == self._override_mtime:
            return False
        await self.load()
        return True

    async def set_override(self, path: str, value):
        async with self._lock:
            self._override = self._load_json(self.override_path)
            self._set_path(self._override, path, value)
            os.makedirs(os.path.dirname(self.override_path), exist_ok=True)
            with open(self.override_path, "w", encoding="utf-8") as f:
                json.dump(self._override, f, ensure_ascii=False, indent=2)
            self._merged = self._merge(deepcopy(self._base), deepcopy(self._override))
            self._override_mtime = self._get_mtime(self.override_path)

    async def replace_overrides(self, data: dict):
        async with self._lock:
            os.makedirs(os.path.dirname(self.override_path), exist_ok=True)
            with open(self.override_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._override = data
            self._merged = self._merge(deepcopy(self._base), deepcopy(self._override))
            self._override_mtime = self._get_mtime(self.override_path)

    def dump(self) -> dict:
        return deepcopy(self._merged)

    def get(self, dotted: str, default=None):
        node = self._merged
        for part in dotted.split("."):
            if not isinstance(node, dict):
                return default
            if part not in node:
                return default
            node = node[part]
        return node

    def get_int(self, dotted: str, default: int = 0) -> int:
        v = self.get(dotted, default)
        try:
            return int(v)
        except Exception:
            return default

    def get_bool(self, dotted: str, default: bool = False) -> bool:
        v = self.get(dotted, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in {"true", "1", "yes", "on"}
        return bool(v)

    def _load_yaml(self, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data

    def _load_json(self, path: str) -> dict:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _merge(self, base: dict, override: dict) -> dict:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                base[k] = self._merge(base[k], v)
            else:
                base[k] = v
        return base

    def _set_path(self, root: dict, dotted: str, value):
        parts = dotted.split(".")
        node = root
        for p in parts[:-1]:
            if p not in node or not isinstance(node[p], dict):
                node[p] = {}
            node = node[p]
        node[parts[-1]] = value

    def _get_mtime(self, path: str) -> float:
        try:
            return os.path.getmtime(path)
        except Exception:
            return 0.0
