import io
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import UserOrganisatie
from models.feedback import FeedbackItem, FeedbackVote, FeedbackComment


class TestFeedback(BaseTestCase):
    def setUp(self):
        super().setUp()

        # Create a lezer user
        self.lezer_user = User(
            naam="LezerLies",
            email="lezer@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="lezer",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.lezer_user)
        db.session.commit()

        lezer_membership = UserOrganisatie(
            user_id=self.lezer_user.id,
            organisatie_id=self.org.id,
            rol="lezer",
            actief=True
        )
        db.session.add(lezer_membership)
        db.session.commit()

    def test_sidebar_contains_algemeen_and_feedback(self):
        """Controleer of de nieuwe rubriek 'Algemeen' en 'Feedback' aanwezig zijn in het menu."""
        self.login("admin@test.com", "password123")
        res = self.client.get("/feedback/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Algemeen", res.data.decode("utf-8"))
        self.assertIn("Feedback", res.data.decode("utf-8"))
        self.assertIn("Privacy & AVG", res.data.decode("utf-8"))

    def test_feedback_creatie_voorstel_en_foutje(self):
        """Test aanmaken van feedback items met type 'voorstel' en 'foutje'."""
        self.login("tim@test.com", "password123")

        # GET nieuw formulier
        res = self.client.get("/feedback/nieuw")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Voorstel", html)
        self.assertIn("Foutje?", html)
        self.assertIn("UserTim", html)  # automatische gebruikersnaam weergave

        # POST nieuw voorstel
        res = self.client.post("/feedback/nieuw", data={
            "type": "voorstel",
            "onderwerp": "Donkere modus toevoegen",
            "beschrijving": "Het zou handig zijn om een donkere modus te hebben voor 's avonds."
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        fb = FeedbackItem.query.filter_by(onderwerp="Donkere modus toevoegen").first()
        self.assertIsNotNone(fb)
        self.assertEqual(fb.type, "voorstel")
        self.assertEqual(fb.type_label, "Voorstel")
        self.assertEqual(fb.user_id, self.medewerker_user.id)
        self.assertFalse(fb.is_afgesloten)

        # POST foutje met screenshot (dummy PNG)
        png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
        res = self.client.post("/feedback/nieuw", data={
            "type": "foutje",
            "onderwerp": "Knop reageert niet op mobiel",
            "beschrijving": "Als ik op mobiel klik, gebeurt er niets.",
            "screenshot": (io.BytesIO(png_data), "screenshot.png")
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        fb_foutje = FeedbackItem.query.filter_by(onderwerp="Knop reageert niet op mobiel").first()
        self.assertIsNotNone(fb_foutje)
        self.assertEqual(fb_foutje.type, "foutje")
        self.assertEqual(fb_foutje.type_label, "Foutje?")
        self.assertEqual(fb_foutje.screenshot_naam, "screenshot.png")
        self.assertIsNotNone(fb_foutje.screenshot_data)

        # Test downloaden/bekijken screenshot
        res_screen = self.client.get(f"/feedback/{fb_foutje.id}/screenshot")
        self.assertEqual(res_screen.status_code, 200)
        self.assertEqual(res_screen.data, png_data)

    def test_sortering_aflopend_en_greyed_out(self):
        """Test dat items aflopend op aanmaakdatum gesorteerd zijn en gesloten items greyed-out getoond worden."""
        self.login("admin@test.com", "password123")

        nu = datetime.now(timezone.utc)
        item1 = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.admin_user.id,
            type="voorstel",
            onderwerp="Oudste voorstel",
            beschrijving="Omschrijving 1",
            aangemaakt_op=nu - timedelta(days=2),
            is_afgesloten=True
        )
        item2 = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.admin_user.id,
            type="foutje",
            onderwerp="Nieuwste foutje",
            beschrijving="Omschrijving 2",
            aangemaakt_op=nu,
            is_afgesloten=False
        )
        db.session.add_all([item1, item2])
        db.session.commit()

        res = self.client.get("/feedback/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # Nieuwste item moet eerst in de HTML voorkomen
        pos_nieuw = html.find("Nieuwste foutje")
        pos_oud = html.find("Oudste voorstel")
        self.assertTrue(pos_nieuw < pos_oud, "Nieuwste item moet vóór het oudere item in de lijst staan.")

        # Afgesloten item moet greyed out indicatie en afgesloten badge hebben
        self.assertIn("opacity-75", html)
        self.assertIn("Afgesloten", html)

    def test_stemmen_duimpjes(self):
        """Test stemmen met duimpje omhoog en duimpje omlaag."""
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.admin_user.id,
            type="voorstel",
            onderwerp="Betere zoekbalk",
            beschrijving="Zoeken op meerdere velden tegelijk.",
            aangemaakt_op=datetime.now(timezone.utc)
        )
        db.session.add(fb)
        db.session.commit()

        # Medewerker stemt duimpje omhoog (+1)
        self.login("tim@test.com", "password123")
        res = self.client.post(f"/feedback/{fb.id}/stem", data={"stem": "1"}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        db.session.refresh(fb)
        self.assertEqual(fb.stemmen_voor, 1)
        self.assertEqual(fb.stemmen_tegen, 0)
        self.assertEqual(fb.gebruiker_stem(self.medewerker_user.id), 1)

        # Klikt nogmaals op duim omhoog -> intrekken stem
        self.client.post(f"/feedback/{fb.id}/stem", data={"stem": "1"}, follow_redirects=True)
        db.session.refresh(fb)
        self.assertEqual(fb.stemmen_voor, 0)

        # Klikt op duimpje omlaag (-1)
        self.client.post(f"/feedback/{fb.id}/stem", data={"stem": "-1"}, follow_redirects=True)
        db.session.refresh(fb)
        self.assertEqual(fb.stemmen_voor, 0)
        self.assertEqual(fb.stemmen_tegen, 1)

        # Admin stemt duimpje omhoog (+1)
        self.logout()
        self.login("admin@test.com", "password123")
        self.client.post(f"/feedback/{fb.id}/stem", data={"stem": "1"}, follow_redirects=True)
        db.session.refresh(fb)
        self.assertEqual(fb.stemmen_voor, 1)
        self.assertEqual(fb.stemmen_tegen, 1)

    def test_conversatie_reacties(self):
        """Test dat gebruikers reacties kunnen plaatsen in de conversatie onder feedback."""
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.admin_user.id,
            type="voorstel",
            onderwerp="Export naar PDF",
            beschrijving="Graag export naar PDF voorzien.",
            aangemaakt_op=datetime.now(timezone.utc)
        )
        db.session.add(fb)
        db.session.commit()

        # Medewerker plaatst een reactie
        self.login("tim@test.com", "password123")
        res = self.client.post(f"/feedback/{fb.id}/reageer", data={
            "tekst": "Heel goed idee, dat zou ons veel tijd besparen!"
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        db.session.refresh(fb)
        self.assertEqual(len(fb.reacties), 1)
        self.assertEqual(fb.reacties[0].user_id, self.medewerker_user.id)
        self.assertEqual(fb.reacties[0].tekst, "Heel goed idee, dat zou ons veel tijd besparen!")

        # Controleer weergave op detailpagina
        res_detail = self.client.get(f"/feedback/{fb.id}")
        html = res_detail.data.decode("utf-8")
        self.assertIn("UserTim", html)
        self.assertIn("Heel goed idee, dat zou ons veel tijd besparen!", html)

    def test_afsluiten_door_beheerder_en_blokkeren_reacties(self):
        """Test dat enkel beheerder kan afsluiten, en dat gesloten items geen reacties/stemmen meer accepteren."""
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.medewerker_user.id,
            type="foutje",
            onderwerp="Layout verspringt in Safari",
            beschrijving="Tekst staat over elkaars velden.",
            aangemaakt_op=datetime.now(timezone.utc)
        )
        db.session.add(fb)
        db.session.commit()

        # Medewerker mag NIET afsluiten
        self.login("tim@test.com", "password123")
        res = self.client.post(f"/feedback/{fb.id}/status", follow_redirects=True)
        self.assertIn("Enkel beheerders", res.data.decode("utf-8"))
        db.session.refresh(fb)
        self.assertFalse(fb.is_afgesloten)

        # Beheerder sluit af
        self.logout()
        self.login("admin@test.com", "password123")
        res = self.client.post(f"/feedback/{fb.id}/status", follow_redirects=True)
        self.assertIn("afgesloten", res.data.decode("utf-8"))
        db.session.refresh(fb)
        self.assertTrue(fb.is_afgesloten)
        self.assertIsNotNone(fb.afgesloten_op)
        self.assertEqual(fb.afgesloten_door_id, self.admin_user.id)

        # Probeer te stemmen op afgesloten item -> geweigerd
        self.logout()
        self.login("tim@test.com", "password123")
        res_stem = self.client.post(f"/feedback/{fb.id}/stem", data={"stem": "1"}, follow_redirects=True)
        self.assertIn("afgesloten", res_stem.data.decode("utf-8"))

        # Probeer te reageren op afgesloten item -> geweigerd
        res_reageer = self.client.post(f"/feedback/{fb.id}/reageer", data={"tekst": "Nieuwe reactie"}, follow_redirects=True)
        self.assertIn("afgesloten", res_reageer.data.decode("utf-8"))

    def test_lezer_rechten_beperkingen(self):
        """Test dat een gebruiker met rol 'lezer' enkel kan kijken en niets mag invoeren, stemmen of reageren."""
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.admin_user.id,
            type="voorstel",
            onderwerp="Suggestie voor dashboard",
            beschrijving="Meer grafieken.",
            aangemaakt_op=datetime.now(timezone.utc)
        )
        db.session.add(fb)
        db.session.commit()

        self.login("lezer@test.com", "password123")

        # Lezer kan de lijst en het item bekijken
        res_lijst = self.client.get("/feedback/")
        self.assertEqual(res_lijst.status_code, 200)
        res_detail = self.client.get(f"/feedback/{fb.id}")
        self.assertEqual(res_detail.status_code, 200)

        # Lezer mag geen nieuw item aanmaken
        res_nieuw = self.client.get("/feedback/nieuw", follow_redirects=True)
        self.assertIn("Als lezer heeft u enkel leesrechten", res_nieuw.data.decode("utf-8"))

        res_post = self.client.post("/feedback/nieuw", data={
            "type": "voorstel",
            "onderwerp": "Lezer poging",
            "beschrijving": "Test"
        }, follow_redirects=True)
        self.assertIn("Als lezer heeft u enkel leesrechten", res_post.data.decode("utf-8"))

        # Lezer mag niet stemmen
        res_stem = self.client.post(f"/feedback/{fb.id}/stem", data={"stem": "1"}, follow_redirects=True)
        self.assertIn("Als lezer heeft u enkel leesrechten", res_stem.data.decode("utf-8"))

        # Lezer mag niet reageren
        res_reageer = self.client.post(f"/feedback/{fb.id}/reageer", data={"tekst": "Poging reactie"}, follow_redirects=True)
        self.assertIn("Als lezer heeft u enkel leesrechten", res_reageer.data.decode("utf-8"))

    def test_screenshot_security_headers(self):
        """SEC-06: Verifieer dat screenshot endpoint strikte CSP en nosniff headers bevat."""
        self.login("tim@test.com", "password123")
        png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
        self.client.post("/feedback/nieuw", data={
            "type": "foutje",
            "onderwerp": "Beveiliging screenshot test",
            "beschrijving": "Test",
            "screenshot": (io.BytesIO(png_data), "veilig.png")
        }, follow_redirects=True)

        fb = FeedbackItem.query.filter_by(onderwerp="Beveiliging screenshot test").first()
        res = self.client.get(f"/feedback/{fb.id}/screenshot")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Content-Security-Policy'), "default-src 'none'; sandbox;")
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')

    def test_cross_tenant_feedback_isolation(self):
        """SEC-07: Verifieer dat gebruikers van een andere organisatie geen acties kunnen uitvoeren op feedback (IDOR-preventie)."""
        from models.organisatie import Organisatie
        org2 = Organisatie(naam="Tweede Organisatie", slug="tweede-org", actief=True)
        db.session.add(org2)
        db.session.commit()

        user_org2 = User(
            naam="UserOrg2",
            email="user2@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="beheerder",
            actief=True
        )
        db.session.add(user_org2)
        db.session.commit()

        uo2 = UserOrganisatie(user_id=user_org2.id, organisatie_id=org2.id, rol="beheerder", actief=True)
        db.session.add(uo2)
        db.session.commit()

        # Feedback in Organisatie 1
        fb_org1 = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=self.admin_user.id,
            type="voorstel",
            onderwerp="Geheim voorstel Org 1",
            beschrijving="Alleen voor Org 1",
            aangemaakt_op=datetime.now(timezone.utc)
        )
        db.session.add(fb_org1)
        db.session.commit()

        # Login als gebruiker van Organisatie 2
        self.login("user2@test.com", "password123")
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = org2.id

        # 1. Detail bekijken van Org 1 feedback -> 404
        res_detail = self.client.get(f"/feedback/{fb_org1.id}")
        self.assertEqual(res_detail.status_code, 404)

        # 2. Stemmen op Org 1 feedback -> 404
        res_stem = self.client.post(f"/feedback/{fb_org1.id}/stem", data={"stem": "1"})
        self.assertEqual(res_stem.status_code, 404)

        # 3. Reageren op Org 1 feedback -> 404
        res_reageer = self.client.post(f"/feedback/{fb_org1.id}/reageer", data={"tekst": "Inbreuk"})
        self.assertEqual(res_reageer.status_code, 404)

        # 4. Status afsluiten van Org 1 feedback (zelfs als beheerder van Org 2) -> 404
        res_status = self.client.post(f"/feedback/{fb_org1.id}/status")
        self.assertEqual(res_status.status_code, 404)
