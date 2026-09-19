import unittest

from ghtoolkit import AuthorRegistry, is_author_match


class IdentityTests(unittest.TestCase):
    def test_default_author_matching(self):
        self.assertTrue(is_author_match("Volcann", login="Volcann"))
        self.assertTrue(is_author_match("volcann", name="Mohsin Ali"))
        self.assertTrue(is_author_match("Volcann", email="mohsinmuhammad823@gmail.com"))
        self.assertTrue(is_author_match("mohsin ali", login="volcann"))

    def test_team_member_aliases(self):
        self.assertTrue(is_author_match("moin bukhari", name="Moin Bukhari"))
        self.assertTrue(is_author_match("moin bukhari", login="mb"))
        self.assertTrue(is_author_match("tayyab sami", login="ts"))
        self.assertTrue(is_author_match("uzair maqsood", login="um"))

    def test_negative_matching(self):
        self.assertFalse(is_author_match("Volcann", login="unknown_contributor"))
        self.assertFalse(
            is_author_match("Volcann", name="Random Person", email="random@test.com")
        )
        self.assertFalse(is_author_match("", login="any"))

    def test_custom_alias_registration(self):
        reg = AuthorRegistry()
        reg.register("charlie", ["Charles Darwin", "cdarwin@evolution.org"])
        self.assertTrue(reg.is_match("charlie", name="Charles Darwin"))
        self.assertTrue(reg.is_match("charlie", email="cdarwin@evolution.org"))
        self.assertFalse(reg.is_match("charlie", name="Alfred Wallace"))


if __name__ == "__main__":
    unittest.main()
