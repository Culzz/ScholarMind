"""Vocabulary normalisation: countries, degree levels, funding components, documents.

These maps turn the vocabulary used by official pages into the controlled
vocabularies stored in the database. A value that cannot be normalised is kept
as-is and flagged rather than being forced into a bucket.
"""

from __future__ import annotations

from typing import Any

# --- countries (African scope plus the main study destinations) -----------
COUNTRY_ALIASES: dict[str, str] = {
    "nigeria": "NGA",
    "nigerian": "NGA",
    "ghana": "GHA",
    "ghanaian": "GHA",
    "kenya": "KEN",
    "kenyan": "KEN",
    "south africa": "ZAF",
    "south african": "ZAF",
    "egypt": "EGY",
    "ethiopia": "ETH",
    "tanzania": "TZA",
    "uganda": "UGA",
    "rwanda": "RWA",
    "zambia": "ZMB",
    "zimbabwe": "ZWE",
    "botswana": "BWA",
    "namibia": "NAM",
    "mozambique": "MOZ",
    "angola": "AGO",
    "senegal": "SEN",
    "cameroon": "CMR",
    "ivory coast": "CIV",
    "cote d'ivoire": "CIV",
    "mali": "MLI",
    "burkina faso": "BFA",
    "benin": "BEN",
    "togo": "TGO",
    "ghana ": "GHA",
    "liberia": "LBR",
    "sierra leone": "SLE",
    "guinea": "GIN",
    "guinea-bissau": "GNB",
    "sudan": "SDN",
    "south sudan": "SSD",
    "somalia": "SOM",
    "djibouti": "DJI",
    "eswatini": "SWZ",
    "lesotho": "LSO",
    "malawi": "MWI",
    "gambia": "GMB",
    "mauritius": "MUS",
    "seychelles": "SYC",
    "madagascar": "MDG",
    "united kingdom": "GBR",
    "uk": "GBR",
    "britain": "GBR",
    "england": "GBR",
    "scotland": "GBR",
    "united states": "USA",
    "usa": "USA",
    "u.s.": "USA",
    "america": "USA",
    "germany": "DEU",
    "france": "FRA",
    "canada": "CAN",
    "australia": "AUS",
    "ireland": "IRL",
    "netherlands": "NLD",
    "china": "CHN",
    "japan": "JPN",
    "india": "IND",
    "belgium": "BEL",
    "sweden": "SWE",
    "norway": "NOR",
    "denmark": "DNK",
    "finland": "FIN",
    "spain": "ESP",
    "italy": "ITA",
    "portugal": "PRT",
    "austria": "AUT",
    "switzerland": "CHE",
    "turkey": "TUR",
    "türkiye": "TUR",
    "south korea": "KOR",
    "korea": "KOR",
    "singapore": "SGP",
    "saudi arabia": "SAU",
    "united arab emirates": "ARE",
    "qatar": "QAT",
    "israel": "ISR",
    "italy": "ITA",
}

DEGREE_LEVEL_ALIASES: dict[str, str] = {
    "undergraduate": "bachelors",
    "bachelor": "bachelors",
    "bachelors": "bachelors",
    "b.sc": "bachelors",
    "bsc": "bachelors",
    "b.a": "bachelors",
    "ba": "bachelors",
    "postgraduate": "masters",
    "post graduate": "masters",
    "master": "masters",
    "masters": "masters",
    "msc": "masters",
    "m.sc": "masters",
    "ma": "masters",
    "m.a": "masters",
    "mba": "mba",
    "phd": "phd",
    "doctorate": "phd",
    "doctoral": "phd",
    "postdoctoral": "postdoc",
    "post doc": "postdoc",
    "research": "research",
}

FUNDING_COMPONENT_ALIASES: dict[str, str] = {
    "tuition": "tuition",
    "tuition fees": "tuition",
    "tuition fee": "tuition",
    "school fees": "tuition",
    "registration": "tuition",
    "stipend": "stipend",
    "living allowance": "stipend",
    "maintenance allowance": "stipend",
    "allowance": "stipend",
    "travel": "travel",
    "airfare": "travel",
    "air fare": "travel",
    "flight": "travel",
    "transport": "travel",
    "accommodation": "accommodation",
    "housing": "accommodation",
    "hostel": "accommodation",
    "lodging": "accommodation",
    "insurance": "insurance",
    "medical insurance": "insurance",
    "health insurance": "insurance",
    "equipment": "equipment",
    "laptop": "equipment",
    "books": "equipment",
    "research": "research",
    "research support": "research",
    "conference": "research",
}

DOCUMENT_TYPE_ALIASES: dict[str, str] = {
    "passport": "passport",
    "national passport": "passport",
    "international passport": "passport",
    "transcript": "transcript",
    "academic transcript": "transcript",
    "statement of results": "transcript",
    "certificate": "certificate",
    "nySC": "nysc",
    "nysc": "nysc",
    "national youth service corps": "nysc",
    "statement of purpose": "sop",
    "sop": "sop",
    "personal statement": "sop",
    "statement of motivation": "sop",
    "motivation letter": "sop",
    "cover letter": "sop",
    "curriculum vitae": "cv",
    "cv": "cv",
    "resume": "cv",
    "letter of reference": "lor",
    "reference letter": "lor",
    "letters of reference": "lor",
    "lor": "lor",
    "recommendation letter": "lor",
    "research proposal": "research_proposal",
    "proposal": "research_proposal",
    "proof of registration": "proof_of_registration",
    "proof of admission": "proof_of_admission",
    "ielts": "ielts",
    "toefl": "toefl",
    "english language test": "ielts",
    "english test": "ielts",
    "birth certificate": "birth_certificate",
    "national id": "national_id",
    "waiver": "waiver",
    "credential evaluation": "credential_evaluation",
    "credential evaluation report": "credential_evaluation",
    "apostille": "apostille",
}


# More specific document types are matched before generic ones: an "NYSC
# certificate" is an NYSC document, not a generic certificate.
DOCUMENT_TYPE_PRIORITY = (
    "nysc",
    "national youth service corps",
    "credential evaluation",
    "research proposal",
    "proof of registration",
    "proof of admission",
    "letter of reference",
    "reference letter",
    "recommendation letter",
    "letters of reference",
    "statement of purpose",
    "statement of motivation",
    "motivation letter",
    "personal statement",
    "cover letter",
    "academic transcript",
    "statement of results",
    "international passport",
    "national passport",
    "national id",
    "birth certificate",
    "english language test",
    "english test",
    "curriculum vitae",
    "passport",
    "transcript",
    "certificate",
    "waiver",
    "apostille",
    "ielts",
    "toefl",
    "sop",
    "lor",
    "cv",
)


def normalise_country(value: str | None) -> str | None:
    """Map a country name to its ISO alpha-3 code."""
    if not value:
        return None
    key = value.strip().lower()
    if len(key) == 3 and key.isalpha() and key.isupper():
        return key
    return COUNTRY_ALIASES.get(key)


def normalise_degree_level(value: str | None) -> str | None:
    """Map a study level phrase to the controlled vocabulary."""
    if not value:
        return None
    key = value.strip().lower()
    if key in DEGREE_LEVEL_ALIASES:
        mapped = DEGREE_LEVEL_ALIASES[key]
        return None if mapped.endswith("_placeholder") else mapped
    for alias, mapped in DEGREE_LEVEL_ALIASES.items():
        if mapped.endswith("_placeholder"):
            continue
        if alias in key:
            return mapped
    return None


def normalise_funding_component(value: str | None) -> str | None:
    """Map a funding phrase to a controlled component."""
    if not value:
        return None
    key = value.strip().lower()
    if key in FUNDING_COMPONENT_ALIASES:
        return FUNDING_COMPONENT_ALIASES[key]
    for alias in sorted(FUNDING_COMPONENT_ALIASES, key=len, reverse=True):
        if alias in key:
            return FUNDING_COMPONENT_ALIASES[alias]
    return None


def normalise_document_type(value: str | None) -> str | None:
    """Map a document phrase to a controlled document type."""
    if not value:
        return None
    key = value.strip().lower()
    if key in DOCUMENT_TYPE_ALIASES:
        return DOCUMENT_TYPE_ALIASES[key]
    for alias in DOCUMENT_TYPE_PRIORITY:
        if alias in key:
            return DOCUMENT_TYPE_ALIASES[alias]
    return None


def normalise_waiver_kind(value: str | None) -> str | None:
    """Map a waiver phrase to a controlled waiver kind."""
    if not value:
        return None
    key = value.strip().lower()
    if "english medium" in key or "medium of instruction" in key:
        return "english_medium_degree"
    if "prior english" in key or "taught in english" in key:
        return "prior_english_medium_study"
    if "exempt" in key or "waiv" in key:
        return "accepted_exemption"
    return None


def normalise_provider_type(value: str | None) -> str:
    """Map a provider description to a controlled provider type."""
    if not value:
        return "other"
    key = value.strip().lower()
    if any(token in key for token in ("government", "ministry", "federation", "national")):
        return "government"
    if "universit" in key or "institute" in key or "polytechnic" in key:
        return "university"
    if "foundation" in key:
        return "foundation"
    if "ngo" in key or "charity" in key:
        return "ngo"
    if any(token in key for token in ("company", "corporate", "bank", "oil")):
        return "corporate"
    if any(token in key for token in ("united nations", "un ", "multilateral", "organisation")):
        return "multilateral"
    return "other"


def normalise_field_of_study(value: str | None) -> str | None:
    """Map a discipline phrase to a coarse internal field code."""
    if not value:
        return None
    key = value.strip().lower()
    table = {
        "engineering": "ENG",
        "computer": "ENG",
        "information technology": "ENG",
        "software": "ENG",
        "data science": "ENG",
        "medicine": "MED",
        "health": "MED",
        "public health": "MED",
        "nursing": "MED",
        "pharmacy": "MED",
        "business": "BUS",
        "management": "BUS",
        "economics": "BUS",
        "accounting": "BUS",
        "finance": "BUS",
        "education": "EDU",
        "law": "LAW",
        "social science": "SOC",
        "sociology": "SOC",
        "political science": "SOC",
        "anthropology": "SOC",
        "psychology": "SOC",
        "agriculture": "AGR",
        "science": "SCI",
        "physics": "SCI",
        "chemistry": "SCI",
        "biology": "SCI",
        "mathematics": "SCI",
        "environment": "ENV",
        "climate": "ENV",
        "development studies": "DEV",
        "gender studies": "SOC",
        "humanities": "HUM",
        "history": "HUM",
        "languages": "HUM",
        "theology": "HUM",
        "architecture": "ENG",
        "art": "ART",
        "music": "ART",
    }
    for alias, code in table.items():
        if alias in key:
            return code
    return None


def normalise_field_of_study_list(values: list[str] | None) -> list[str]:
    """Normalise a list of disciplines, dropping unrecognised entries."""
    if not values:
        return []
    codes: list[str] = []
    for value in values:
        code = normalise_field_of_study(value)
        if code and code not in codes:
            codes.append(code)
    return codes


def describe_unmapped(values: list[str] | None) -> dict[str, Any]:
    """Report which values could not be normalised, for the review queue."""
    if not values:
        return {"unmapped": []}
    unmapped: list[str] = []
    for value in values:
        if not normalise_country(value) and not normalise_degree_level(value):
            unmapped.append(value)
    return {"unmapped": unmapped}
