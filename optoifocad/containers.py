"""Containers."""

from typing import Any
from dataclasses import dataclass, field


class OptocadScript(list):
    """Optocad script container."""


@dataclass
class OptocadCommand:
    """Optocad command container."""
    directive: str
    args: list
    kwargs: dict
    secondary_surfaces: list = field(default_factory=list)

    def __str__(self):
        args = ", ".join(str(a) for a in self.args)
        kwargs = ", ".join(f"{str(k)}={str(v)}" for k, v in self.kwargs.items())
        string = f"{self.directive} {args}, {kwargs}"
        if self.secondary_surfaces:
            string += "\n" + "\n".join(str(s) for s in self.secondary_surfaces)
        return string


@dataclass
class OptocadSecondarySurfaceCommand:
    """Optocad secondary surface command container."""
    args: list
    kwargs: dict

    def __str__(self):
        args = ", ".join(str(a) for a in self.args)
        kwargs = ", ".join(f"{str(k)}={str(v)}" for k, v in self.kwargs.items())
        return f"\t+ {args}, {kwargs}"


@dataclass
class OptocadUnaryExpression:
    operator: str
    argument: Any

    def __str__(self):
        return f"{self.operator}{str(self.argument)}"

@dataclass
class OptocadBinaryExpression:
    operator: str
    lhs: Any
    rhs: Any

    def __str__(self):
        return f"{str(self.lhs)}{self.operator}{str(self.rhs)}"
