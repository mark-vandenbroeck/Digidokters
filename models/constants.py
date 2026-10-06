"""Centrale constanten voor rollen, statussen, intervallen, permissies en types."""

# Gebruikersrollen (historisch/compatibiliteit)
ROLE_PLATFORMBEHEERDER = 'platformbeheerder'
ROLE_BEHEERDER = 'beheerder'
ROLE_MEDEWERKER = 'medewerker'
ROLE_LEZER = 'lezer'

ALLE_ROLLEN = (ROLE_PLATFORMBEHEERDER, ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER)
ORGANISATIE_ROLLEN = (ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER)

# Permissie Toegangsniveaus
ACCESS_NONE = 'geen'
ACCESS_READ = 'lezen'
ACCESS_WRITE = 'schrijven'

ACCESS_LEVELS = (ACCESS_NONE, ACCESS_READ, ACCESS_WRITE)
ACCESS_LEVEL_ORDER = {ACCESS_NONE: 0, ACCESS_READ: 1, ACCESS_WRITE: 2}

# Functionele Modules (Feature Keys)
FEATURE_REGISTRATIES = 'registraties'
FEATURE_AGENDA = 'agenda'
FEATURE_STATISTIEKEN = 'statistieken'
FEATURE_DOCUMENTEN = 'documenten'
FEATURE_EVALUATIES = 'evaluaties'
FEATURE_FEEDBACK = 'feedback'
FEATURE_STAMGEGEVENS = 'stamgegevens'
FEATURE_GEBRUIKERS = 'gebruikers'
FEATURE_IMPORT_EXPORT = 'import_export'

ALL_FEATURES = (
    FEATURE_REGISTRATIES,
    FEATURE_AGENDA,
    FEATURE_STATISTIEKEN,
    FEATURE_DOCUMENTEN,
    FEATURE_EVALUATIES,
    FEATURE_FEEDBACK,
    FEATURE_STAMGEGEVENS,
    FEATURE_GEBRUIKERS,
    FEATURE_IMPORT_EXPORT,
)

FEATURE_LABELS = {
    FEATURE_REGISTRATIES: 'Hulpvragen & Consultaties',
    FEATURE_AGENDA: 'Agenda & Planning',
    FEATURE_STATISTIEKEN: 'Statistieken & Rapporten',
    FEATURE_DOCUMENTEN: 'Kennisbank & Documenten',
    FEATURE_EVALUATIES: 'Evaluaties & Kwaliteitsmeting',
    FEATURE_FEEDBACK: 'Feedback & Verbeterpunten',
    FEATURE_STAMGEGEVENS: 'Stamgegevens & Beheertabellen',
    FEATURE_GEBRUIKERS: 'Gebruikers- & Groepsbeheer',
    FEATURE_IMPORT_EXPORT: 'Data Importeren & Exporteren',
}

FEATURE_DESCRIPTIONS = {
    FEATURE_REGISTRATIES: 'Registraties raadplegen (lezen) of toevoegen, bewerken en verwijderen (schrijven).',
    FEATURE_AGENDA: 'Sessies en planning inzien (lezen) of sessies inplannen, bewerken en digidokters toewijzen (schrijven).',
    FEATURE_STATISTIEKEN: 'Statistische rapporten en grafieken inzien (lezen).',
    FEATURE_DOCUMENTEN: 'Documenten en mappen inzien/downloaden (lezen) of uploaden en beheren (schrijven).',
    FEATURE_EVALUATIES: 'Evaluatieresultaten inzien (lezen) of formulieren configureren en reacties bewerken (schrijven).',
    FEATURE_FEEDBACK: 'Feedback en ideeën bekijken (lezen) of indienen, stemmen, reageren en statussen wijzigen (schrijven).',
    FEATURE_STAMGEGEVENS: 'Stamgegevens zoals locaties, toestellen en categorieën raadplegen (lezen) of beheren (schrijven).',
    FEATURE_GEBRUIKERS: 'Gebruikerslijsten inzien (lezen) of gebruikers toevoegen, groepen en rechten toewijzen (schrijven).',
    FEATURE_IMPORT_EXPORT: 'Gegevens exporteren naar Excel/CSV (lezen) of historische bestanden importeren (schrijven).',
}

# Standaard Systeemgroepen
DEFAULT_GROUP_LEZERS = 'lezers'
DEFAULT_GROUP_MEDEWERKERS = 'medewerkers'
DEFAULT_GROUP_BEHEERDERS = 'beheerders'
DEFAULT_GROUP_PLATFORMBEHEERDERS = 'platformbeheerders'

DEFAULT_GROUPS = (
    DEFAULT_GROUP_LEZERS,
    DEFAULT_GROUP_MEDEWERKERS,
    DEFAULT_GROUP_BEHEERDERS,
    DEFAULT_GROUP_PLATFORMBEHEERDERS,
)

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

