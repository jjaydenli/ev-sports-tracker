"""Cross-platform master board normalization."""

from parsers.betr_parser import parse_betr_prop, parse_betr_props
from parsers.dk_parser import parse_dk_prop, parse_dk_props

__all__ = [
    "parse_betr_prop",
    "parse_betr_props",
    "parse_dk_prop",
    "parse_dk_props",
]
