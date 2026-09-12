from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.feedback import FeedbackItem, FeedbackComment, FeedbackView
from utils.feedback_tracker import markeer_feedback_bekeken, get_feedback_meldingen


class TestFeedbackNotifications(BaseTestCase):
    def setUp(self):
        super().setUp()

        # Tweede gebruiker in zelfde organisatie
        self.collega_user = User(
            naam="CollegaKarel",
            email="karel@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.collega_user)
        db.session.commit()

        collega_uo = UserOrganisatie(
            user_id=self.collega_user.id,
            organisatie_id=self.org.id,
            rol="medewerker",
            actief=True
        )
        db.session.add(collega_uo)

        # Tweede organisatie + gebruiker in andere organisatie
        self.andere_org = Organisatie(naam="Gemeente B", slug="gemeente-b", actief=True)
        db.session.add(self.andere_org)
        db.session.commit()

        self.externe_user = User(
            naam="ExterneEva",
            email="eva@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.externe_user)
        db.session.commit()

        externe_uo = UserOrganisatie(
            user_id=self.externe_user.id,
            organisatie_id=self.andere_org.id,
            rol="medewerker",
            actief=True
        )
        db.session.add(externe_uo)

        # Platformbeheerder aanmaken
        self.platform_user = User(
            naam="SuperAdmin",
            email="superadmin@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.platform_user)
        db.session.commit()

        platform_uo = UserOrganisatie(
            user_id=self.platform_user.id,
            organisatie_id=self.org.id,
            rol="beheerder",
            actief=True
        )
        db.session.add(platform_uo)
        db.session.commit()

    def test_markeer_feedback_bekeken_lijst_en_detail(self):
        """Test dat markeer_feedback_bekeken correct records aanmaakt en bijwerkt."""
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.medewerker_user.id,
            type="voorstel",
            onderwerp="Test item",
            beschrijving="Test beschrijving"
        )
        db.session.add(fb)
        db.session.commit()

        # 1. Lijst view registreren
        v_lijst = markeer_feedback_bekeken(self.medewerker_user.id, feedback_id=None)
        self.assertIsNotNone(v_lijst)
        self.assertIsNone(v_lijst.feedback_id)
        t1 = v_lijst.bekeken_op

        # 2. Detail view registreren
        v_detail = markeer_feedback_bekeken(self.medewerker_user.id, feedback_id=fb.id)
        self.assertIsNotNone(v_detail)
        self.assertEqual(v_detail.feedback_id, fb.id)

        # 3. Opnieuw markeren actualiseert timestamp
        v_lijst2 = markeer_feedback_bekeken(self.medewerker_user.id, feedback_id=None)
        self.assertEqual(v_lijst.id, v_lijst2.id)
        self.assertGreaterEqual(v_lijst2.bekeken_op, t1)

    def test_automatische_registratie_via_routes(self):
        """Test dat het bezoeken van /feedback/ en /feedback/<id> de views automatisch registreert."""
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.medewerker_user.id,
            type="voorstel",
            onderwerp="Automatisch bekeken",
            beschrijving="Omschrijving"
        )
        db.session.add(fb)
        db.session.commit()

        self.login("tim@test.com", "password123")

        # Bezoek overzichtspagina
        res = self.client.get("/feedback/")
        self.assertEqual(res.status_code, 200)

        view_lijst = FeedbackView.query.filter_by(user_id=self.medewerker_user.id, feedback_id=None).first()
        self.assertIsNotNone(view_lijst)

        # Bezoek detailpagina
        res2 = self.client.get(f"/feedback/{fb.id}")
        self.assertEqual(res2.status_code, 200)

        view_detail = FeedbackView.query.filter_by(user_id=self.medewerker_user.id, feedback_id=fb.id).first()
        self.assertIsNotNone(view_detail)

    def test_melding_nieuwe_reactie_op_eigen_feedback(self):
        """Test dat de eigenaar van een feedback een melding ziet als een collega reageert."""
        nu = datetime.now(timezone.utc)
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.medewerker_user.id,
            type="voorstel",
            onderwerp="Vergrootglas functie",
            beschrijving="Graag tekstvergroting",
            aangemaakt_op=nu - timedelta(hours=2)
        )
        db.session.add(fb)
        db.session.commit()

        # Eigenaar Tim heeft het item 1 uur geleden bekeken
        markeer_feedback_bekeken(self.medewerker_user.id, feedback_id=fb.id)
        view = FeedbackView.query.filter_by(user_id=self.medewerker_user.id, feedback_id=fb.id).first()
        view.bekeken_op = nu - timedelta(hours=1)
        db.session.commit()

        # Collega Karel plaatst een reactie 10 minuten geleden
        reactie = FeedbackComment(
            feedback_id=fb.id,
            user_id=self.collega_user.id,
            tekst="Goed voorstel, steun ik!",
            aangemaakt_op=nu - timedelta(minutes=10)
        )
        db.session.add(reactie)
        db.session.commit()

        # Tim logt in en bezoekt een willekeurige pagina (bijv. /registraties)
        self.login("tim@test.com", "password123")
        res = self.client.get("/registraties")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # De melding moet zichtbaar zijn
        self.assertIn("Nieuwe reactie op uw feedback", html)
        self.assertIn("Vergrootglas functie", html)
        self.assertIn("CollegaKarel", html)
        self.assertIn(f"/feedback/{fb.id}", html)

        # Tim klikt op de melding en bekijkt het item
        res_detail = self.client.get(f"/feedback/{fb.id}")
        self.assertEqual(res_detail.status_code, 200)

        # Tim navigeert daarna naar de agenda: de melding is nu weg!
        res_agenda = self.client.get("/agenda")
        self.assertEqual(res_agenda.status_code, 200)
        html_agenda = res_agenda.data.decode("utf-8")
        self.assertNotIn("Nieuwe reactie op uw feedback", html_agenda)

    def test_geen_melding_voor_eigen_reactie(self):
        """Test dat een gebruiker geen melding krijgt over een eigen reactie."""
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.medewerker_user.id,
            type="voorstel",
            onderwerp="Eigen item",
            beschrijving="Omschrijving"
        )
        db.session.add(fb)
        db.session.commit()

        reactie = FeedbackComment(
            feedback_id=fb.id,
            user_id=self.medewerker_user.id,  # Zelfde gebruiker
            tekst="Mijn eigen reactie"
        )
        db.session.add(reactie)
        db.session.commit()

        self.login("tim@test.com", "password123")
        res = self.client.get("/registraties")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertNotIn("Nieuwe reactie op uw feedback", html)

    def test_melding_nieuwe_feedback_door_collega(self):
        """Test dat een gebruiker een melding ziet wanneer een collega een nieuw item indient."""
        nu = datetime.now(timezone.utc)

        # Tim heeft de feedbacklijst 2 uur geleden bekeken
        markeer_feedback_bekeken(self.medewerker_user.id, feedback_id=None)
        view = FeedbackView.query.filter_by(user_id=self.medewerker_user.id, feedback_id=None).first()
        view.bekeken_op = nu - timedelta(hours=2)
        db.session.commit()

        # Collega Karel dient 30 minuten geleden een nieuw voorstel in
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.collega_user.id,
            type="voorstel",
            onderwerp="Nieuwe printknop",
            beschrijving="Graag een snelle knop om consultaties af te drukken",
            aangemaakt_op=nu - timedelta(minutes=30)
        )
        db.session.add(fb)
        db.session.commit()

        # Tim bezoekt de agenda
        self.login("tim@test.com", "password123")
        res = self.client.get("/agenda")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # Melding moet zichtbaar zijn
        self.assertIn("Nieuw voorstel", html)
        self.assertIn("Nieuwe printknop", html)
        self.assertIn("CollegaKarel", html)

        # Tim bezoekt de feedback overzichtspagina
        res_lijst = self.client.get("/feedback/")
        self.assertEqual(res_lijst.status_code, 200)

        # Tim navigeert naar een andere pagina: melding is verdwenen
        res_reg = self.client.get("/registraties")
        self.assertEqual(res_reg.status_code, 200)
        html_reg = res_reg.data.decode("utf-8")
        self.assertNotIn("Nieuwe printknop", html_reg)

    def test_melding_wegklikken(self):
        """Test dat het wegklikken (POST melding-wegklikken) de melding direct markeert als gelezen."""
        nu = datetime.now(timezone.utc)
        self.medewerker_user.aangemaakt_op = nu - timedelta(hours=2)
        db.session.commit()

        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.collega_user.id,
            type="foutje",
            onderwerp="Scrollbar ontbreekt",
            beschrijving="Op mobiel zie ik geen scrollbar",
            aangemaakt_op=nu - timedelta(minutes=15)
        )
        db.session.add(fb)
        db.session.commit()

        self.login("tim@test.com", "password123")
        res = self.client.get("/registraties")
        self.assertIn("Scrollbar ontbreekt", res.data.decode("utf-8"))

        # POST wegklikken
        res_close = self.client.post("/feedback/melding-wegklikken", data={
            "melding_code": "new_feedback",
            "item_id": fb.id
        }, follow_redirects=True)
        self.assertEqual(res_close.status_code, 200)

        # Controleer dat de melding weg is
        res_after = self.client.get("/registraties")
        self.assertNotIn("Scrollbar ontbreekt", res_after.data.decode("utf-8"))

    def test_multi_tenant_isolatie_meldingen(self):
        """Test dat een gebruiker geen melding krijgt van een feedback uit een andere gemeente, behalve platformadmin."""
        nu = datetime.now(timezone.utc)
        self.platform_user.aangemaakt_op = nu - timedelta(hours=2)
        self.medewerker_user.aangemaakt_op = nu - timedelta(hours=2)
        db.session.commit()

        fb = FeedbackItem(
            organisatie_id=self.andere_org.id,  # Gemeente B
            user_id=self.externe_user.id,
            type="voorstel",
            onderwerp="Gemeente B voorstel",
            beschrijving="Enkel voor Gemeente B",
            aangemaakt_op=nu - timedelta(minutes=10)
        )
        db.session.add(fb)
        db.session.commit()

        # Tim (Gemeente A) mag dit NIET zien
        self.login("tim@test.com", "password123")
        res_tim = self.client.get("/registraties")
        self.assertNotIn("Gemeente B voorstel", res_tim.data.decode("utf-8"))
        self.logout()

        # Platformbeheerder ziet het WEL
        self.login("superadmin@test.com", "password123")
        self.select_organisatie(self.org.id)
        res_admin = self.client.get("/registraties")
        self.assertIn("Gemeente B voorstel", res_admin.data.decode("utf-8"))

