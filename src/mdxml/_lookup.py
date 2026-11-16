"""Tuples of named definitions that can also be looked up by name."""

from __future__ import annotations

from typing import Protocol, SupportsIndex, TypeVar, overload

T_co = TypeVar("T_co", bound="HasName", covariant=True)


class HasName(Protocol):
    """Anything with a ``name``, like a unit or type definition."""

    @property
    def name(self) -> str: ...


class Named(tuple[T_co, ...]):
    """A tuple of definitions in document order that also accepts a name as the key.

    ``units["m/s"]`` returns the first definition with that name and raises
    :class:`KeyError` when there's none. Integer indexes and slices work as for
    any tuple, and a ``Named`` compares equal to a plain tuple with the same items.
    """

    __slots__ = ()

    @overload
    def __getitem__(self, key: SupportsIndex) -> T_co: ...
    @overload
    def __getitem__(self, key: slice) -> tuple[T_co, ...]: ...
    @overload
    def __getitem__(self, key: str) -> T_co: ...

    def __getitem__(self, key: SupportsIndex | slice | str) -> T_co | tuple[T_co, ...]:
        """Return the item at an index, the items in a slice, or the first item with a name."""
        if isinstance(key, str):
            for item in self:
                if item.name == key:
                    return item
            raise KeyError(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        """Check for an item, or for a definition with that name."""
        if isinstance(key, str):
            return any(item.name == key for item in self)
        return super().__contains__(key)

    def get(self, name: str) -> T_co | None:
        """Return the first definition with ``name``, or ``None``."""
        for item in self:
            if item.name == name:
                return item
        return None
