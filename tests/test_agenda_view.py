import datetime
from tests.base import BaseTestCase
from models.agenda import AgendaItem
from models.activity_type import ActivityType
from models.location import Location
from extensions import db

class TestAgendaView(BaseTestCase):
    def test_weekdag_filter(self):
        filter_fn = self.app.jinja_env.filters.get('weekdag')
        self.assertIsNotNone(filter_fn)
        
        # Test Monday through Sunday
        # 2026-09-07 is a Monday, 2026-09-13 is a Sunday
        expected = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag']
        for day_offset, expected_day in enumerate(expected):
            d = datetime.date(2026, 9, 7 + day_offset)
            self.assertEqual(filter_fn(d), expected_day)

        # None / invalid should return empty string gracefully
        self.assertEqual(filter_fn(None), '')

    def test_agenda_lijst_shows_weekday(self):
        self.login("UserAdmin", "password123")
        
        # Add an agenda item on a known date (e.g. 2026-10-15 is Thursday -> donderdag)
        act_type = ActivityType(naam="Ondersteuning", actief=True, organisatie_id=1)
        loc = Location(naam="Bib Test", actief=True, organisatie_id=1)
        db.session.add_all([act_type, loc])
        db.session.commit()

        item = AgendaItem(
            datum=datetime.date(2026, 10, 15),
            uur_van="10:00",
            uur_tot="12:00",
            type_id=act_type.id,
            locatie_id=loc.id,
            organisatie_id=1
        )
        db.session.add(item)
        db.session.commit()

        response = self.client.get('/agenda?toon_verleden=on')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('15/10/2026', html)
        self.assertIn('donderdag', html)
