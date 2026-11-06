from copy import deepcopy
import unittest

import test_contract_prefix_headers as fixture


class UnionTupleTests(unittest.TestCase):
    def result(self, keyword, value, *branches):
        helper = fixture.PrefixHeaderTests()
        doc = helper.spec()
        helper.header(doc)['schema'] = {keyword: list(branches)}
        return helper.check(doc, value)

    def test_match_whole_branch(self):
        for keyword in ('oneOf', 'anyOf'):
            branches = [{'type': 'array', 'prefixItems': [{'const': tag}, {'const': n}],
                         'minItems': 2, 'items': False} for tag, n in [('A', 2), ('B', 5)]]
            for raw in ('A,2', 'B,5'):
                self.assertTrue(self.result(keyword, raw, *branches)['valid'])
            for raw in ('A,5', 'A', 'B,5,extra'):
                self.assertFalse(self.result(keyword, raw, *branches)['valid'])

    def test_overlap_and_boundaries(self):
        a = {'type': 'array', 'prefixItems': [{'type': 'integer'}, {'type': 'string'}],
             'minItems': 2, 'maxItems': 2}
        b = deepcopy(a)
        b['prefixItems'][0]['minimum'] = 5
        self.assertTrue(self.result('oneOf', '4,x', a, b)['valid'])
        self.assertFalse(self.result('oneOf', '5,x', a, b)['valid'])
        self.assertTrue(self.result('anyOf', '5,x', a, b)['valid'])

    def test_disagreeing_slots_fail_closed(self):
        a = {'type': 'array', 'prefixItems': [{'type': 'string'}, {'type': 'integer'}]}
        b = deepcopy(a)
        b['prefixItems'][1] = {'type': 'boolean'}
        self.assertFalse(self.result('anyOf', 'tag,12', a, b)['valid'])
        self.assertTrue(self.result('anyOf', 'tag', a, b)['valid'])

    def test_closed_short_branch_does_not_choose_the_long_branch_decoder(self):
        short = {'type': 'array', 'prefixItems': [{'type': 'string'}], 'items': False}
        long = {'type': 'array', 'prefixItems': [{'type': 'string'}, {'type': 'integer'}],
                'minItems': 2, 'items': False}
        for keyword in ('oneOf', 'anyOf'):
            self.assertTrue(self.result(keyword, 'tag', short, long)['valid'])
            self.assertTrue(self.result(keyword, 'tag,2', short, long)['valid'])
            self.assertFalse(self.result(keyword, 'tag,PRIVATE', short, long)['valid'])
