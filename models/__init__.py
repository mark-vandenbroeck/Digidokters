"""Models package – importeer alle modellen hier zodat Flask-Migrate ze detecteert."""
from .user import User
from .digidokter import Digidokter
from .age_category import AgeCategory
from .device import Device
from .registration import Registration
from .organisatie import Organisatie, UserOrganisatie

__all__ = ['User', 'Digidokter', 'AgeCategory', 'Device', 'Registration', 'Organisatie', 'UserOrganisatie']
