"""
Convention-based endpoint registry.

This module provides automatic discovery and registration of custom endpoints,
following the same pattern as processor registration.
"""

import importlib
import inspect
import pkgutil
from typing import Dict, Optional, Type

from .endpoint import BaseEndpoint


class EndpointRegistry:
    """
    Registry for custom batch endpoints.

    The registry supports:
    - Manual registration via register()
    - Automatic discovery via discover()
    - Convention-based lookup by batch_type
    """

    def __init__(self):
        self._endpoints: Dict[str, Type[BaseEndpoint]] = {}

    def register(
        self, batch_type: str, endpoint_class: Type[BaseEndpoint]
    ) -> None:
        """
        Manually register a custom endpoint for a batch type.

        Args:
            batch_type: The batch type identifier
            endpoint_class: The endpoint class to register
        """
        if not issubclass(endpoint_class, BaseEndpoint):
            raise ValueError(
                f"{endpoint_class.__name__} must inherit from BaseEndpoint"
            )

        self._endpoints[batch_type] = endpoint_class

    def get(self, batch_type: str) -> Optional[Type[BaseEndpoint]]:
        """
        Get the custom endpoint class for a batch type.

        Args:
            batch_type: The batch type identifier

        Returns:
            The endpoint class, or None if no custom endpoint is registered
        """
        return self._endpoints.get(batch_type)

    def has(self, batch_type: str) -> bool:
        """Check if a custom endpoint is registered for a batch type."""
        return batch_type in self._endpoints

    def list_batch_types(self) -> list:
        """Get all batch types with custom endpoints."""
        return list(self._endpoints.keys())

    def discover(self, package_name: str) -> int:
        """
        Automatically discover and register custom endpoints in a package.

        This method searches for all classes that inherit from BaseEndpoint
        and automatically registers them based on their batch_type.

        Convention: Classes should be named like `CustomerDataEndpoint`
        which will be registered for batch_type `customer_data`.

        Args:
            package_name: Python package to search (e.g., 'myapp.endpoints')

        Returns:
            Number of endpoints discovered and registered

        Example:
            >>> registry = EndpointRegistry()
            >>> registry.discover('myapp.endpoints')
            3
        """
        count = 0

        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            raise ImportError(f"Cannot import package {package_name}: {e}")

        # Get package path
        if hasattr(package, '__path__'):
            package_path = package.__path__
        else:
            # Single module, not a package
            package_path = None

        # Discover all modules in package
        if package_path:
            for importer, modname, ispkg in pkgutil.walk_packages(
                path=package_path, prefix=package_name + '.'
            ):
                try:
                    module = importlib.import_module(modname)
                    count += self._register_endpoints_in_module(module)
                except Exception as e:
                    # Log but don't fail on import errors
                    print(f"Warning: Could not import {modname}: {e}")
        else:
            # Register endpoints in the single module
            count += self._register_endpoints_in_module(package)

        return count

    def _register_endpoints_in_module(self, module) -> int:
        """Register all endpoint classes found in a module."""
        count = 0

        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Check if it's an endpoint (but not the base class itself)
            if (
                issubclass(obj, BaseEndpoint)
                and obj is not BaseEndpoint
                and obj.__module__ == module.__name__
            ):
                # Create instance to get batch_type
                instance = obj()
                if instance.batch_type:
                    self.register(instance.batch_type, obj)
                    count += 1

        return count


# Global registry instance
_default_endpoint_registry = EndpointRegistry()


def get_endpoint_registry() -> EndpointRegistry:
    """Get the default global endpoint registry."""
    return _default_endpoint_registry


def endpoint(batch_type: str):
    """
    Decorator to register a custom endpoint for a batch type.

    This provides an alternative to automatic discovery for explicit registration.

    Example:
        >>> @endpoint('customer_data')
        ... class CustomerEndpoint(BaseEndpoint):
        ...     def before_create_batch(self, request_data, ctx):
        ...         # Custom validation
        ...         return request_data
    """

    def decorator(cls: Type[BaseEndpoint]) -> Type[BaseEndpoint]:
        _default_endpoint_registry.register(batch_type, cls)
        return cls

    return decorator
