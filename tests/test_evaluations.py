from datetime import date, datetime, timedelta
from tests.base import BaseTestCase
from extensions import db
from models.activity_type import ActivityType
from models.agenda import AgendaItem
from models.digidokter import Digidokter
from models.evaluation import EvaluationForm, EvaluationQuestion, EvaluationResponse, EvaluationInvitation
from models.location import Location


class TestEvaluations(BaseTestCase):
    def setUp(self):
        super().setUp()

        # Create Location and ActivityTypes
        self.locatie = Location(naam="Bib Test", actief=True, organisatie_id=self.org.id)
        self.type_digicafe = ActivityType(
            naam="Digicafé",
            actief=True,
            heeft_evaluatie=True,
            organisatie_id=self.org.id
        )
        self.type_overig = ActivityType(
            naam="Overig",
            actief=True,
            heeft_evaluatie=False,
            organisatie_id=self.org.id
        )
        db.session.add_all([self.locatie, self.type_digicafe, self.type_overig])
        db.session.commit()

        # Link digidokter to user for test
        self.digidokter.user_id = self.medewerker_user.id
        db.session.commit()

    def test_activity_type_heeft_evaluatie_flag(self):
        """Test dat de vlag heeft_evaluatie correct kan worden ingesteld en gewijzigd."""
        self.login('AdminMark', 'password123')
        
        # Nieuw activiteitstype met evaluatie aanmaken
        resp = self.client.post('/beheer/activiteitstypes/nieuw', data={
            'naam': 'Workshop AI',
            'actief': 'on',
            'heeft_evaluatie': 'on',
            'kleur': 'purple'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        created = ActivityType.query.filter_by(naam='Workshop AI', organisatie_id=self.org.id).first()
        self.assertIsNotNone(created)
        self.assertTrue(created.heeft_evaluatie)

        # Wijzigen: vlag uitzetten
        resp2 = self.client.post(f'/beheer/activiteitstypes/{created.id}/wijzig', data={
            'naam': 'Workshop AI',
            'actief': 'on',
            'kleur': 'purple'
            # heeft_evaluatie niet meegestuurd -> False
        }, follow_redirects=True)
        self.assertEqual(resp2.status_code, 200)
        db.session.refresh(created)
        self.assertFalse(created.heeft_evaluatie)

    def test_evaluation_form_and_questions_management(self):
        """Test dat een beheerder vragen kan toevoegen, bewerken, van volgorde wijzigen en verwijderen."""
        self.login('AdminMark', 'password123')

        # Open formulier editor
        resp = self.client.get(f'/admin/evaluaties/{self.type_digicafe.id}/bewerken')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Evaluatieformulier: Digicaf', resp.data)

        form = EvaluationForm.query.filter_by(activity_type_id=self.type_digicafe.id).first()
        self.assertIsNotNone(form)

        # Voeg een multiple choice vraag toe
        resp_add = self.client.post(f'/admin/evaluaties/formulier/{form.id}/vraag/toevoegen', data={
            'vraag_tekst': 'Hoeveel bezoekers waren er?',
            'type': 'multiple_choice',
            'opties': '1 tot 5\n6 tot 10\nMeer dan 10',
            'verplicht': 'on'
        }, follow_redirects=True)
        self.assertEqual(resp_add.status_code, 200)

        v1 = EvaluationQuestion.query.filter_by(form_id=form.id, vraag_tekst='Hoeveel bezoekers waren er?').first()
        self.assertIsNotNone(v1)
        self.assertEqual(v1.type, 'multiple_choice')
        self.assertEqual(len(v1.opties_lijst), 3)

        # Voeg een open tekst vraag toe
        resp_add2 = self.client.post(f'/admin/evaluaties/formulier/{form.id}/vraag/toevoegen', data={
            'vraag_tekst': 'Vrije opmerkingen:',
            'type': 'open_tekst',
            'opties': '',
        }, follow_redirects=True)
        self.assertEqual(resp_add2.status_code, 200)

        v2 = EvaluationQuestion.query.filter_by(form_id=form.id, vraag_tekst='Vrije opmerkingen:').first()
        self.assertIsNotNone(v2)
        self.assertEqual(v2.type, 'open_tekst')
        self.assertFalse(v2.verplicht)

        # Vraag bewerken
        resp_edit = self.client.post(f'/admin/evaluaties/vraag/{v1.id}/bewerken', data={
            'vraag_tekst': 'Hoeveel bezoekers waren er vandaag?',
            'type': 'multiple_choice',
            'opties': 'Weinig\nGemiddeld\nVeel',
            'verplicht': 'on'
        }, follow_redirects=True)
        self.assertEqual(resp_edit.status_code, 200)
        db.session.refresh(v1)
        self.assertEqual(v1.vraag_tekst, 'Hoeveel bezoekers waren er vandaag?')

        # Vraag verwijderen
        resp_del = self.client.post(f'/admin/evaluaties/vraag/{v2.id}/verwijderen', follow_redirects=True)
        self.assertEqual(resp_del.status_code, 200)
        self.assertIsNone(db.session.get(EvaluationQuestion, v2.id))

    def test_permission_restrictions_for_editor(self):
        """Medewerkers mogen de formulieren niet bewerken, enkel beheerders."""
        self.login('UserTim', 'password123')  # Medewerker
        resp = self.client.get(f'/admin/evaluaties/{self.type_digicafe.id}/bewerken', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        resp_follow = self.client.get(f'/admin/evaluaties/{self.type_digicafe.id}/bewerken', follow_redirects=True)
        self.assertIn(b'geen toegang', resp_follow.data.lower())

    def test_fill_and_submit_evaluation_by_logged_in_user(self):
        """Test dat een ingelogde medewerker/digidokter een evaluatieformulier kan invullen en opslaan."""
        # Maak een sessie aan in het verleden
        gisteren = date.today() - timedelta(days=1)
        agenda_item = AgendaItem(
            datum=gisteren,
            uur_van="14:00",
            uur_tot="16:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie.id,
            organisatie_id=self.org.id
        )
        agenda_item.digidokters.append(self.digidokter)
        db.session.add(agenda_item)
        db.session.commit()

        # Maak evaluatieformulier aan
        form = EvaluationForm(
            organisatie_id=self.org.id,
            activity_type_id=self.type_digicafe.id,
            titel="Evaluatie Digicafé Test"
        )
        db.session.add(form)
        db.session.flush()

        v1 = EvaluationQuestion(
            form_id=form.id,
            vraag_tekst="Hoeveel deelnemers?",
            type="multiple_choice",
            opties=["Weinig", "Veel"],
            volgorde=1,
            verplicht=True
        )
        v2 = EvaluationQuestion(
            form_id=form.id,
            vraag_tekst="Opmerkingen:",
            type="open_tekst",
            opties=[],
            volgorde=2,
            verplicht=False
        )
        db.session.add_all([v1, v2])
        db.session.commit()

        # Inloggen als medewerker (gekoppeld aan digidokter)
        self.login('UserTim', 'password123')

        # Formulier openen
        resp_get = self.client.get(f'/evaluaties/agenda/{agenda_item.id}/invullen')
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn(b'Evaluatie Digicaf', resp_get.data)

        # Formulier inzenden
        resp_post = self.client.post(f'/evaluaties/agenda/{agenda_item.id}/invullen', data={
            'digidokter_id': self.digidokter.id,
            f'vraag_{v1.id}': 'Veel',
            f'vraag_{v2.id}': 'Zeer geslaagde namiddag met actieve senioren.'
        }, follow_redirects=True)
        self.assertEqual(resp_post.status_code, 200)

        # Controleer dat de reactie in de database staat
        reactie = EvaluationResponse.query.filter_by(agenda_item_id=agenda_item.id, digidokter_id=self.digidokter.id).first()
        self.assertIsNotNone(reactie)
        self.assertEqual(reactie.antwoorden.get(str(v1.id)), 'Veel')
        self.assertEqual(reactie.antwoorden.get(str(v2.id)), 'Zeer geslaagde namiddag met actieve senioren.')
        self.assertIsNotNone(reactie.ingediend_op)

        # Opnieuw proberen in te vullen voor dezelfde digidokter moet een melding geven
        resp_dup = self.client.post(f'/evaluaties/agenda/{agenda_item.id}/invullen', data={
            'digidokter_id': self.digidokter.id,
            f'vraag_{v1.id}': 'Weinig'
        }, follow_redirects=True)
        self.assertIn(b'al eerder ingevuld', resp_dup.data)

    def test_evaluation_token_direct_link(self):
        """Test dat een digidokter via de unieke e-mail link (token) de evaluatie kan invullen."""
        gisteren = date.today() - timedelta(days=1)
        agenda_item = AgendaItem(
            datum=gisteren,
            uur_van="10:00",
            uur_tot="12:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie.id,
            organisatie_id=self.org.id
        )
        agenda_item.digidokters.append(self.digidokter)
        db.session.add(agenda_item)
        db.session.commit()

        form = EvaluationForm(organisatie_id=self.org.id, activity_type_id=self.type_digicafe.id, titel="Digicafé Evaluatie")
        db.session.add(form)
        db.session.flush()
        vraag = EvaluationQuestion(form_id=form.id, vraag_tekst="Tevreden?", type="multiple_choice", opties=["Ja", "Nee"], volgorde=1, verplicht=True)
        db.session.add(vraag)
        db.session.commit()

        # Maak een uitnodigingstoken
        invitation = EvaluationInvitation(
            agenda_item_id=agenda_item.id,
            digidokter_id=self.digidokter.id,
            token="secure_test_token_12345",
            is_ingevuld=False
        )
        db.session.add(invitation)
        db.session.commit()

        # Uitloggen (publieke token route)
        self.logout()

        # Formulier openen via token
        resp_get = self.client.get(f'/evaluaties/invullen/{invitation.token}')
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn(b'Tevreden?', resp_get.data)

        # Formulier inzenden via token
        resp_post = self.client.post(f'/evaluaties/invullen/{invitation.token}', data={
            f'vraag_{vraag.id}': 'Ja'
        }, follow_redirects=True)
        self.assertEqual(resp_post.status_code, 200)
        self.assertIn(b'Hartelijk dank', resp_post.data)

        # Token status moet bijgewerkt zijn
        db.session.refresh(invitation)
        self.assertTrue(invitation.is_ingevuld)

        # Tweede bezoek aan token link toont reeds ingevuld
        resp_again = self.client.get(f'/evaluaties/invullen/{invitation.token}')
        self.assertIn(b'Reeds ingevuld', resp_again.data)

    def test_results_overview_and_detail(self):
        """Test dat beheerders de resultatenpagina en sessiedetails kunnen bekijken, inclusief enkel_ingevuld filter."""
        self.login('AdminMark', 'password123')

        # Maak 2 sessies aan: 1 met reactie, 1 zonder
        gisteren = date.today() - timedelta(days=1)
        sessie1 = AgendaItem(datum=gisteren, uur_van="10:00", uur_tot="12:00", type_id=self.type_digicafe.id, locatie_id=self.locatie.id, organisatie_id=self.org.id)
        sessie2 = AgendaItem(datum=gisteren, uur_van="14:00", uur_tot="16:00", type_id=self.type_digicafe.id, locatie_id=self.locatie.id, organisatie_id=self.org.id)
        db.session.add_all([sessie1, sessie2])
        db.session.commit()

        form = EvaluationForm(organisatie_id=self.org.id, activity_type_id=self.type_digicafe.id, titel="Digicafé Evaluatie")
        db.session.add(form)
        db.session.flush()
        vraag = EvaluationQuestion(form_id=form.id, vraag_tekst="Vraag 1", type="open_tekst", opties=[], volgorde=1, verplicht=False)
        db.session.add(vraag)
        db.session.commit()

        reactie = EvaluationResponse(organisatie_id=self.org.id, agenda_item_id=sessie1.id, form_id=form.id, digidokter_id=self.digidokter.id, antwoorden={"1": "Goed"})
        db.session.add(reactie)
        db.session.commit()

        # Overzichtspagina zonder filter: toont beide sessies
        resp_alle = self.client.get('/admin/evaluaties/resultaten')
        self.assertEqual(resp_alle.status_code, 200)
        self.assertIn(b'10:00 - 12:00', resp_alle.data)
        self.assertIn(b'14:00 - 16:00', resp_alle.data)

        # Overzichtspagina met enkel_ingevuld=on filter: toont enkel sessie1
        resp_filtered = self.client.get('/admin/evaluaties/resultaten?enkel_ingevuld=on')
        self.assertEqual(resp_filtered.status_code, 200)
        self.assertIn(b'10:00 - 12:00', resp_filtered.data)
        self.assertNotIn(b'14:00 - 16:00', resp_filtered.data)

        # Detailpagina voor sessie1
        resp_detail = self.client.get(f'/admin/evaluaties/sessie/{sessie1.id}')
        self.assertEqual(resp_detail.status_code, 200)
        self.assertIn(b'Goed', resp_detail.data)

        # Dashboard overzicht
        resp_dash = self.client.get('/admin/evaluaties')
        self.assertEqual(resp_dash.status_code, 200)
        self.assertIn(b'Formulieren per Activiteitstype', resp_dash.data)
