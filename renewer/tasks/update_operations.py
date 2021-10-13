from renewer.huey import retriable_task
from renewer.models.common import RouteType, OperationState
from renewer.models.cdn import CdnOperation
from renewer.models.domain import DomainOperation


@retriable_task
def mark_complete(session, operation_id, route_type: RouteType):
    if route_type == RouteType.ALB:
        Operation = DomainOperation
    else:
        Operation = CdnOperation
    operation = session.query(Operation).get(operation_id)
    operation.state = OperationState.SUCCEEDED.value
    session.add(operation)
    session.commit()
