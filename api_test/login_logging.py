"""Keep authorization response secrets out of standard Uvicorn access logs."""
import logging
from urllib.parse import urlsplit, unquote


class LoginAccessFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            target = record.args[2]
            if isinstance(target, str):
                path = urlsplit(target).path
                if unquote(path).startswith(('/auth/', '/api/oauth/callback/')):
                    values = list(record.args); values[2] = path; record.args = tuple(values)
        return True


def install_access_filter():
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(item, LoginAccessFilter) for item in logger.filters):
        logger.addFilter(LoginAccessFilter())
