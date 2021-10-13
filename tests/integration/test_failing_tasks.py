import time
import pytest

from huey.exceptions import TaskException
from renewer.extensions import config
from renewer.huey import huey
from renewer.models.cdn import CdnOperation, CdnRoute
from renewer.models.domain import DomainOperation, DomainRoute

from tests.lib.tasks import fallible_huey, immediate_huey


@pytest.mark.parametrize(
    "Operation,Route", [(CdnOperation, CdnRoute), (DomainOperation, DomainRoute)]
)
def test_operations_marked_failed_after_failing(
    tasks, clean_db, immediate_huey, Operation, Route
):
    @huey.task(name=f"no_retry_task{Operation}")
    def no_retry_task(operation_id, route_type):
        raise Exception()

    route = Route(instance_id="asdf", state="provisioned")
    no_retries_left_operation = Operation(
        id="9876", state="in progress", action="Renew", route=route
    )
    clean_db.add(no_retries_left_operation)
    clean_db.add(route)
    clean_db.commit()
    pipeline = no_retry_task.s("9876", route.route_type)
    with fallible_huey():
        immediate_huey.enqueue(pipeline)
    clean_db.expunge_all()
    no_retries_left_operation = clean_db.query(Operation).get("9876")
    assert no_retries_left_operation.state == "failed"


@pytest.mark.parametrize(
    "Operation,Route", [(CdnOperation, CdnRoute), (DomainOperation, DomainRoute)]
)
def test_retry_tasks_marked_failed_only_after_last_retry(
    clean_db, immediate_huey, Operation, Route
):
    global retry_marked_failed
    retry_marked_failed = False

    @huey.task(retries=7, name=f"retry_task{Operation}")
    def retry_task(operation_id, route_type):
        operation = clean_db.query(Operation).get(operation_id)
        global retry_marked_failed
        if operation.state == "failed":
            retry_marked_failed = True
        raise Exception()

    route = Route(instance_id="asdf", state="provisioned")
    no_retries_left_operation = Operation(
        id="6789", state="in progress", action="Renew", route=route
    )
    clean_db.add(route)
    clean_db.add(no_retries_left_operation)
    clean_db.commit()
    with fallible_huey() as h:
        task = retry_task("6789", route.route_type)
        with pytest.raises(Exception):
            result = task()
    clean_db.expunge_all()
    operation_with_retries = clean_db.query(Operation).get("6789")
    assert operation_with_retries.state == "failed"
    assert not retry_marked_failed
