from __future__ import annotations

import asyncio

from dev_tools.deferred_ui import DeferredLoadController, LoadState


class _Page:
    def __init__(self) -> None:
        self.tasks = []
        self.update_count = 0

    def run_task(self, handler):
        self.tasks.append(handler)
        return handler

    def update(self) -> None:
        self.update_count += 1


def test_deferred_load_deduplicates_loading_and_reuses_loaded_state(monkeypatch) -> None:
    async def inline_to_thread(function):
        return function()

    monkeypatch.setattr("dev_tools.deferred_ui.asyncio.to_thread", inline_to_thread)
    page = _Page()
    calls = []
    applied = []
    controller = DeferredLoadController(
        page=page,
        load=lambda: calls.append("load") or "result",
        apply=applied.append,
    )

    controller.start()
    controller.start()

    assert controller.state == LoadState.LOADING
    assert len(page.tasks) == 1
    asyncio.run(page.tasks.pop()())
    assert controller.state == LoadState.LOADED
    assert calls == ["load"]
    assert applied == ["result"]

    controller.start()
    assert page.tasks == []


def test_invalidated_slow_completion_cannot_overwrite_newer_result(monkeypatch) -> None:
    page = _Page()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    call_number = 0
    applied = []

    def load() -> str:
        raise AssertionError("the deterministic bridge supplies the result")

    async def controlled_to_thread(_function):
        nonlocal call_number
        call_number += 1
        current = call_number
        if current == 1:
            first_started.set()
            await release_first.wait()
        return f"result-{current}"

    monkeypatch.setattr("dev_tools.deferred_ui.asyncio.to_thread", controlled_to_thread)
    controller = DeferredLoadController(page=page, load=load, apply=applied.append)
    controller.start()
    first_handler = page.tasks.pop()

    async def exercise_race() -> None:
        first_task = asyncio.create_task(first_handler())
        await first_started.wait()
        controller.invalidate()
        controller.start()
        second_handler = page.tasks.pop()
        await second_handler()
        release_first.set()
        await first_task

    asyncio.run(exercise_race())

    assert applied == ["result-2"]
    assert controller.state == LoadState.LOADED


def test_close_discards_queued_completion(monkeypatch) -> None:
    async def inline_to_thread(function):
        return function()

    monkeypatch.setattr("dev_tools.deferred_ui.asyncio.to_thread", inline_to_thread)
    page = _Page()
    applied = []
    controller = DeferredLoadController(page=page, load=lambda: "late", apply=applied.append)
    controller.start()
    handler = page.tasks.pop()
    controller.close()

    asyncio.run(handler())

    assert applied == []
    assert controller.active is False
