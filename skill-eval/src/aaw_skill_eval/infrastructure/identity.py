import uuid
from datetime import UTC, datetime


def new_id():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(UTC)
