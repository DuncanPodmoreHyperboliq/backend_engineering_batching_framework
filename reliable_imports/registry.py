"""
Convention-based processor registry.

This module provides automatic discovery and registration of processors,
saving developer time by eliminating manual registration boilerplate.
"""

import importlib
import inspect
import pkgutil
from typing import Dict, Optional, Type

from .exceptions import ProcessorNotFoundError
from .processor import BaseProcessor


class ProcessorRegistry:
    """
    Registry for batch processors.

    The registry supports:
    - Manual registration via register()
    - Automatic discovery via discover()
    - Convention-based lookup by batch_type
    """

    def __init__(self):
        self._processors: Dict[str, Type[BaseProcessor]] = {}

    def register(
        self, batch_type: str, processor_class: Type[BaseProcessor]
    ) -> None:
        """
        Manually register a processor for a batch type.

        Args:
            batch_type: The batch type identifier
            processor_class: The processor class to register
        """
        if not issubclass(processor_class, BaseProcessor):
            raise ValueError(
                f"{processor_class.__name__} must inherit from BaseProcessor"
            )

        self._processors[batch_type] = processor_class

    def get(self, batch_type: str) -> Type[BaseProcessor]:
        """
        Get the processor class for a batch type.

        Args:
            batch_type: The batch type identifier

        Returns:
            The processor class

        Raises:
            ProcessorNotFoundError: If no processor is registered for the batch type
        """
        if batch_type not in self._processors:
            raise ProcessorNotFoundError(
                f"No processor registered for batch type: {batch_type}. "
                f"Available types: {', '.join(self._processors.keys())}"
            )

        return self._processors[batch_type]

    def has(self, batch_type: str) -> bool:
        """Check if a processor is registered for a batch type."""
        return batch_type in self._processors

    def list_batch_types(self) -> list:
        """Get all registered batch types."""
        return list(self._processors.keys())

    def discover(self, package_name: str) -> int:
        """
        Automatically discover and register processors in a package.

        This method searches for all classes that inherit from BaseProcessor
        and automatically registers them based on their batch_type.

        Convention: Classes should be named like `CustomerDataProcessor`
        which will be registered for batch_type `customer_data`.

        Args:
            package_name: Python package to search (e.g., 'myapp.processors')

        Returns:
            Number of processors discovered and registered

        Example:
            >>> registry = ProcessorRegistry()
            >>> registry.discover('myapp.processors')
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
                    count += self._register_processors_in_module(module)
                except Exception as e:
                    # Log but don't fail on import errors
                    print(f"Warning: Could not import {modname}: {e}")
        else:
            # Register processors in the single module
            count += self._register_processors_in_module(package)

        return count

    def _register_processors_in_module(self, module) -> int:
        """Register all processor classes found in a module."""
        count = 0

        for name, obj in inspect.getmembers(module, inspect.isclass):
            # Check if it's a processor (but not the base class itself)
            if (
                issubclass(obj, BaseProcessor)
                and obj is not BaseProcessor
                and obj.__module__ == module.__name__
            ):
                # Create instance to get batch_type
                instance = obj()
                if instance.batch_type:
                    self.register(instance.batch_type, obj)
                    count += 1

        return count


# Global registry instance
_default_registry = ProcessorRegistry()


def get_registry() -> ProcessorRegistry:
    """Get the default global processor registry."""
    return _default_registry


def processor(batch_type: str):
    """
    Decorator to register a processor for a batch type.

    This provides an alternative to automatic discovery for explicit registration.

    Example:
        >>> @processor('customer_data')
        ... class CustomerProcessor(BaseProcessor):
        ...     def process_item(self, item, ctx):
        ...         # Process customer data
        ...         pass
    """

    def decorator(cls: Type[BaseProcessor]) -> Type[BaseProcessor]:
        _default_registry.register(batch_type, cls)
        return cls

    return decorator
