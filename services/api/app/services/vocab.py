"""Controlled vocabulary seeding.

The database stores countries, degree levels and fields of study in controlled
vocabularies. This module seeds them from the platform's own reference data so
that the corpus builder can attach a scholarship to a country without hitting a
foreign-key violation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# African countries in scope, plus the main study destinations.
COUNTRIES: dict[str, tuple[str, str]] = {
    "NGA": ("Nigeria", "africa"),
    "GHA": ("Ghana", "africa"),
    "KEN": ("Kenya", "africa"),
    "ZAF": ("South Africa", "africa"),
    "EGY": ("Egypt", "africa"),
    "ETH": ("Ethiopia", "africa"),
    "TZA": ("Tanzania", "africa"),
    "UGA": ("Uganda", "africa"),
    "RWA": ("Rwanda", "africa"),
    "ZMB": ("Zambia", "africa"),
    "ZWE": ("Zimbabwe", "africa"),
    "BWA": ("Botswana", "africa"),
    "NAM": ("Namibia", "africa"),
    "MOZ": ("Mozambique", "africa"),
    "AGO": ("Angola", "africa"),
    "SEN": ("Senegal", "africa"),
    "CMR": ("Cameroon", "africa"),
    "CIV": ("Cote d'Ivoire", "africa"),
    "MLI": ("Mali", "africa"),
    "BFA": ("Burkina Faso", "africa"),
    "BEN": ("Benin", "africa"),
    "TGO": ("Togo", "africa"),
    "LBR": ("Liberia", "africa"),
    "SLE": ("Sierra Leone", "africa"),
    "GIN": ("Guinea", "africa"),
    "GNB": ("Guinea-Bissau", "africa"),
    "SDN": ("Sudan", "africa"),
    "SSD": ("South Sudan", "africa"),
    "SOM": ("Somalia", "africa"),
    "DJI": ("Djibouti", "africa"),
    "SWZ": ("Eswatini", "africa"),
    "LSO": ("Lesotho", "africa"),
    "MWI": ("Malawi", "africa"),
    "GMB": ("Gambia", "africa"),
    "MUS": ("Mauritius", "africa"),
    "SYC": ("Seychelles", "africa"),
    "MDG": ("Madagascar", "africa"),
    "GBR": ("United Kingdom", "europe"),
    "DEU": ("Germany", "europe"),
    "FRA": ("France", "europe"),
    "IRL": ("Ireland", "europe"),
    "NLD": ("Netherlands", "europe"),
    "BEL": ("Belgium", "europe"),
    "SWE": ("Sweden", "europe"),
    "NOR": ("Norway", "europe"),
    "DNK": ("Denmark", "europe"),
    "FIN": ("Finland", "europe"),
    "ESP": ("Spain", "europe"),
    "ITA": ("Italy", "europe"),
    "PRT": ("Portugal", "europe"),
    "AUT": ("Austria", "europe"),
    "CHE": ("Switzerland", "europe"),
    "TUR": ("Turkiye", "europe"),
    "USA": ("United States", "north america"),
    "CAN": ("Canada", "north america"),
    "AUS": ("Australia", "oceania"),
    "CHN": ("China", "asia"),
    "JPN": ("Japan", "asia"),
    "IND": ("India", "asia"),
    "KOR": ("South Korea", "asia"),
    "SGP": ("Singapore", "asia"),
    "SAU": ("Saudi Arabia", "asia"),
    "ARE": ("United Arab Emirates", "asia"),
    "QAT": ("Qatar", "asia"),
    "ISR": ("Israel", "asia"),
}

DEGREE_LEVELS: dict[str, tuple[str, int]] = {
    "bachelors": ("Bachelor's degree", 1),
    "masters": ("Master's degree", 2),
    "mba": ("MBA", 3),
    "phd": ("Doctorate (PhD)", 4),
    "postdoc": ("Postdoctoral fellowship", 5),
    "research": ("Research programme", 6),
}

FIELDS: dict[str, tuple[str, str | None]] = {
    "ENG": ("Engineering and technology", None),
    "MED": ("Medicine and health", None),
    "BUS": ("Business and management", None),
    "EDU": ("Education", None),
    "LAW": ("Law", None),
    "SOC": ("Social sciences", None),
    "AGR": ("Agriculture", None),
    "SCI": ("Natural sciences", None),
    "ENV": ("Environment and climate", None),
    "DEV": ("Development studies", None),
    "HUM": ("Arts and humanities", None),
    "ART": ("Arts and creative industries", None),
}


def seed_vocabulary(session: Any) -> dict[str, int]:
    """Seed the controlled vocabularies. Idempotent."""
    from sqlalchemy import text

    counts = {"countries": 0, "degree_levels": 0, "fields_of_study": 0}

    for iso3, (name, region) in COUNTRIES.items():
        session.execute(
            text(
                """
                INSERT INTO countries (iso3, name, region, is_in_scope)
                VALUES (:iso3, :name, :region, :in_scope)
                ON CONFLICT (iso3) DO UPDATE SET name = EXCLUDED.name, region = EXCLUDED.region
                """
            ),
            {"iso3": iso3, "name": name, "region": region, "in_scope": region == "africa"},
        )
        counts["countries"] += 1

    for code, (name, ordinal) in DEGREE_LEVELS.items():
        session.execute(
            text(
                """
                INSERT INTO degree_levels (code, name, ordinal)
                VALUES (:code, :name, :ordinal)
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, ordinal = EXCLUDED.ordinal
                """
            ),
            {"code": code, "name": name, "ordinal": ordinal},
        )
        counts["degree_levels"] += 1

    for code, (name, parent) in FIELDS.items():
        session.execute(
            text(
                """
                INSERT INTO fields_of_study (code, name, parent_code, aliases)
                VALUES (:code, :name, :parent, '[]'::jsonb)
                ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
                """
            ),
            {"code": code, "name": name, "parent": parent},
        )
        counts["fields_of_study"] += 1

    return counts
