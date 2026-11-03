from datetime import date, datetime
import unittest

from utils.helpers import is_veilige_redirect, safe_int, safe_date, safe_str


class TestHelpers(unittest.TestCase):
    """Unit tests voor utils/helpers.py."""

    # -------------------------------------------------------------------------
    # is_veilige_redirect
    # -------------------------------------------------------------------------
    def test_is_veilige_redirect_geldige_relatieve_urls(self):
        """Test dat geldige interne relatieve paden worden geaccepteerd."""
        self.assertTrue(is_veilige_redirect("/"))
        self.assertTrue(is_veilige_redirect("/agenda"))
        self.assertTrue(is_veilige_redirect("/registraties?zoek=test&pagina=2"))
        self.assertTrue(is_veilige_redirect("/beheer/gebruikers/1/wijzig#tab"))

    def test_is_veilige_redirect_ongeldige_en_onveilige_urls(self):
        """Test dat absolute URL's, scheme-relative URL's en ongeldige waarden worden geweigerd."""
        self.assertFalse(is_veilige_redirect(""))
        self.assertFalse(is_veilige_redirect(None))
        self.assertFalse(is_veilige_redirect("https://evil.com"))
        self.assertFalse(is_veilige_redirect("http://evil.com/phishing"))
        self.assertFalse(is_veilige_redirect("//evil.com"))
        self.assertFalse(is_veilige_redirect("///evil.com"))
        self.assertFalse(is_veilige_redirect("javascript:alert(1)"))
        self.assertFalse(is_veilige_redirect("agenda/overzicht"))  # relatief zonder leidende slash

    # -------------------------------------------------------------------------
    # safe_int
    # -------------------------------------------------------------------------
    def test_safe_int_geldige_waarden(self):
        """Test safe_int met gehele getallen en numerieke strings."""
        self.assertEqual(safe_int(42), 42)
        self.assertEqual(safe_int("123"), 123)
        self.assertEqual(safe_int("-15"), -15)
        self.assertEqual(safe_int(0), 0)
        self.assertEqual(safe_int("0"), 0)

    def test_safe_int_ongeldige_en_leeg_waarden(self):
        """Test safe_int met None, niet-numerieke strings en ongeldige types."""
        self.assertIsNone(safe_int(None))
        self.assertIsNone(safe_int(""))
        self.assertIsNone(safe_int("abc"))
        self.assertIsNone(safe_int("12.34"))
        self.assertIsNone(safe_int([]))
        self.assertIsNone(safe_int({}))

        # Met aangepaste default waarde
        self.assertEqual(safe_int(None, default=10), 10)
        self.assertEqual(safe_int("ongeldig", default=99), 99)
        self.assertEqual(safe_int([], default=0), 0)

    # -------------------------------------------------------------------------
    # safe_date
    # -------------------------------------------------------------------------
    def test_safe_date_geldige_waarden(self):
        """Test safe_date met ISO-strings, date-objecten en datetime-objecten."""
        vandaag = date(2026, 11, 2)
        nu = datetime(2026, 11, 2, 14, 30, 0)

        # Date object direct
        self.assertEqual(safe_date(vandaag), vandaag)

        # Datetime object (moet val.date() teruggeven)
        self.assertEqual(safe_date(nu), vandaag)

        # Geldige ISO datumstring
        self.assertEqual(safe_date("2026-11-02"), vandaag)
        self.assertEqual(safe_date("  2026-11-02  "), vandaag)  # met witruimte

    def test_safe_date_ongeldige_en_leeg_waarden(self):
        """Test safe_date met None, lege strings en ongeldige datums."""
        self.assertIsNone(safe_date(None))
        self.assertIsNone(safe_date(""))
        self.assertIsNone(safe_date("   "))
        self.assertIsNone(safe_date("02-11-2026"))  # niet-ISO
        self.assertIsNone(safe_date("geen-datum"))
        self.assertIsNone(safe_date("2026-13-45"))  # ongeldige kalenderdatum
        self.assertIsNone(safe_date(12345))

        # Met aangepaste default waarde
        standaard = date(2026, 1, 1)
        self.assertEqual(safe_date(None, default=standaard), standaard)
        self.assertEqual(safe_date("", default=standaard), standaard)
        self.assertEqual(safe_date("fout", default=standaard), standaard)

    # -------------------------------------------------------------------------
    # safe_str
    # -------------------------------------------------------------------------
    def test_safe_str(self):
        """Test safe_str met verschillende input types en witruimte."""
        self.assertEqual(safe_str("  hallo  "), "hallo")
        self.assertEqual(safe_str("woord"), "woord")
        self.assertEqual(safe_str(""), "")
        self.assertEqual(safe_str(123), "123")
        self.assertEqual(safe_str(True), "True")

        # None input
        self.assertEqual(safe_str(None), "")
        self.assertEqual(safe_str(None, default="onbekend"), "onbekend")

