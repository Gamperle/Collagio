"""Undo/redo history of commands applied to one project."""

from __future__ import annotations

from collections.abc import Callable

from collagio.core.commands import Command
from collagio.core.model import Project

Listener = Callable[[], None]


class UndoStack:
    """Applies commands and keeps them for undo and redo.

    `clean` marks the state that matches the file on disk (see `set_clean`);
    `modified` is true whenever the current state differs from it.
    """

    def __init__(self, project: Project, limit: int = 200) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self.project = project
        self.limit = limit
        self._done: list[Command] = []
        self._undone: list[Command] = []
        self._clean_index: int | None = 0  # None: the clean state was dropped from history
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    def push(self, command: Command) -> None:
        """Apply `command` and record it. Clears the redo history."""
        command.apply(self.project)
        self._done.append(command)
        if self._clean_index is not None and self._clean_index > len(self._done) - 1:
            self._clean_index = None  # the clean state was in the discarded redo history
        self._undone.clear()
        if len(self._done) > self.limit:
            self._done.pop(0)
            if self._clean_index is not None:
                self._clean_index = self._clean_index - 1 if self._clean_index > 0 else None
        self._notify()

    def undo(self) -> None:
        if not self._done:
            return
        command = self._done.pop()
        command.revert(self.project)
        self._undone.append(command)
        self._notify()

    def redo(self) -> None:
        if not self._undone:
            return
        command = self._undone.pop()
        command.apply(self.project)
        self._done.append(command)
        self._notify()

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()
        self._clean_index = 0
        self._notify()

    def set_clean(self) -> None:
        self._clean_index = len(self._done)
        self._notify()

    def set_dirty(self) -> None:
        """Mark the current state as unsaved (e.g. a recovered autosave)."""
        self._clean_index = None
        self._notify()

    @property
    def modified(self) -> bool:
        return self._clean_index != len(self._done)

    @property
    def can_undo(self) -> bool:
        return bool(self._done)

    @property
    def can_redo(self) -> bool:
        return bool(self._undone)

    @property
    def undo_label(self) -> str | None:
        return self._done[-1].label if self._done else None

    @property
    def redo_label(self) -> str | None:
        return self._undone[-1].label if self._undone else None
