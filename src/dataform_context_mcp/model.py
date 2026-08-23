"""Typed model of a compiled Dataform graph (subset needed for context serving)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Target:
    database: str
    schema: str
    name: str

    def canonical(self) -> str:
        return f"{self.database}.{self.schema}.{self.name}"


@dataclass
class ColumnDoc:
    name: str  # nested field paths joined with "."
    description: str | None = None


@dataclass
class Action:
    target: Target
    action_type: str  # table|view|incremental|declaration|operations|assertion
    file_name: str | None = None
    tags: list[str] = field(default_factory=list)
    description: str | None = None
    columns: list[ColumnDoc] = field(default_factory=list)
    dependency_targets: list[Target] = field(default_factory=list)
    query: str | None = None
    incremental_query: str | None = None
    unique_key: list[str] = field(default_factory=list)
    disabled: bool = False


@dataclass
class CompiledGraphData:
    actions: list[Action]
    dataform_version: str | None = None
