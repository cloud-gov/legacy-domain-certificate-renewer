import pytest

from tests.lib.alb_fixtures import alb_route, proxy
from tests.lib.cdn_fixtures import cdn_route
from tests.lib.database import clean_db
from tests.lib.fake_alb import alb
from tests.lib.fake_iam import iam_govcloud
from tests.lib.tasks import tasks, immediate_huey


def pytest_configure(config):
    config.addinivalue_line("markers", "focus: Only run this test.")


def pytest_collection_modifyitems(items, config):
    """
    Focus on tests marked focus, if any.  Run all
    otherwise.
    """

    selected_items = []
    deselected_items = []

    focused = False

    for item in items:
        if item.get_closest_marker("focus"):
            focused = True
            selected_items.append(item)
        else:
            deselected_items.append(item)

    if focused:
        print("\nOnly running @pytest.mark.focus tests")
        config.hook.pytest_deselected(items=deselected_items)
        items[:] = selected_items
