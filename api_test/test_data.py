"""Allowlisted declarative run-local data. No script execution."""
import random
import re
import uuid
from datetime import datetime, timezone

NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
REFERENCE = re.compile(r'\$\{run\.([A-Za-z_][A-Za-z0-9_]*)\}')


def generate(definitions, seed=None):
    from api_test.runner import CaseConfigurationError
    if not isinstance(definitions, dict) or len(definitions) > 100:
        raise CaseConfigurationError('generators must be an object with at most 100 entries')
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, (int, str))):
        raise CaseConfigurationError('seed must be an integer or string')
    rng = random.Random(seed)
    values = {}
    for name, definition in definitions.items():
        if not NAME.fullmatch(name) or not isinstance(definition, dict):
            raise CaseConfigurationError('Invalid generator definition')
        kind = definition.get('type')
        if kind == 'uuid':
            values[name] = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        elif kind == 'timestamp':
            # Seeded runs use a deterministic UTC timestamp; unseeded runs use now.
            values[name] = datetime.fromtimestamp(rng.randint(946684800, 4102444800), timezone.utc).isoformat() if seed is not None else datetime.now(timezone.utc).isoformat()
        elif kind == 'integer':
            low, high = definition.get('min', 0), definition.get('max', 100)
            if any(isinstance(v, bool) or not isinstance(v, int) for v in (low, high)) or low > high:
                raise CaseConfigurationError('integer generator needs min <= max integers')
            values[name] = rng.randint(low, high)
        else:
            raise CaseConfigurationError('Allowed generators: uuid, timestamp, integer')
    return values


def resolve(value, variables):
    from api_test.runner import CaseConfigurationError
    if isinstance(value, dict):
        return {k: resolve(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, variables) for v in value]
    if not isinstance(value, str):
        return value
    def lookup(match):
        if match[1] not in variables:
            raise CaseConfigurationError('Unknown run variable: ' + match[1])
        return variables[match[1]]
    match = REFERENCE.fullmatch(value)
    return lookup(match) if match else REFERENCE.sub(lambda m: str(lookup(m)), value)


def extract(definitions, response):
    from api_test.runner import CaseConfigurationError, _dig
    if not isinstance(definitions, dict) or len(definitions) > 100:
        raise CaseConfigurationError('extract must be an object with at most 100 entries')
    values = {}
    for name, path in definitions.items():
        if not NAME.fullmatch(name) or not isinstance(path, str) or not re.fullmatch(r'(body(?:\.[\w-]+)*|status)', path):
            raise CaseConfigurationError('Extract paths must start with body or status')
        try:
            values[name] = response.status if path == 'status' else _dig(response.body, path[5:]) if path.startswith('body.') else response.body
        except (KeyError, IndexError, TypeError, ValueError):
            raise CaseConfigurationError('Extract response path not found') from None
    return values


def sensitive_strings(value):
    if isinstance(value, dict):
        return set().union(*(sensitive_strings(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(sensitive_strings(v) for v in value)) if value else set()
    return {str(value)} if value is not None else set()
