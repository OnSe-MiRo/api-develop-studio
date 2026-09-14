"""Best-effort cache of revision metadata only. Never cache documents or auth."""
import hashlib
import json
import os


class RevisionCache:
    def __init__(self, client=None, ttl=60):
        if client is None and os.environ.get("STUDIO_REDIS_URL"):
            from redis import Redis
            client = Redis.from_url(os.environ["STUDIO_REDIS_URL"], socket_timeout=0.2,
                                    socket_connect_timeout=0.2, decode_responses=True)
        self.client = client
        self.ttl = ttl

    def key(self, workspace, resource, revision):
        identity = json.dumps([os.environ.get("STUDIO_ENV", "local"), workspace, resource])
        return f"studio:cache:v3:{hashlib.sha256(identity.encode()).hexdigest()}:{revision}"

    def get(self, key):
        if self.client is None:
            return None
        try:
            value = json.loads(self.client.get(key) or "null")
            if not isinstance(value, list) or any(
                not isinstance(row, dict) or set(row) != {"revision", "created_by", "created_at", "content_hash"}
                for row in value
            ):
                return None
            return value
        except (ValueError, OSError):
            return None
        except Exception as exc:
            from redis.exceptions import RedisError
            if not isinstance(exc, RedisError):
                raise
            return None

    def set(self, key, value):
        if self.client is None:
            return
        try:
            self.client.set(key, json.dumps(value), ex=self.ttl)
        except Exception as exc:
            from redis.exceptions import RedisError
            if not isinstance(exc, (RedisError, OSError)):
                raise

    def invalidate(self, key):
        if self.client is None:
            return
        try:
            self.client.delete(key)
        except Exception as exc:
            from redis.exceptions import RedisError
            if not isinstance(exc, (RedisError, OSError)):
                raise
