from contextlib import contextmanager

import pytest
from huey import Huey
from huey import signals

from renewer.huey import huey


@huey.signal(signals.SIGNAL_ERROR)
def re_raise_exceptions(signal, task, exc=None):
    print(f"Exception {type(exc)} raised while executing {task.name}:")
    raise exc


@huey.signal(signals.SIGNAL_RETRYING)
def stop_task_from_retrying(signal, task):
    raise AssertionError(f"{task.name} attempted to rety.")


@pytest.fixture(scope="function")
def clean_huey():
    # a huey with an empty task queue that validates the task queue is empty at the end of the test
    # used alone, the intent is to either add tasks to huey and step through them, or add tasks
    # and make assertions about what tasks are enqueued
    try:
        huey.storage.flush_all()
        yield huey
    finally:
        assert huey.pending_count() == 0


@pytest.fixture(scope="function")
def immediate_huey(clean_huey):
    # put huey into immediate mode. This is good for tests where you
    # don't want to step through tasks, and just want huey to run through them
    # synchronously
    old_immediate = clean_huey.immediate
    try:
        clean_huey.immediate = True
        yield clean_huey
    finally:
        clean_huey.immediate = old_immediate


def _emit_without_exception_catching(self, signal, task, *args, **kwargs):
    self._signal.send(signal, task, *args, **kwargs)


@contextmanager
def fallible_huey():
    try:
        huey.disconnect_signal(re_raise_exceptions)
        huey.disconnect_signal(stop_task_from_retrying)
        Huey._emit = default_emit
        yield huey
    finally:
        huey._signal.connect(re_raise_exceptions, signals.SIGNAL_ERROR)
        huey._signal.connect(stop_task_from_retrying, signals.SIGNAL_RETRYING)
        Huey._emit = _emit_without_exception_catching


default_emit = Huey._emit
Huey._emit = _emit_without_exception_catching


class Tasks:
    def run_queued_tasks_and_enqueue_dependents(self):
        """
        Runs all currently queued tasks.  Enqueues pipeline tasks (created with
        `Task.then()`) for the next call of run_all_queued_without_pipelines,
        but does not execute them.  This is useful for stepping through
        pipeline stages in your tests.

        Will fail the test if there's not at least a single Task to be run.
        """
        # __tracebackhide__ = True

        currently_queued_tasks = []

        task = huey.dequeue()
        while task:
            currently_queued_tasks.append(task)
            task = huey.dequeue()

        if not currently_queued_tasks:
            pytest.fail("No tasks queued to run!")

        for task in currently_queued_tasks:
            print(f"Executing Task {task.name}")
            huey.execute(task, None)


@pytest.fixture(scope="function")
def tasks():
    return Tasks()
