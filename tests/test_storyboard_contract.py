import copy
import unittest

import storyboard_contract as contract


class StoryboardContractTests(unittest.TestCase):
    def test_legacy_no_migration_or_mutation(self):
        shot = {'creative_details': {'camera': {'movement': '锁定'}}, 'reference_images': ['https://example.com/1.png']}
        original = copy.deepcopy(shot)
        self.assertTrue(contract.matches({}, shot))
        self.assertFalse(contract.has_assistance(shot))
        contract.record_binding(shot)
        self.assertEqual(shot, original)

    def test_adding_assistance_does_not_inherit_legacy_approval(self):
        self.assertFalse(contract.matches({}, {'creative_details': {'action_chain': {'start': '静止'}}}))

    def test_new_binding_changes_for_refs_or_each_assist_field(self):
        shot = {'creative_details': {}, 'reference_images': ['https://example.com/1.png']}
        record = contract.record_binding(shot)
        self.assertTrue(contract.matches(record, shot))
        for key in contract.FIELDS:
            edited = copy.deepcopy(shot);edited['creative_details'][key] = {'test': 'changed'}
            self.assertFalse(contract.matches(record, edited))
        shot['reference_images'] = ['https://example.com/2.png']
        self.assertFalse(contract.matches(record, shot))

    def test_unknown_version_fails_closed(self):
        self.assertFalse(contract.matches({'storyboard_binding_version': 999}, {}))


if __name__ == '__main__':
    unittest.main()
