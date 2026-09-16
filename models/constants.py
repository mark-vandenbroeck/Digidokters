"""Centrale constanten voor rollen, statussen, intervallen en types."""

# Gebruikersrollen
ROLE_PLATFORMBEHEERDER = 'platformbeheerder'
ROLE_BEHEERDER = 'beheerder'
ROLE_MEDEWERKER = 'medewerker'
ROLE_LEZER = 'lezer'

ALLE_ROLLEN = (ROLE_PLATFORMBEHEERDER, ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER)
ORGANISATIE_ROLLEN = (ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER)

# Evaluatie vraagtypes
QUESTION_TYPE_MC = 'multiple_choice'
QUESTION_TYPE_OPEN = 'open_tekst'

# Agenda intervallen
INTERVAL_DAGELIJKS = 'dagelijks'
INTERVAL_WEKELIJKS = 'wekelijks'
INTERVAL_MAANDELIJKS = 'maandelijks'

# Audit operaties
AUDIT_CREATE = 'CREATE'
AUDIT_UPDATE = 'UPDATE'
AUDIT_DELETE = 'DELETE'
