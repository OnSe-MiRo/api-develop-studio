import json
import unittest

from api_test.contracts import validate_response
from test_contracts import document


def tuple_contract(first, second):
    doc = document('3.1.0')
    doc['components']['schemas'].update(Base=first, Overlay=second)
    header = {'required': True, 'schema': {'allOf': [
        {'$ref': '#/components/schemas/Base'}, {'$ref': '#/components/schemas/Overlay'}
    ]}}
    doc['paths']['/items/{id}']['get']['responses']['200']['headers'] = {'X-Window': header}
    return doc, header


def check(doc, raw):
    return validate_response(doc, 'GET', '/items/1', 200,
                             {'Content-Type': 'application/json', 'x-window': raw}, {'id': 1})


class AllOfTupleTests(unittest.TestCase):
    def test_different_prefix_lengths_apply_local_tail_at_each_position(self):
        doc, header = tuple_contract(
            {'type': ['array', 'null'], 'prefixItems': [{'type': 'string'}, {'type': 'integer', 'minimum': 1}],
             'items': {'type': 'number', 'minimum': 0}},
            {'allOf': [{'prefixItems': [{'const': 'ready'}, {'maximum': 5}, {'type': 'integer', 'maximum': 9}],
                        'items': {'maximum': 4}}, {'minItems': 2, 'uniqueItems': True}]})
        for explode in [False, True]:
            header['explode'] = explode
            self.assertTrue(check(doc, 'ready,2,7,1.5')['valid'])
            for raw, code in [('ready', 'minItems'), ('ready,0', 'minimum'), ('ready,6', 'maximum'),
                              ('ready,2,7.5', 'type'), ('ready,2,7,5', 'maximum'),
                              ('ready,2,2', 'uniqueItems'), ('ready,PRIVATE', 'type')]:
                with self.subTest(explode=explode, raw=raw):
                    errors = check(doc, raw)['issues']
                    self.assertIn('schema_' + code, [issue['code'] for issue in errors])
                    self.assertNotIn('PRIVATE', json.dumps(errors))

    def test_short_closed_prefix_keeps_its_own_items_boundary(self):
        doc, _ = tuple_contract(
            {'type': 'array', 'prefixItems': [True, {}], 'items': False},
            {'prefixItems': [{'const': '2'}, {'const': 3}, {'type': 'integer'}]})
        self.assertTrue(check(doc, '2')['valid'])
        self.assertTrue(check(doc, '2,3')['valid'])
        self.assertIn('schema_items', [issue['code'] for issue in check(doc, '2,3,4')['issues']])

    def test_ref_sibling_allof_and_unconstrained_tail(self):
        doc, header = tuple_contract(
            {'type': 'array', 'prefixItems': [True]},
            {'prefixItems': [{'type': 'integer'}], 'minItems': 1})
        doc['components']['schemas']['Combined'] = {
            '$ref': '#/components/schemas/Base', 'allOf': [{'$ref': '#/components/schemas/Overlay'}]}
        header['schema'] = {'$ref': '#/components/schemas/Combined'}
        doc['components']['schemas']['Combined']['enum'] = [[2, '003']]
        self.assertTrue(check(doc, '2,003')['valid'])
        self.assertFalse(check(doc, '2,3')['valid'])

    def test_item_ref_chains_keep_sibling_type_and_constraints(self):
        doc, _ = tuple_contract(
            {'type': 'array', 'prefixItems': [{'$ref': '#/components/schemas/Limited'}]},
            {'minItems': 1})
        doc['components']['schemas'].update(
            AnyItem=True, Limited={'$ref': '#/components/schemas/AnyItem', 'type': 'integer', 'maximum': 5})
        self.assertTrue(check(doc, '4')['valid'])
        self.assertIn('schema_maximum', [issue['code'] for issue in check(doc, '6')['issues']])

    def test_annotation_only_alias_keeps_unconstrained_wire_text(self):
        doc, header = tuple_contract(
            {'type': 'array', 'prefixItems': [{'$ref': '#/components/schemas/Named'}]},
            {'enum': [['002']]})
        doc['components']['schemas'].update(AnyItem=True, Named={'$ref': '#/components/schemas/AnyItem', 'title': 'Label'})
        self.assertTrue(check(doc, '002')['valid'])
        header['schema'] = {'$ref': '#/components/schemas/Base'}
        self.assertTrue(check(doc, '002')['valid'])

    def test_ambiguous_position_fails_and_union_uses_common_present_slots(self):
        doc, header = tuple_contract(
            {'type': 'array', 'prefixItems': [{'type': 'integer'}]},
            {'prefixItems': [{'type': 'string'}]})
        result = check(doc, 'PRIVATE')
        self.assertIn('unsupported_header_serialization', [issue['code'] for issue in result['issues']])
        self.assertNotIn('PRIVATE', json.dumps(result))
        header['schema'] = {'anyOf': [{'allOf': [{'$ref': '#/components/schemas/Base'}]},
                                      {'type': 'array', 'items': {'type': 'integer'}}]}
        self.assertTrue(check(doc, '2')['valid'])
        self.assertFalse(check(doc, '2,3')['valid'])
