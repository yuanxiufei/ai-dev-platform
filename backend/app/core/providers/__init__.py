"""
Provider 注册表 — 自动发现 + 统一管理

借鉴 AstrBot 的 ProviderManager 设计：
1. 自动扫描 providers/ 目录下的所有 Provider 子类
2. 按 ProviderConfig 元数据注册
3. 统一接口：list_all(), get_candidates(), get_by_name()
4. 支持运行时动态添加/移除 Provider
5. 环境变量自动注入 API 密钥

使用方式：
  registry = ProviderRegistry.auto_discover()
  candidates = registry.get_candidates()  # 获取所有可用 Provider
  provider = registry.get_by_name("openai")  # 按名获取
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
import pkgutil
from typing import Type

from app.core.providers.base import BaseProvider, ProviderConfig

logger = logging.getLogger("provider.registry")


# ── 内置 Provider 类映射 ──────────────────────────────────

# 每个 Provider 在 sources/ 目录下是一个独立模块
# 模块名 → Provider 类名 映射
_BUILTIN_PROVIDERS: dict[str, str] = {
    "openai": "OpenAIProvider",
    "anthropic": "AnthropicProvider",
    "deepseek": "DeepSeekProvider",
    "replicate": "ReplicateProvider",
    "zhipu": "ZhipuProvider",
    "qwen": "QwenProvider",
    "ollama": "OllamaProvider",
}


# ── 默认配置工厂 ─────────────────────────────────────────


def _default_configs() -> list[ProviderConfig]:
    """默认提供商配置（密钥从 os.environ 注入，确保 load_dotenv 已执行）"""
    # 显式加载 .env：确保在任何进程上下文中都能读到密钥
    # 路径：providers/__init__.py → core/ → app/ → backend/ → root/
    from pathlib import Path as _Path
    _dotenv_path = _Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
    if _dotenv_path.exists():
        from dotenv import load_dotenv as _load_dotenv
        _load_dotenv(_dotenv_path, override=True)

    # ⚠️ 必须用 os.getenv 读取密钥（而非 settings）
    # 因为 pydantic-settings 会缓存启动时的值，
    # 经 load_dotenv(override=True) 后 os.getenv 能读到最新值
    api_keys: dict[str, str] = {
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
        "deepseek": os.getenv("DEEPSEEK_API_KEY", ""),
        "replicate": os.getenv("REPLICATE_API_KEY", ""),
        "zhipu": os.getenv("ZHIPU_API_KEY", ""),
        "qwen": os.getenv("QWEN_API_KEY", ""),
        "ollama": os.getenv("OLLAMA_API_KEY", ""),
        "azure": os.getenv("AZURE_OPENAI_API_KEY", ""),
    }

    configs = [
        ProviderConfig(
            name="openai",
            display_name="OpenAI",
            base_url="https://api.openai.com",
            models=["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            priority=80,
            strengths=["ui_design", "frontend_code", "general_code"],
        ),
        ProviderConfig(
            name="anthropic",
            display_name="Anthropic Claude",
            base_url="https://api.anthropic.com",
            models=["claude-sonnet-4-20250514", "claude-3-opus-20240229"],
            priority=75,
            strengths=["ui_design", "frontend_code", "general_code"],
        ),
        ProviderConfig(
            name="deepseek",
            display_name="DeepSeek",
            base_url=os.getenv("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com"),
            models=["deepseek-chat", "deepseek-coder"],
            priority=70,
            strengths=["backend_code", "general_code"],
        ),
        ProviderConfig(
            name="azure",
            display_name="Azure OpenAI",
            base_url="https://{resource}.openai.azure.com",
            models=["gpt-4o"],
            priority=65,
            strengths=["general_code"],
        ),
        ProviderConfig(
            name="ollama",
            display_name="Ollama (本地)",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            models=["llama3.1:8b", "qwen2.5-coder:7b", "gemma2:27b"],
            priority=60,
            strengths=["ui_design", "frontend_code", "general_code"],
            extra_config={"no_auth_required": True},
        ),
        ProviderConfig(
            name="replicate",
            display_name="Replicate",
            base_url="https://api.replicate.com",
            models=["cogvideox-5b", "stable-video-diffusion"],
            priority=60,
            strengths=["short_video"],
        ),
        ProviderConfig(
            name="zhipu",
            display_name="智谱 GLM-4",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            models=["glm-4-plus", "glm-4v"],
            priority=55,
            strengths=["general_code"],
        ),
        ProviderConfig(
            name="qwen",
            display_name="通义千问",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            models=["qwen-max", "qwen-plus"],
            priority=55,
            strengths=["general_code"],
        ),
    ]

    # 密钥注入（优先从 settings 读取，fallback 到 os.getenv）
    for cfg in configs:
        key = api_keys.get(cfg.name)
        if key is not None:
            cfg.api_key = key

    return configs


# ── Provider 注册表 ───────────────────────────────────────


class ProviderRegistry:
    """
    Provider 自动发现注册表

    特性：
    - 自动扫描 providers/ 目录加载所有 Provider 类
    - 按优先级排序
    - 运行时增删 Provider
    - 环境变量密钥自动注入
    - 健康状态追踪
    """

    def __init__(self):
        self._providers: list[BaseProvider] = []
        self._provider_map: dict[str, BaseProvider] = {}
        self._configs: list[ProviderConfig] = []
        self._initialized: bool = False

    # ── 自动发现 ────────────────────────────────────────

    def auto_discover(
        self,
        configs: list[ProviderConfig] | None = None,
    ) -> list[BaseProvider]:
        """
        自动发现并加载所有 Provider

        流程：
        1. 加载默认配置（或自定义配置）
        2. 遍历 providers/ 目录，加载每个模块的 Provider 类
        3. 匹配配置到 Provider 类，实例化
        4. 按优先级排序
        5. 仅保留有密钥的 Provider（除非标记 no_auth_required）
        """
        if self._initialized:
            logger.debug("ProviderRegistry already initialized, skipping auto_discover")
            return self._providers

        self._configs = configs or _default_configs()
        config_map = {c.name: c for c in self._configs}

        # 动态加载 providers/ 包下的所有模块
        providers_package = "app.core.providers"
        loaded_classes: dict[str, Type[BaseProvider]] = {}

        try:
            package = importlib.import_module(providers_package)
            package_path = os.path.dirname(package.__file__ or "")

            for _, module_name, _ in pkgutil.iter_modules([package_path]):
                if module_name in ("base", "__init__"):
                    continue

                try:
                    mod = importlib.import_module(f"{providers_package}.{module_name}")
                    # 查找模块中的 BaseProvider 子类
                    for name, obj in inspect.getmembers(mod, inspect.isclass):
                        if (
                            issubclass(obj, BaseProvider)
                            and obj is not BaseProvider
                            and obj.__module__ == mod.__name__
                        ):
                            loaded_classes[module_name] = obj
                            logger.debug("Discovered provider class: %s → %s", module_name, obj.__name__)
                except Exception as e:
                    logger.warning(
                        "Failed to load provider module '%s': %s",
                        module_name, e,
                    )
        except ImportError:
            logger.warning(
                "Cannot import providers package, using built-in class map. "
                "Create providers/*.py files for auto-discovery."
            )

        # 降级：如果动态加载失败，使用内置映射
        if not loaded_classes:
            loaded_classes = self._load_builtin_classes()

        # 实例化 Provider
        for name, cls in loaded_classes.items():
            config = config_map.get(name)
            if not config:
                # 也尝试匹配 _BUILTIN_PROVIDERS 中的键
                matched = self._match_provider_name(name, config_map)
                if matched:
                    config = config_map[matched]

            if config:
                # 检查是否需要 API 密钥
                no_auth = config.extra_config.get("no_auth_required", False)
                if not config.api_key and not no_auth:
                    logger.debug(
                        "Provider '%s' has no API key configured, skipping instantiation",
                        config.name,
                    )
                    continue

                try:
                    provider = cls(config)
                    self._providers.append(provider)
                    self._provider_map[config.name] = provider
                    logger.info(
                        "Provider '%s' loaded: priority=%d, models=%s",
                        config.name, config.priority, config.models,
                    )
                except Exception as e:
                    logger.error("Failed to instantiate provider '%s': %s", config.name, e)

        # 按优先级降序排列
        self._providers.sort(key=lambda p: p.priority, reverse=True)
        self._initialized = True

        logger.info(
            "ProviderRegistry initialized: %d providers loaded",
            len(self._providers),
        )
        return self._providers

    def _load_builtin_classes(self) -> dict[str, Type[BaseProvider]]:
        """从内置映射加载 Provider 类（降级方案）"""
        classes: dict[str, Type[BaseProvider]] = {}

        # 直接 import 已知的 provider 模块
        provider_imports = {
            "openai": "app.core.providers.openai",
            "anthropic": "app.core.providers.anthropic",
            "deepseek": "app.core.providers.deepseek",
            "replicate": "app.core.providers.replicate",
            "zhipu": "app.core.providers.zhipu",
            "qwen": "app.core.providers.qwen",
            "ollama": "app.core.providers.ollama",
        }

        for name, module_path in provider_imports.items():
            try:
                mod = importlib.import_module(module_path)
                class_name = _BUILTIN_PROVIDERS[name]
                cls = getattr(mod, class_name, None)
                if cls and issubclass(cls, BaseProvider):
                    classes[name] = cls
            except Exception as e:
                logger.warning("Failed to load builtin provider '%s': %s", name, e)

        return classes

    def _match_provider_name(self, module_name: str, config_map: dict[str, ProviderConfig]) -> str | None:
        """将模块名匹配到配置名"""
        # 直接匹配
        if module_name in config_map:
            return module_name
        # 降级：检查 _BUILTIN_PROVIDERS 的反向映射
        if module_name in _BUILTIN_PROVIDERS:
            return module_name
        return None

    # ── 查询接口 ────────────────────────────────────────

    def get_candidates(self) -> list[BaseProvider]:
        """获取所有可用的 Provider 候选"""
        return [p for p in self._providers if p.is_available]

    def get_by_name(self, name: str) -> BaseProvider | None:
        """按名称获取 Provider"""
        return self._provider_map.get(name)

    def list_all(self) -> list[dict]:
        """列出所有 Provider（含状态信息）"""
        result = []
        for cfg in self._configs:
            provider = self._provider_map.get(cfg.name)
            result.append({
                "name": cfg.name,
                "display_name": cfg.display_name,
                "models": cfg.models,
                "is_configured": bool(cfg.api_key),
                "is_active": cfg.is_active,
                "is_available": provider.is_available if provider else False,
                "priority": cfg.priority,
                "strengths": cfg.strengths,
            })
        return result

    def get_config(self, name: str) -> ProviderConfig | None:
        """获取 Provider 配置"""
        for cfg in self._configs:
            if cfg.name == name:
                return cfg
        return None

    # ── 动态管理 ────────────────────────────────────────

    def _get_provider_class_map(self) -> dict[str, type[BaseProvider]]:
        """获取 Provider 类名→类对象的映射（降级到内置映射）"""
        return _get_provider_class_map()

    def force_reload(self) -> int:
        """强制重新加载所有 Provider（用于 .env 热更新后刷新密钥/端点）

        与 auto_discover 的关键区别：
        - 不检查 _initialized（始终允许重新加载）
        - 会实例化之前因缺少密钥而被跳过的 Provider
        - 更新已有 Provider 的配置 + 重建 HTTP 客户端
        """
        # 重新加载 .env 到 os.environ（确保 override）
        from pathlib import Path as _Path
        _dotenv_path = _Path(__file__).resolve().parent.parent.parent.parent.parent / ".env"
        if _dotenv_path.exists():
            from dotenv import load_dotenv as _load_dotenv
            _load_dotenv(_dotenv_path, override=True)

        # 重新生成配置（读 os.environ，获取最新值）
        self._configs = _default_configs()
        config_map = {c.name: c for c in self._configs}

        # 关闭所有现有客户端的 HTTP 连接
        for p in self._providers:
            try:
                p._client = None
            except Exception:
                pass

        # 加载 Provider 类映射
        available_classes = _get_provider_class_map()

        loaded = 0
        processed_names: set[str] = set()

        # 1. 更新已在 _provider_map 中的 Provider
        for provider_name, provider_inst in list(self._provider_map.items()):
            processed_names.add(provider_name)
            new_config = config_map.get(provider_name)
            if not new_config:
                continue
            no_auth = new_config.extra_config.get("no_auth_required", False)
            if not new_config.api_key and not no_auth:
                # 密钥仍然缺失 → 移除该 Provider
                self._providers = [p for p in self._providers if p.name != provider_name]
                del self._provider_map[provider_name]
                logger.info("Provider '%s' removed (still no API key)", provider_name)
                continue

            # 更新配置
            provider_inst.config = new_config
            provider_inst.priority = new_config.priority
            provider_inst.strengths = new_config.strengths
            provider_inst.is_available = True
            loaded += 1
            logger.info(
                "Provider '%s' reloaded: base_url=%s, api_key=%s",
                provider_name,
                new_config.base_url,
                "***" if new_config.api_key else "(none)",
            )

        # 2. 实例化之前不存在的新 Provider（首次获得密钥）
        for cfg_name, cfg in config_map.items():
            if cfg_name in processed_names:
                continue
            no_auth = cfg.extra_config.get("no_auth_required", False)
            if not cfg.api_key and not no_auth:
                continue  # 仍无密钥，跳过

            cls = available_classes.get(_BUILTIN_PROVIDERS.get(cfg_name, ""))
            if not cls:
                logger.warning("No provider class for '%s', skipping", cfg_name)
                continue
            try:
                provider = cls(cfg)
                self._providers.append(provider)
                self._provider_map[cfg.name] = provider
                loaded += 1
                logger.info(
                    "Provider '%s' newly instantiated: base_url=%s, api_key=%s",
                    cfg_name, cfg.base_url,
                    "***" if cfg.api_key else "(none)",
                )
            except Exception as e:
                logger.error("Failed to instantiate '%s': %s", cfg_name, e)

        # 按优先级重新排序
        self._providers.sort(key=lambda p: p.priority, reverse=True)
        # 标记已初始化（防止后续 auto_discover 覆盖）
        self._initialized = True

        logger.info(
            "ProviderRegistry force_reload: %d providers total (%d from %d configs)",
            loaded, len(self._providers), len(self._configs),
        )
        return loaded

    def update_key(self, name: str, api_key: str) -> bool:
        """动态更新 Provider API 密钥"""
        config = self.get_config(name)
        if not config:
            return False

        config.api_key = api_key

        # 如果已有实例，更新它
        existing = self._provider_map.get(name)
        if existing:
            existing.config.api_key = api_key
            existing._client = None  # 刷新 HTTP 客户端
        else:
            # 重新实例化
            self._init_single_provider(config)

        return True

    def _init_single_provider(self, config: ProviderConfig) -> None:
        """初始化单个 Provider"""
        available_classes = {c.__name__: c for c in _get_all_provider_subclasses()}

        # 尝试匹配类名
        class_name = _BUILTIN_PROVIDERS.get(config.name, "")
        cls = available_classes.get(class_name)

        if not cls:
            logger.warning("No provider class found for '%s'", config.name)
            return

        try:
            provider = cls(config)
            # 移除旧的同名 Provider
            self._providers = [p for p in self._providers if p.name != config.name]
            self._providers.append(provider)
            self._provider_map[config.name] = provider
            self._providers.sort(key=lambda p: p.priority, reverse=True)
            logger.info("Provider '%s' re-initialized", config.name)
        except Exception as e:
            logger.error("Failed to init provider '%s': %s", config.name, e)

    def remove_provider(self, name: str) -> bool:
        """移除 Provider"""
        self._providers = [p for p in self._providers if p.name != name]
        return self._provider_map.pop(name, None) is not None

    async def health_check_all(self) -> dict[str, bool]:
        """对所有 Provider 执行健康检查"""
        results: dict[str, bool] = {}
        for p in self._providers:
            try:
                results[p.name] = await p.health_check()
            except Exception:
                results[p.name] = False
        return results

    async def close_all(self):
        """关闭所有 Provider 的 HTTP 客户端"""
        for p in self._providers:
            try:
                await p.close()
            except Exception:
                pass

    @property
    def count(self) -> int:
        return len(self._providers)


# ── 辅助：获取所有 Provider 子类 ──────────────────────────


def _get_all_provider_subclasses() -> list[Type[BaseProvider]]:
    """获取所有 BaseProvider 的子类"""
    from app.core.providers.base import BaseProvider as BP
    subclasses: list[Type[BaseProvider]] = []

    def _collect(cls):
        for sub in cls.__subclasses__():
            if sub not in subclasses:
                subclasses.append(sub)
            _collect(sub)

    _collect(BP)
    return subclasses


def _get_provider_class_map() -> dict[str, Type[BaseProvider]]:
    """获取 {类名: Provider类} 映射（优先动态加载，降级到内置映射）"""
    classes: dict[str, Type[BaseProvider]] = {}

    # 尝试动态加载
    providers_package = "app.core.providers"
    try:
        package = importlib.import_module(providers_package)
        package_path = os.path.dirname(package.__file__ or "")
        for _, module_name, _ in pkgutil.iter_modules([package_path]):
            if module_name in ("base", "__init__"):
                continue
            try:
                mod = importlib.import_module(f"{providers_package}.{module_name}")
                for name, obj in inspect.getmembers(mod, inspect.isclass):
                    if (
                        issubclass(obj, BaseProvider)
                        and obj is not BaseProvider
                        and obj.__module__ == mod.__name__
                    ):
                        classes[name] = obj
            except Exception as e:
                logger.debug("Failed to load provider module '%s': %s", module_name, e)
    except ImportError:
        pass

    # 降级：使用内置映射加载
    if not classes:
        provider_imports = {
            "openai": "app.core.providers.openai",
            "anthropic": "app.core.providers.anthropic",
            "deepseek": "app.core.providers.deepseek",
            "replicate": "app.core.providers.replicate",
            "zhipu": "app.core.providers.zhipu",
            "qwen": "app.core.providers.qwen",
            "ollama": "app.core.providers.ollama",
        }
        for name, module_path in provider_imports.items():
            try:
                mod = importlib.import_module(module_path)
                class_name = _BUILTIN_PROVIDERS[name]
                cls = getattr(mod, class_name, None)
                if cls and issubclass(cls, BaseProvider):
                    classes[class_name] = cls
            except Exception as e:
                logger.debug("Failed to load builtin provider '%s': %s", name, e)

    return classes


# ── 全局注册表单例 ────────────────────────────────────────


_registry: ProviderRegistry | None = None


def init_provider_registry(configs: list[ProviderConfig] | None = None) -> ProviderRegistry:
    """初始化全局 Provider 注册表"""
    global _registry
    _registry = ProviderRegistry()
    _registry.auto_discover(configs)
    return _registry


def get_provider_registry() -> ProviderRegistry:
    """获取全局 Provider 注册表"""
    global _registry
    if _registry is None:
        return init_provider_registry()
    return _registry
