from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Callable


class LoadState(str, Enum):
    NOT_LOADED = "NOT_LOADED"
    LOADING = "LOADING"
    LOADED = "LOADED"
    ERROR = "ERROR"


class DeferredLoadController:
    """Session-local bridge from blocking reads to Flet's async UI context."""

    def __init__(
        self,
        *,
        page: Any,
        load: Callable[[], Any],
        apply: Callable[[Any], None],
        loading: Callable[[], None] | None = None,
        failed: Callable[[Exception], None] | None = None,
    ) -> None:
        self.page = page
        self.load = load
        self.apply = apply
        self.loading = loading or (lambda: None)
        self.failed = failed or (lambda _exc: None)
        self.state = LoadState.NOT_LOADED
        self.generation = 0
        self.active = True

    def start(self, *, force: bool = False) -> Any:
        if not self.active:
            return None
        if self.state == LoadState.LOADING:
            return None
        if self.state == LoadState.LOADED and not force:
            return None
        self.generation += 1
        generation = self.generation
        self.state = LoadState.LOADING
        self.loading()
        self._update()

        async def _load_generation() -> None:
            await self._run(generation)

        return self.page.run_task(_load_generation)

    def invalidate(self) -> None:
        self.generation += 1
        self.state = LoadState.NOT_LOADED

    def close(self) -> None:
        """Prevent a queued completion from touching a closed Flet session."""
        self.active = False
        self.invalidate()

    async def _run(self, generation: int) -> None:
        try:
            result = await asyncio.to_thread(self.load)
        except Exception as exc:
            if not self.active or generation != self.generation:
                return
            self.state = LoadState.ERROR
            self.failed(exc)
            self._update()
            return
        if not self.active or generation != self.generation:
            return
        self.apply(result)
        self.state = LoadState.LOADED
        self._update()

    def _update(self) -> None:
        update = getattr(self.page, "update", None)
        if callable(update):
            try:
                update()
            except RuntimeError:
                self.close()
