import unittest

from routes.global_search_routes import (
    ACTIONS,
    PAGES,
    _ACTION_ROLES,
    _PAGE_ROLES,
    _visible_url,
)


class GlobalSearchVisibilityTests(unittest.TestCase):
    def test_every_search_link_has_an_explicit_role_mapping(self):
        page_urls = {page[2] for page in PAGES}
        action_urls = {action[2] for action in ACTIONS}

        self.assertEqual(page_urls - _PAGE_ROLES.keys(), set())
        self.assertEqual(action_urls - _ACTION_ROLES.keys(), set())

    def test_unknown_urls_are_hidden_from_non_super_admin_roles(self):
        self.assertFalse(_visible_url("/admin/new-sensitive-page", "employee", _PAGE_ROLES))

    def test_super_admin_can_see_mapped_and_unmapped_urls(self):
        self.assertTrue(_visible_url("/admin/new-sensitive-page", "super_admin", _PAGE_ROLES))


if __name__ == "__main__":
    unittest.main()
