"""Vocabulary of stable fact-keys the bot recognises per domain.

Each domain exposes a list of keys the reflect-node prompt enumerates so
extraction stays bounded and the (user, domain, key) triples converge rather
than fan out into free-form strings.

Add new keys here first, then point the reflect-node prompt at this module.
Remove a key here and old rows become unreadable by name; orphan them via a
migration or let the next upsert overwrite.
"""

from __future__ import annotations

from typing import Final

# Each entry: human-readable name + JSON shape (informational — values are
# JSONB and not enforced at the DB level).
LEGAL_KEYS: Final[tuple[str, ...]] = (
    "property_assets",
    "marital_status",
    "dependents",
    "citizenship",
    "state_of_residence",
    "ongoing_legal_cases",
    "will_or_testament_status",
)

healthcare_KEYS: Final[tuple[str, ...]] = (
    "chronic_conditions",
    "current_medications",
    "known_allergies",
    "blood_type",
    "pregnancy_status",
    "smoking_status",
    "alcohol_use",
    "primary_physician",
    "insurance_provider",
)

FINANCIAL_KEYS: Final[tuple[str, ...]] = (
    "annual_income_bracket",
    "tax_bracket",
    "employment_status",
    "existing_loans",
    "monthly_expenses_bracket",
    "dependents_financial",
    "investment_portfolio",
    "insurance_policies",
)


def keys_for_domain(domain: str) -> tuple[str, ...]:
    """Return the recognised key list for a domain. Empty tuple for unknown."""
    if domain == "legal":
        return LEGAL_KEYS
    if domain == "healthcare":
        return healthcare_KEYS
    if domain == "financial":
        return FINANCIAL_KEYS
    return ()


__all__ = [
    "LEGAL_KEYS",
    "healthcare_KEYS",
    "FINANCIAL_KEYS",
    "keys_for_domain",
]