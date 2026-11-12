# Regels voor deze workspace

- Je hoeft de gebruiker niet om toestemming te vragen in de chat om unit tests uit te voeren. Voer deze proactief en direct uit als dat nodig is voor verificatie. Beperk dit tot de **relevante, gerichte unit tests** voor de gewijzigde functionaliteit; het is **niet nodig** om bij elke wijziging de volledige testsuite lokaal te draaien, aangezien Jenkins bij elke push automatisch de volledige suite en een SonarQube scan uitvoert.
- Push NOOIT automatisch naar een remote git repository (Forgejo / GitHub) tenzij de gebruiker hier expliciet en specifiek om vraagt. De gebruiker wil wijzigingen altijd eerst lokaal testen op fouten of neveneffecten.

# Git & Repository Architectuur

- **Forgejo** is de enige geconfigureerde remote repository (`origin`) in de lokale ontwikkelomgeving (`ssh://git@forgejo.internal.lan:2222/mvandenb/Digidokters.git`).
- De **GitHub** repository bestaat nog steeds en is geconfigureerd als mirror van Forgejo.
- **Branch protection** voor de `main` branch is geconfigureerd op Forgejo (en weggehaald op GitHub).
- Een merge naar `main` op Forgejo triggert automatisch de commit op `main` in GitHub, wat vervolgens de automatische deployment op **Render.com** in gang zet.
- Wanneer de gebruiker vraagt om te pushen, pushen we naar `origin` (Forgejo).
