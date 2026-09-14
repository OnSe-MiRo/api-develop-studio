"""Project environment overrides and reusable authentication references."""
from copy import deepcopy
from urllib.parse import urlparse
from .project_variables import ProjectVariableError, normalize_project_variables, project_variables_for_client, PROJECT_VARIABLE_PATTERN

AUTH_FIELDS = {
    'No Auth': set(), 'API Key': {'key', 'value', 'addTo'},
    'Basic Auth': {'username', 'password'}, 'Bearer Token': {'token'},
}
SECRET_FIELDS = {'value', 'password', 'token'}


def validate_auth_profiles(profiles):
    if not isinstance(profiles, dict):
        raise ProjectVariableError('auth_profiles must be an object')
    for name, auth in profiles.items():
        if not name or not isinstance(auth, dict) or not isinstance(auth.get('type'), str) or auth.get('type') not in AUTH_FIELDS:
            raise ProjectVariableError('Invalid authentication profile')
        if set(auth) - AUTH_FIELDS[auth['type']] - {'type'}:
            raise ProjectVariableError('Unsupported authentication profile field')
        for field, value in auth.items():
            if not isinstance(value, str):
                raise ProjectVariableError('Authentication values must be strings')
            if field in SECRET_FIELDS and not PROJECT_VARIABLE_PATTERN.fullmatch(value):
                raise ProjectVariableError('Profile credentials must reference an encrypted {{project.NAME}} variable')


def normalize_profiles(document, existing=None):
    result = deepcopy(document)
    existing = existing or {}
    environments = result.get('environments', existing.get('environments', {}))
    if not isinstance(environments, dict):
        raise ProjectVariableError('environments must be an object')
    normalized = {}
    for name, environment in environments.items():
        if not name or not isinstance(environment, dict):
            raise ProjectVariableError('Invalid environment')
        if not isinstance(environment.get('base_url'), str):
            raise ProjectVariableError('Environment base_url must be a string')
        parsed = urlparse(environment['base_url'])
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ProjectVariableError('Environment base_url must be an absolute HTTP URL')
        old = existing.get('environments', {}).get(name, {})
        env = deepcopy(environment)
        if 'environments' in document:
            env['variables'] = normalize_project_variables(env.get('variables', {}), old.get('variables'))
        normalized[name] = env
    if 'variables' not in result:
        result['variables'] = deepcopy(existing.get('variables', {}))
    result['environments'] = normalized
    selected = result.get('default_environment', existing.get('default_environment', ''))
    if not isinstance(selected, str) or (selected and selected not in normalized):
        raise ProjectVariableError('Unknown default environment')
    result['default_environment'] = selected
    result['auth_profiles'] = result.get('auth_profiles', existing.get('auth_profiles', {}))
    validate_auth_profiles(result['auth_profiles'])
    for env in normalized.values():
        validate_auth_profiles(env.get('auth_profiles', {}))
    for env_name in ['', *normalized]:
        effective = select_environment(result, env_name, use_default=False)
        secret = effective.get('variables', {}).get('secret', {})
        for auth in effective['auth_profiles'].values():
            for field in SECRET_FIELDS & auth.keys():
                match = PROJECT_VARIABLE_PATTERN.fullmatch(auth[field])
                if match.group(1) not in secret:
                    raise ProjectVariableError('Profile credentials must reference encrypted variables')
    return result


def select_environment(project, environment=None, *, use_default=True):
    result = deepcopy(project)
    if environment is not None and not isinstance(environment, str):
        raise ProjectVariableError('Environment must be a string')
    selected = environment or (project.get('default_environment', '') if use_default else '')
    if not selected:
        return result
    if not isinstance(selected, str) or selected not in project.get('environments', {}):
        raise ProjectVariableError('Unknown environment')
    override = project['environments'][selected]
    result['base_url'] = override['base_url']
    common = result.setdefault('variables', {})
    for kind, other in [('plain', 'secret'), ('secret', 'plain')]:
        common.setdefault(kind, {})
        common.setdefault(other, {})
        for name, value in override.get('variables', {}).get(kind, {}).items():
            common[other].pop(name, None)
            common[kind][name] = value
    result['auth_profiles'] = {**project.get('auth_profiles', {}), **override.get('auth_profiles', {})}
    return result


def resolve_auth_profile(request, profiles):
    result = deepcopy(request)
    reference = result.pop('auth_profile', '')
    if reference:
        if not isinstance(reference, str) or reference not in profiles:
            raise ProjectVariableError('Unknown authentication profile')
        result['auth'] = deepcopy(profiles[reference])
    return result


def profiles_for_client(project):
    result = project_variables_for_client(project)
    result['environments'] = {name: project_variables_for_client(env) for name, env in project.get('environments', {}).items()}
    return result
