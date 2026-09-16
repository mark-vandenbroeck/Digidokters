from datetime import date
from tests.base import BaseTestCase
from extensions import db
from models.registration import Registration
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.gender_identity import GenderIdentity
from models.location import Location


class TestQuickRegistration(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # Haal standaard seed-data op
        self.dok = Digidokter.query.filter_by(organisatie_id=self.org.id, actief=True).first()
        self.age = AgeCategory.query.filter_by(organisatie_id=self.org.id, actief=True).first()
        self.dev = Device.query.filter_by(organisatie_id=self.org.id, actief=True).first()
        self.loc = Location.query.filter_by(organisatie_id=self.org.id, actief=True, gebruikt_voor_consultaties=True).first()

    def test_quick_registration_get_renders_page(self):
        res = self.client.get('/registraties/snel')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Snelle balie-registratie', html)
        self.assertIn('Opslaan & Volgende bezoeker', html)
        self.assertIn('itsme', html)
        self.assertIn('WhatsApp', html)
        self.assertIn(self.dok.naam, html)

    def test_quick_registration_post_saves_record_and_redirects(self):
        res = self.client.post('/registraties/snel', data={
            'datum': str(date.today()),
            'client': 'Marie K.',
            'nieuwe_klant': 'ja',
            'geslacht': 'Vrouw',
            'digidokter_id': str(self.dok.id),
            'leeftijdscategorie_id': str(self.age.id),
            'toestel_id': str(self.dev.id),
            'locatie_id': str(self.loc.id) if self.loc else '',
            'onderwerp': 'Hulp bij aanmelden itsme na nieuwe smartphone',
            'actie': 'volgende'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('succesvol opgeslagen', html)

        # Verifieer in database
        reg = Registration.query.filter_by(organisatie_id=self.org.id, client='Marie K.').first()
        self.assertIsNotNone(reg)
        self.assertTrue(reg.nieuwe_klant)
        self.assertEqual(reg.geslacht, 'Vrouw')
        self.assertEqual(reg.digidokter_id, self.dok.id)
        self.assertEqual(reg.leeftijdscategorie_id, self.age.id)
        self.assertEqual(reg.toestel_id, self.dev.id)
        self.assertIn('itsme', reg.onderwerp)

        # Controleer dat sessie-context bewaard is gebleven
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('snelle_reg_digidokter_id'), self.dok.id)
            if self.loc:
                self.assertEqual(sess.get('snelle_reg_locatie_id'), self.loc.id)
            self.assertEqual(sess.get('snelle_reg_datum'), str(date.today()))

    def test_quick_registration_post_actie_overzicht(self):
        res = self.client.post('/registraties/snel', data={
            'datum': str(date.today()),
            'client': 'Jozef D.',
            'nieuwe_klant': 'nee',
            'geslacht': 'Man',
            'digidokter_id': str(self.dok.id),
            'leeftijdscategorie_id': str(self.age.id),
            'toestel_id': str(self.dev.id),
            'locatie_id': str(self.loc.id) if self.loc else '',
            'onderwerp': 'Vraag over eBox documenten',
            'actie': 'overzicht'
        }, follow_redirects=False)

        # Moet redirecten naar /registraties
        self.assertEqual(res.status_code, 302)
        self.assertIn('/registraties', res.headers.get('Location', ''))

        reg = Registration.query.filter_by(organisatie_id=self.org.id, client='Jozef D.').first()
        self.assertIsNotNone(reg)
        self.assertFalse(reg.nieuwe_klant)

    def test_quick_registration_validation_errors(self):
        # Ontbrekende client en onderwerp
        res = self.client.post('/registraties/snel', data={
            'datum': str(date.today()),
            'client': '',
            'digidokter_id': str(self.dok.id),
            'leeftijdscategorie_id': str(self.age.id),
            'toestel_id': str(self.dev.id),
            'onderwerp': ''
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('Naam of initialen van de bezoeker is verplicht', html)
        self.assertIn('Onderwerp/vraag is verplicht', html)

    def test_quick_registration_reader_is_blocked(self):
        from werkzeug.security import generate_password_hash
        from models.user import User
        from models.organisatie import UserOrganisatie

        reader = User(
            naam="ReaderAnn",
            email="reader@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="lezer",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(reader)
        db.session.commit()

        uo = UserOrganisatie(
            user_id=reader.id,
            organisatie_id=self.org.id,
            rol="lezer",
            actief=True
        )
        db.session.add(uo)
        db.session.commit()

        self.logout()
        self.login("ReaderAnn", "password123")
        self.select_organisatie(self.org.id)

        res = self.client.get('/registraties/snel', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('U heeft geen schrijfrechten voor deze organisatie', html)

    def test_quick_registration_sjabloon_org_is_blocked(self):
        from models.organisatie import Organisatie
        sjabloon = Organisatie(naam="Sjabloon", slug="sjabloon", actief=True)
        db.session.add(sjabloon)
        db.session.commit()

        # Login as platformbeheerder
        self.admin_user.rol = "platformbeheerder"
        db.session.commit()

        self.logout()
        self.login("AdminMark", "password123")
        self.client.post('/switch-organisatie', data={'organisatie_id': sjabloon.id}, follow_redirects=True)

        res = self.client.get('/registraties/snel', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('leeftijdscategorie', res.headers.get('Location', ''))
