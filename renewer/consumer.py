"""
This is essentially Huey's entrypoint. We need to import:
- our huey instance
- any cron tasks we want to run
we do this in a file separate from renewer.huey to avoid circular imports
(e.g. we'd have to import renewer.tasks.cron into renewer.huey, but cron
imports renewer.huey)
"""
import logging

from renewer.huey import huey
from renewer.tasks import migrations, renewals
from renewer.extensions import config

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
