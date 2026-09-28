#!/usr/bin/env python3
"""
switch_schema.py

Handige CLI-tool om snel te wisselen tussen het 'public' schema (artificiële testdata)
en het 'productie' schema (echte productiedata uit de backup) in je lokale .env bestand.

Gebruik:
    python scripts/switch_schema.py              # Toont het huidige actieve schema
    python scripts/switch_schema.py public       # Schakelt over naar het public schema
    python scripts/switch_schema.py productie    # Schakelt over naar het productie schema
    python scripts/switch_schema.py toggle       # Wisselt tussen public en productie
"""

import sys
import re
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

def get_current_schema(env_content: str) -> str:
    match = re.search(r"^\s*DB_SCHEMA\s*=\s*(\w+)", env_content, re.MULTILINE)
    if match:
        return match.group(1)
    return "public"

def set_schema(target_schema: str):
    target_schema = target_schema.strip().lower()
    if target_schema not in ["public", "productie"]:
        print(f"❌ Ongeldig schema '{target_schema}'. Kies 'public' of 'productie'.")
        sys.exit(1)

    if not ENV_PATH.exists():
        print(f"❌ .env bestand niet gevonden op {ENV_PATH}")
        sys.exit(1)

    with open(ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    current = get_current_schema(content)

    if re.search(r"^\s*DB_SCHEMA\s*=", content, re.MULTILINE):
        # Vervang bestaande DB_SCHEMA regel
        new_content = re.sub(
            r"^\s*DB_SCHEMA\s*=.*$",
            f"DB_SCHEMA={target_schema}",
            content,
            flags=re.MULTILINE,
        )
    else:
        # Voeg DB_SCHEMA toe
        new_content = content.rstrip() + f"\n\n# PostgreSQL schema keuze (public of productie)\nDB_SCHEMA={target_schema}\n"

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ Schema gewijzigd: {current} ➜  {target_schema}")
    print(f"   Herstart je Flask server om de wijziging toe te passen.")

def main():
    if not ENV_PATH.exists():
        print(f"❌ .env bestand niet gevonden op {ENV_PATH}")
        sys.exit(1)

    with open(ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    current = get_current_schema(content)

    if len(sys.argv) == 1:
        print(f"Huidig actief PostgreSQL schema: \033[1m{current}\033[0m")
        print("\nGebruik:")
        print("  python scripts/switch_schema.py public     (voor testdata)")
        print("  python scripts/switch_schema.py productie  (voor productiedata)")
        print("  python scripts/switch_schema.py toggle     (snel wisselen)")
        return

    arg = sys.argv[1].strip().lower()
    if arg == "toggle":
        target = "productie" if current == "public" else "public"
        set_schema(target)
    elif arg in ["public", "productie"]:
        set_schema(arg)
    else:
        print(f"❌ Onbekende optie '{arg}'. Gebruik 'public', 'productie' of 'toggle'.")
        sys.exit(1)

if __name__ == "__main__":
    main()
