from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from tests.base import BaseTestCase
from extensions import db
from models.activity_type import ActivityType
from models.agenda import AgendaItem
from models.digidokter import Digidokter
from models.evaluation import EvaluationForm, EvaluationQuestion, EvaluationResponse, EvaluationInvitation
from models.location import Location
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from routes.evaluations import (
    get_or_create_evaluation_form,
    get_huidige_digidokter_voor_user,
    kan_evaluatie_bewerken,
    controleer_en_verstuur_afgelopen_evaluaties,
    verstuur_uitnodigingen_voor_sessie,
    verstuur_herinneringen_voor_sessie
)


class TestEvaluationsExtended(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.locatie = Location(naam="Bib Test Extended", actief=True, organisatie_id=self.org.id)
        self.type_digicafe = ActivityType(
            naam="Digicafé Extra",
            actief=True,
            heeft_evaluatie=True,
            organisatie_id=self.org.id
        )
        self.type_geen_eval = ActivityType(
            naam="Consultatie Geen Eval",
            actief=True,
            heeft_evaluatie=False,
            organisatie_id=self.org.id
        )
        db.session.add_all([self.locatie, self.type_digicafe, self.type_geen_eval])
        db.session.commit()

        self.digidokter.user_id = self.medewerker_user.id
        db.session.commit()

    def login_admin(self):
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        return self.client.post('/login', data={
            'email': 'admin@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def login_medewerker(self):
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        return self.client.post('/login', data={
            'email': 'tim@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def test_get_or_create_evaluation_form_creates_standard_questions(self):
        """Test dat get_or_create_evaluation_form een formulier met standaardvragen initialiseert."""
        form = get_or_create_evaluation_form(self.type_digicafe.id, self.org.id)
        self.assertIsNotNone(form)
        self.assertEqual(form.activity_type_id, self.type_digicafe.id)
        self.assertTrue(len(form.vragen) >= 3)
        self.assertIn("Hebben de deelnemers iets geleerd", form.vragen[0].vraag_tekst)

        # Tweede aanroep retourneert hetzelfde formulier zonder dubbele vragen toe te voegen
        form2 = get_or_create_evaluation_form(self.type_digicafe.id, self.org.id)
        self.assertEqual(form.id, form2.id)

    def test_form_and_question_validation_and_reordering(self):
        """Test toevoegen, bewerken, valideren en herordenen van vragen in formulier-editor."""
        self.login_admin()
        form = get_or_create_evaluation_form(self.type_digicafe.id, self.org.id)

        # 1. Formulier details bijwerken
        res_edit_form = self.client.post(f'/admin/evaluaties/{self.type_digicafe.id}/bewerken', data={
            'titel': 'Aangepaste Evaluatie Titel',
            'toelichting': 'Vul deze korte vragen in.',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_edit_form.status_code, 200)
        db.session.refresh(form)
        self.assertEqual(form.titel, 'Aangepaste Evaluatie Titel')
        self.assertEqual(form.toelichting, 'Vul deze korte vragen in.')

        # 2. Vraag toevoegen met lege tekst -> foutmelding
        res_empty_q = self.client.post(f'/admin/evaluaties/formulier/{form.id}/vraag/toevoegen', data={
            'vraag_tekst': '',
            'type': 'open_tekst'
        }, follow_redirects=True)
        self.assertIn("vraagtekst is verplicht", res_empty_q.get_data(as_text=True).lower())

        # 3. Vraag toevoegen met meerkeuze opties per regel
        res_add_mc = self.client.post(f'/admin/evaluaties/formulier/{form.id}/vraag/toevoegen', data={
            'vraag_tekst': 'Hoe vond je de locatie?',
            'type': 'multiple_choice',
            'opties': 'Slecht\nMatig\nGoed\nUitstekend',
            'verplicht': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_add_mc.status_code, 200)

        q_mc = EvaluationQuestion.query.filter_by(form_id=form.id, vraag_tekst='Hoe vond je de locatie?').first()
        self.assertIsNotNone(q_mc)
        self.assertEqual(q_mc.opties_lijst, ['Slecht', 'Matig', 'Goed', 'Uitstekend'])
        self.assertTrue(q_mc.verplicht)

        # 4. Vraag bewerken met lege tekst -> foutmelding
        res_edit_empty = self.client.post(f'/admin/evaluaties/vraag/{q_mc.id}/bewerken', data={
            'vraag_tekst': '',
            'type': 'multiple_choice'
        }, follow_redirects=True)
        self.assertIn("vraagtekst is verplicht", res_edit_empty.get_data(as_text=True).lower())

        # 5. Vraag bewerken met nieuwe opties en velden
        res_edit_ok = self.client.post(f'/admin/evaluaties/vraag/{q_mc.id}/bewerken', data={
            'vraag_tekst': 'Hoe was de locatie en bereikbaarheid?',
            'type': 'open_tekst',
            'opties': ''
        }, follow_redirects=True)
        self.assertEqual(res_edit_ok.status_code, 200)
        db.session.refresh(q_mc)
        self.assertEqual(q_mc.vraag_tekst, 'Hoe was de locatie en bereikbaarheid?')
        self.assertEqual(q_mc.type, 'open_tekst')

        # 6. Vraag volgorde wijzigen omhoog en omlaag
        vragen = EvaluationQuestion.query.filter_by(form_id=form.id).order_by(EvaluationQuestion.volgorde).all()
        q_first = vragen[0]
        q_second = vragen[1]
        v_orig1 = q_first.volgorde
        v_orig2 = q_second.volgorde

        res_omlaag = self.client.get(f'/admin/evaluaties/vraag/{q_first.id}/volgorde/omlaag', follow_redirects=True)
        self.assertEqual(res_omlaag.status_code, 200)
        db.session.refresh(q_first)
        db.session.refresh(q_second)
        self.assertEqual(q_first.volgorde, v_orig2)
        self.assertEqual(q_second.volgorde, v_orig1)

        # 7. Vraag verwijderen
        res_del = self.client.post(f'/admin/evaluaties/vraag/{q_mc.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(db.session.get(EvaluationQuestion, q_mc.id))

    def test_cross_tenant_isolation_in_evaluations(self):
        """Test dat een beheerder geen formulieren, vragen of sessiedetails van een andere organisatie kan inzien/bewerken."""
        org2 = Organisatie(naam="Tenant Twee", slug="tenant-2", actief=True)
        db.session.add(org2)
        db.session.commit()

        loc2 = Location(naam="Bib Org 2", actief=True, organisatie_id=org2.id)
        type_org2 = ActivityType(naam="Type Org 2", actief=True, heeft_evaluatie=True, organisatie_id=org2.id)
        db.session.add_all([loc2, type_org2])
        db.session.commit()

        form_org2 = get_or_create_evaluation_form(type_org2.id, org2.id)
        q_org2 = form_org2.vragen[0]

        agenda_org2 = AgendaItem(
            datum=date.today(),
            uur_van="10:00",
            uur_tot="12:00",
            type_id=type_org2.id,
            locatie_id=loc2.id,
            organisatie_id=org2.id
        )
        db.session.add(agenda_org2)
        db.session.commit()

        self.login_admin()

        # 1. GET formulier editor van org2 -> 404
        res_get_form = self.client.get(f'/admin/evaluaties/{type_org2.id}/bewerken')
        self.assertEqual(res_get_form.status_code, 404)

        # 2. POST vraag toevoegen aan formulier van org2 -> 404
        res_add_q = self.client.post(f'/admin/evaluaties/formulier/{form_org2.id}/vraag/toevoegen', data={
            'vraag_tekst': 'Hack attempt'
        })
        self.assertEqual(res_add_q.status_code, 404)

        # 3. POST vraag bewerken van org2 -> 404
        res_edit_q = self.client.post(f'/admin/evaluaties/vraag/{q_org2.id}/bewerken', data={
            'vraag_tekst': 'Hack attempt'
        })
        self.assertEqual(res_edit_q.status_code, 404)

        # 4. POST vraag verwijderen van org2 -> 404
        res_del_q = self.client.post(f'/admin/evaluaties/vraag/{q_org2.id}/verwijderen')
        self.assertEqual(res_del_q.status_code, 404)

        # 5. GET sessie detail van org2 -> 404
        res_sessie = self.client.get(f'/evaluaties/sessie/{agenda_org2.id}')
        self.assertEqual(res_sessie.status_code, 404)

    def test_kan_evaluatie_bewerken_permission_helper(self):
        """Test unit logic van kan_evaluatie_bewerken permissie helper."""
        form = get_or_create_evaluation_form(self.type_digicafe.id, self.org.id)
        sessie = AgendaItem(
            datum=date.today() - timedelta(days=1),
            uur_van="10:00",
            uur_tot="12:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie.id,
            organisatie_id=self.org.id
        )
        db.session.add(sessie)
        db.session.commit()

        reactie = EvaluationResponse(
            organisatie_id=self.org.id,
            agenda_item_id=sessie.id,
            form_id=form.id,
            digidokter_id=self.digidokter.id,
            user_id=self.medewerker_user.id,
            antwoorden={}
        )
        db.session.add(reactie)
        db.session.commit()

        # 1. Beheerder mag bewerken
        self.assertTrue(kan_evaluatie_bewerken(self.admin_user, reactie, self.org.id))

        # 2. Auteur mag bewerken
        self.assertTrue(kan_evaluatie_bewerken(self.medewerker_user, reactie, self.org.id))

        # 3. Andere medewerker mag niet bewerken
        andere_user = User(naam="Andere Medewerker", email="andere@test.com", wachtwoord_hash="hash", rol="medewerker", actief=True)
        db.session.add(andere_user)
        db.session.commit()
        self.assertFalse(kan_evaluatie_bewerken(andere_user, reactie, self.org.id))

        # 4. Niet-ingelogde gebruiker (None) mag niet bewerken
        self.assertFalse(kan_evaluatie_bewerken(None, reactie, self.org.id))

    def test_verstuur_uitnodigingen_en_herinneringen_routes(self):
        """Test handmatige routes voor versturen van evaluatie-uitnodigingen en herinneringen."""
        sessie = AgendaItem(
            datum=date.today() - timedelta(days=1),
            uur_van="14:00",
            uur_tot="16:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie.id,
            omschrijving="Thema: Veilig surfen",
            organisatie_id=self.org.id
        )
        db.session.add(sessie)
        sessie.digidokters.append(self.digidokter)

        sessie_geen_eval = AgendaItem(
            datum=date.today() - timedelta(days=1),
            uur_van="10:00",
            uur_tot="11:00",
            type_id=self.type_geen_eval.id,
            locatie_id=self.locatie.id,
            organisatie_id=self.org.id
        )
        db.session.add(sessie_geen_eval)
        db.session.commit()

        form = get_or_create_evaluation_form(self.type_digicafe.id, self.org.id)

        self.login_admin()

        # 1. Versturen voor activiteitstype ZONDER evaluatie -> waarschuwing
        res_no_eval = self.client.post(f'/agenda/{sessie_geen_eval.id}/verstuur-evaluaties', follow_redirects=True)
        self.assertIn("geen evaluatieformulier ingeschakeld", res_no_eval.get_data(as_text=True).lower())

        # 2. Versturen voor geldige sessie (met patch op email)
        with patch('routes.evaluations.verstuur_email') as mock_email:
            mock_email.return_value = (True, "OK")
            res_send = self.client.post(f'/agenda/{sessie.id}/verstuur-evaluaties', follow_redirects=True)
            self.assertEqual(res_send.status_code, 200)
            self.assertIn("succesvol verstuurd", res_send.get_data(as_text=True).lower())

            # Uitnodigingstoken moet aangemaakt zijn
            inv = EvaluationInvitation.query.filter_by(agenda_item_id=sessie.id, digidokter_id=self.digidokter.id).first()
            self.assertIsNotNone(inv)
            self.assertFalse(inv.is_ingevuld)

        # 3. Herinnering sturen naar openstaande uitnodiging
        with patch('routes.evaluations.verstuur_email') as mock_email:
            mock_email.return_value = (True, "OK")
            res_remind = self.client.post(f'/agenda/{sessie.id}/verstuur-herinneringen', follow_redirects=True)
            self.assertEqual(res_remind.status_code, 200)
            self.assertIn("herinnering succesvol verstuurd", res_remind.get_data(as_text=True).lower())
            db.session.refresh(inv)
            self.assertIsNotNone(inv.herinnering_verzonden_op)

        # 4. Als evaluatie al is ingevuld -> versturen geeft info flash dat alles al is ingevuld
        resp_obj = EvaluationResponse(
            organisatie_id=self.org.id,
            agenda_item_id=sessie.id,
            form_id=form.id,
            digidokter_id=self.digidokter.id,
            antwoorden={}
        )
        db.session.add(resp_obj)
        db.session.commit()

        res_resend = self.client.post(f'/agenda/{sessie.id}/verstuur-evaluaties', follow_redirects=True)
        self.assertIn("reeds ingevuld of ontvangen", res_resend.get_data(as_text=True).lower())

    def test_controleer_en_verstuur_afgelopen_evaluaties_helper(self):
        """Test automatische achtergrondcheck voor voltooide sessies."""
        gisteren = date.today() - timedelta(days=1)
        sessie = AgendaItem(
            datum=gisteren,
            uur_van="09:00",
            uur_tot="11:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie.id,
            organisatie_id=self.org.id
        )
        db.session.add(sessie)
        sessie.digidokters.append(self.digidokter)
        db.session.commit()

        get_or_create_evaluation_form(self.type_digicafe.id, self.org.id)

        with patch('routes.evaluations.verstuur_email') as mock_email:
            mock_email.return_value = (True, "OK")
            aantal = controleer_en_verstuur_afgelopen_evaluaties(self.org.id, "http://localhost:5000")
            self.assertEqual(aantal, 1)

            # Controleer dat token is aangemaakt
            inv = EvaluationInvitation.query.filter_by(agenda_item_id=sessie.id).first()
            self.assertIsNotNone(inv)

            # Tweede run verstuurt niets extra
            aantal2 = controleer_en_verstuur_afgelopen_evaluaties(self.org.id, "http://localhost:5000")
            self.assertEqual(aantal2, 0)

    def test_in_app_evaluation_required_question_validation(self):
        """Test dat ontbrekende verplichte vragen bij het in-app invullen correct worden gesignaleerd."""
        form = get_or_create_evaluation_form(self.type_digicafe.id, self.org.id)
        vraag_verplicht = form.vragen[0]
        vraag_verplicht.verplicht = True
        db.session.commit()

        sessie = AgendaItem(
            datum=date.today() - timedelta(days=1),
            uur_van="14:00",
            uur_tot="16:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie.id,
            organisatie_id=self.org.id
        )
        sessie.digidokters.append(self.digidokter)
        db.session.add(sessie)
        db.session.commit()

        self.login_medewerker()

        # Inzenden zonder de verplichte vraag in te vullen
        res_post = self.client.post(f'/evaluaties/agenda/{sessie.id}/invullen', data={
            'digidokter_id': self.digidokter.id
            # vraag_verplicht ontbreekt
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn("verplicht", res_post.get_data(as_text=True).lower())

        # Response mag nog niet opgeslagen zijn
        self.assertIsNone(EvaluationResponse.query.filter_by(agenda_item_id=sessie.id).first())

    def test_token_evaluation_required_question_validation(self):
        """Test dat ontbrekende verplichte vragen bij token-inzending correct worden gesignaleerd."""
        form = get_or_create_evaluation_form(self.type_digicafe.id, self.org.id)
        vraag_verplicht = form.vragen[0]
        vraag_verplicht.verplicht = True
        db.session.commit()

        sessie = AgendaItem(
            datum=date.today() - timedelta(days=1),
            uur_van="14:00",
            uur_tot="16:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie.id,
            organisatie_id=self.org.id
        )
        sessie.digidokters.append(self.digidokter)
        db.session.add(sessie)
        db.session.commit()

        invitation = EvaluationInvitation(
            agenda_item_id=sessie.id,
            digidokter_id=self.digidokter.id,
            token="token_validation_test_xyz",
            is_ingevuld=False
        )
        db.session.add(invitation)
        db.session.commit()

        self.logout()

        # Inzenden via token zonder antwoord op verplichte vraag
        res_post = self.client.post('/evaluaties/invullen/token_validation_test_xyz', data={}, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn("verplicht", res_post.get_data(as_text=True).lower())
        db.session.refresh(invitation)
        self.assertFalse(invitation.is_ingevuld)

    def test_reactie_bewerken_cross_tenant_and_non_author_forbidden(self):
        """Test beveiliging op /evaluaties/reactie/<id>/bewerken voor cross-tenant en niet-gemachtigde medewerkers."""
        org2 = Organisatie(naam="Org 2", slug="org2", actief=True)
        db.session.add(org2)
        db.session.commit()

        loc2 = Location(naam="Bib 2", actief=True, organisatie_id=org2.id)
        type2 = ActivityType(naam="Type 2", actief=True, heeft_evaluatie=True, organisatie_id=org2.id)
        db.session.add_all([loc2, type2])
        db.session.commit()

        sessie2 = AgendaItem(datum=date.today(), uur_van="10:00", uur_tot="12:00", type_id=type2.id, locatie_id=loc2.id, organisatie_id=org2.id)
        form2 = get_or_create_evaluation_form(type2.id, org2.id)
        db.session.add(sessie2)
        db.session.commit()

        dd2 = Digidokter(naam="DD 2", actief=True, organisatie_id=org2.id)
        db.session.add(dd2)
        db.session.commit()

        resp2 = EvaluationResponse(
            organisatie_id=org2.id,
            agenda_item_id=sessie2.id,
            form_id=form2.id,
            digidokter_id=dd2.id,
            antwoorden={"1": "Antwoord"}
        )
        db.session.add(resp2)
        db.session.commit()

        self.login_admin()

        # 1. Beheerder van org1 probeert reactie van org2 te bewerken -> 404
        res_cross = self.client.get(f'/evaluaties/reactie/{resp2.id}/bewerken')
        self.assertEqual(res_cross.status_code, 404)

        # 2. Medewerker van org1 probeert reactie van andere medewerker binnen org1 te bewerken
        sessie1 = AgendaItem(datum=date.today(), uur_van="10:00", uur_tot="12:00", type_id=self.type_digicafe.id, locatie_id=self.locatie.id, organisatie_id=self.org.id)
        db.session.add(sessie1)
        db.session.commit()

        dd_admin = Digidokter(naam="DD Admin", user_id=self.admin_user.id, actief=True, organisatie_id=self.org.id)
        db.session.add(dd_admin)
        db.session.commit()

        resp_org1 = EvaluationResponse(
            organisatie_id=self.org.id,
            agenda_item_id=sessie1.id,
            form_id=form2.id,
            digidokter_id=dd_admin.id,
            user_id=self.admin_user.id,
            antwoorden={"1": "Van Admin"}
        )
        db.session.add(resp_org1)
        db.session.commit()

        self.logout()
        self.login_medewerker()

        res_unauth = self.client.post(f'/evaluaties/reactie/{resp_org1.id}/bewerken', data={
            'vraag_1': 'Gehackt door medewerker'
        }, follow_redirects=True)
        self.assertIn("geen rechten", res_unauth.get_data(as_text=True).lower())

    def test_invalid_token_redirects_with_flash(self):
        """Test dat een onbekende token netjes doorverwijst naar login met foutmelding."""
        self.logout()
        res = self.client.get('/evaluaties/invullen/onbekende_random_token_xyz', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("ongeldige of verlopen evaluatielink", res.get_data(as_text=True).lower())
