import io
import os
import tempfile
import urllib.error
from unittest.mock import patch, MagicMock
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.email_template import EmailTemplate
from models.app_document import AppDocument, AppFolder
from utils.mail import verstuur_email, stuur_fout_email, stuur_welkomst_email

class TestMailExtended(BaseTestCase):
    def test_verstuur_email_mail_override(self):
        with patch.dict(os.environ, {
            'MAIL_OVERRIDE_RECIPIENT': 'override@example.com',
            'BREVO_API_KEY': 'test-key'
        }):
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"messageId": "msg-123"}'
            mock_resp.__enter__.return_value = mock_resp

            with patch('urllib.request.urlopen', return_value=mock_resp) as mock_urlopen:
                success, msg = verstuur_email('user@example.com', 'Test Subj', 'Test Body')
                self.assertTrue(success)
                self.assertIn("Succesvol", msg)
                # Verify request payload was sent to override recipient
                req = mock_urlopen.call_args[0][0]
                self.assertIn(b"override@example.com", req.data)

    def test_verstuur_email_brevo_api_with_attachments_and_bcc(self):
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp:
            tmp.write(b"bestandsinhoud")
            tmp_path = tmp.name

        try:
            with patch.dict(os.environ, {
                'BREVO_API_KEY': 'test-key',
                'MAIL_OVERRIDE_RECIPIENT': ''
            }, clear=False):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"messageId": "msg-456"}'
                mock_resp.__enter__.return_value = mock_resp

                with patch('urllib.request.urlopen', return_value=mock_resp):
                    # Test als_bcc=True with both content_bytes and file path attachments
                    success, msg = verstuur_email(
                        ontvangers=['a@example.com', 'b@example.com'],
                        onderwerp='Test',
                        inhoud_tekst='Body',
                        bijlagen=[
                            {'naam': 'inline.txt', 'content_bytes': b'hello'},
                            {'naam': 'disk.txt', 'path': tmp_path}
                        ],
                        als_bcc=True
                    )
                    self.assertTrue(success)
                    self.assertIn("msg-456", msg)

                    # Test bcc as list and als_bcc=False
                    success2, msg2 = verstuur_email(
                        ontvangers=['c@example.com'],
                        onderwerp='Test',
                        inhoud_tekst='Body',
                        bcc=['bcc@example.com'],
                        als_bcc=False
                    )
                    self.assertTrue(success2)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_verstuur_email_brevo_api_error_handling(self):
        with patch.dict(os.environ, {
            'BREVO_API_KEY': 'test-key',
            'SMTP_SERVER': '',
            'MAIL_SERVER': '',
            'MAIL_OVERRIDE_RECIPIENT': ''
        }):
            # Test HTTPError
            http_err = urllib.error.HTTPError('https://api.brevo.com', 400, 'Bad Request', {}, io.BytesIO(b'{"message": "invalid email"}'))
            with patch('urllib.request.urlopen', side_effect=http_err):
                with self.assertRaises(Exception) as ctx:
                    verstuur_email('bad@example.com', 'Test', 'Body')
                self.assertIn("Brevo API Fout (400)", str(ctx.exception))

            # Test generic exception when no SMTP configured
            with patch('urllib.request.urlopen', side_effect=Exception("Network down")):
                with self.assertRaises(Exception) as ctx:
                    verstuur_email('bad@example.com', 'Test', 'Body')
                self.assertIn("Brevo HTTPS API Fout", str(ctx.exception))

    def test_verstuur_email_smtp_success(self):
        with patch.dict(os.environ, {
            'BREVO_API_KEY': '',
            'BREVO_KEY': '',
            'SMTP_USERNAME': 'user',
            'SMTP_PASSWORD': 'password',
            'SMTP_SERVER': 'smtp.example.com',
            'SMTP_PORT': '587',
            'MAIL_OVERRIDE_RECIPIENT': ''
        }):
            mock_smtp = MagicMock()
            with patch('smtplib.SMTP', return_value=mock_smtp) as mock_smtp_cls:
                success, msg = verstuur_email(
                    ontvangers=['recipient@example.com'],
                    onderwerp='SMTP Test',
                    inhoud_tekst='Hello SMTP',
                    bijlagen=[{'naam': 'test.txt', 'content_bytes': b'test content'}],
                    bcc=['bcc@example.com']
                )
                self.assertTrue(success)
                self.assertIn("Succesvol verzonden via SMTP", msg)
                mock_smtp.starttls.assert_called_once()
                mock_smtp.login.assert_called_once_with('user', 'password')
                mock_smtp.sendmail.assert_called_once()

    def test_verstuur_email_smtp_ssl_port_465(self):
        with patch.dict(os.environ, {
            'BREVO_API_KEY': '',
            'BREVO_KEY': '',
            'SMTP_USERNAME': 'user',
            'SMTP_PASSWORD': 'password',
            'SMTP_SERVER': 'smtp.example.com',
            'SMTP_PORT': '465',
            'MAIL_OVERRIDE_RECIPIENT': ''
        }):
            mock_ssl = MagicMock()
            with patch('smtplib.SMTP_SSL', return_value=mock_ssl):
                success, msg = verstuur_email('user@example.com', 'Subj', 'Body')
                self.assertTrue(success)
                mock_ssl.login.assert_called_once()

    def test_verstuur_email_missing_credentials(self):
        with patch.dict(os.environ, {
            'BREVO_API_KEY': '',
            'BREVO_KEY': '',
            'SMTP_USERNAME': '',
            'SMTP_PASSWORD': '',
            'MAIL_USERNAME': '',
            'MAIL_PASSWORD': '',
            'MAIL_OVERRIDE_RECIPIENT': ''
        }):
            with self.assertRaises(Exception) as ctx:
                verstuur_email('test@example.com', 'Test', 'Body')
            self.assertIn("Geen SMTP of Brevo API instellingen", str(ctx.exception))

    def test_stuur_fout_email_no_platform_admins(self):
        with self.app.test_request_context('/test-route'):
            with patch('utils.mail.verstuur_email') as mock_send:
                stuur_fout_email(500, "Ernstige fout")
                mock_send.assert_not_called()

    def test_stuur_fout_email_with_platform_admin(self):
        admin = User(naam="SuperAdmin", email="superadmin@example.com", wachtwoord_hash="x", rol="platformbeheerder")
        db.session.add(admin)
        db.session.commit()

        with self.app.test_request_context('/error-url'):
            with patch('utils.mail.verstuur_email', return_value=(True, "OK")) as mock_send:
                try:
                    raise ValueError("Test value error")
                except ValueError as ex:
                    stuur_fout_email(500, "Crash!", exception=ex)

                mock_send.assert_called_once()
                args, kwargs = mock_send.call_args
                self.assertEqual(args[0], ["superadmin@example.com"])
                self.assertIn("500", args[1])
                self.assertIn("Test value error", args[2])
                self.assertTrue(kwargs.get('als_bcc'))

    def test_stuur_welkomst_email(self):
        # Empty recipient
        ok, msg = stuur_welkomst_email("", "Naam")
        self.assertFalse(ok)
        self.assertIn("Geen e-mailadres", msg)

        # Successful sending with temporary password
        with self.app.test_request_context():
            with patch('utils.mail.verstuur_email', return_value=(True, "Verzonden")) as mock_send:
                ok, msg = stuur_welkomst_email("nieuw@example.com", "Nieuwe Gebruiker", tijdelijk_wachtwoord="Geheim123")
                self.assertTrue(ok)
                mock_send.assert_called_once()
                args = mock_send.call_args[1]
                self.assertIn("Geheim123", args['inhoud_tekst'])
                self.assertEqual(args['ontvangers'], ["nieuw@example.com"])

        # Test with template in DB and AppDocument attached
        tpl = EmailTemplate(
            naam="Welkomstmail",
            sleutel="welkomstmail",
            onderwerp="Welkom {naam}!",
            inhoud="Hallo {naam}, je login is {email}.",
            organisatie_id=self.org.id
        )
        folder = AppFolder(naam="Gebruikershandleidingen", aangemaakt_door_id=self.admin_user.id)
        db.session.add_all([tpl, folder])
        db.session.commit()

        doc = AppDocument(
            map_id=folder.id,
            bestandsnaam="Digidokters_Gebruikershandleiding.docx",
            type="docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            bestandsgrootte=22,
            inhoud=b"Word handleiding bytes",
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(doc)
        db.session.commit()

        with self.app.test_request_context():
            with patch('utils.mail.verstuur_email', return_value=(True, "OK")) as mock_send:
                ok, msg = stuur_welkomst_email("test@example.com", "Jan", organisatie_id=self.org.id)
                self.assertTrue(ok)
                kwargs = mock_send.call_args[1]
                self.assertEqual(kwargs['onderwerp'], "Welkom Jan!")
                self.assertIn("Hallo Jan", kwargs['inhoud_tekst'])
                self.assertEqual(len(kwargs['bijlagen']), 1)
                self.assertEqual(kwargs['bijlagen'][0]['naam'], "Digidokters_Gebruikershandleiding.docx")
