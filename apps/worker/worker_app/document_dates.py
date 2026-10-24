import re
from datetime import date


_DATE = r"(?P<year>(?:19|20)\d{2})\s*(?:年|[-/.])\s*(?P<month>0?[1-9]|1[0-2])\s*(?:月|[-/.])\s*(?P<day>0?[1-9]|[12]\d|3[01])\s*日?"
_PUBLICATION_LABEL = re.compile(
    rf"(?:发布日期|发布日|印发日期|印发日|颁布日期|公布日期)\s*[:：]?\s*{_DATE}"
)
_EFFECTIVE_LABEL = re.compile(
    rf"(?:生效日期|生效日|施行日期|施行日|实施日期|实施日|执行日期|执行日)\s*[:：]?\s*{_DATE}"
)
_EFFECTIVE_PHRASE = re.compile(rf"自\s*{_DATE}\s*日起\s*(?:正式)?(?:生效|施行|实施|执行)")


def _first_date(pattern: re.Pattern, text: str) -> date | None:
    for match in pattern.finditer(text[:100_000]):
        try:
            return date(int(match["year"]), int(match["month"]), int(match["day"]))
        except ValueError:
            continue
    return None


def extract_document_dates(text: str) -> tuple[date | None, date | None]:
    """Extract explicitly labeled publication/effective dates; never infer from upload time."""
    publication_date = _first_date(_PUBLICATION_LABEL, text)
    effective_date = _first_date(_EFFECTIVE_LABEL, text) or _first_date(_EFFECTIVE_PHRASE, text)
    return publication_date, effective_date
