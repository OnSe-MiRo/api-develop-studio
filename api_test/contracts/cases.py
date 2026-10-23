"""Opt-in saved-case contract settings and a per-case document snapshot."""
from copy import deepcopy
from .documents import ContractError, digest
from .validation import lint, match_operation, validate_document_url, validate_server_variables


def case_contract_config(value):
    if not isinstance(value, dict) or set(value) - {'enabled', 'server_variables', 'document_url'} or not isinstance(value.get('enabled'), bool):
        raise ContractError('Invalid case contract configuration')
    if 'server_variables' in value:
        validate_server_variables(value['server_variables'])
    if 'document_url' in value:
        validate_document_url(value['document_url'])
    return deepcopy(value)


def prepare_case_contract(value, document, method, url, base_url):
    config = case_contract_config(value)
    if not config['enabled']:
        return None
    if not isinstance(document, dict):
        raise ContractError('A saved project contract is required')
    snapshot = deepcopy(document)
    if any(item['severity'] == 'error' for item in lint(snapshot)):
        raise ContractError('Invalid saved project contract')
    options = {'base_url': base_url, 'server_variables': config.get('server_variables'), 'document_url': config.get('document_url')}
    match_operation(snapshot, method, url, **options)
    return snapshot, options, digest(snapshot)
