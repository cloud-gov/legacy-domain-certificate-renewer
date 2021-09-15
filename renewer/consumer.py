"""
This is essentially Huey's entrypoint. We need to import:
- our huey instance
- any cron tasks we want to run
we do this in a file separate from renewer.huey to avoid circular imports
(e.g. we'd have to import renewer.tasks.cron into renewer.huey, but cron
imports renewer.huey)
"""
from renewer.huey import huey
from renewer.tasks import migrations
