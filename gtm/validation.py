"""Input cleaning and validation shared by every write. Raises ValidationError with ALL problems at once (good for forms)."""
import re
from datetime import date, datetime
from urllib.parse import urlparse


class ValidationError(ValueError):
    def __init__(self, messages):
        self.messages = [messages] if isinstance(messages, str) else list(messages)
        super().__init__("; ".join(self.messages))


_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+$")
_LEGAL = {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "gmbh", "plc", "sa", "ag", "bv"}


def text(value, maxlen=500):
    """Trimmed single-spaced text; control characters removed."""
    s = "" if value is None else str(value)
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()[:maxlen]


def name_key(name):
    """Deduplication key for company names: case, punctuation and legal suffixes ignored."""
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", text(name).lower()).split() if w not in _LEGAL]
    return " ".join(words)


def email_key(email):
    return text(email).lower() or None


def valid_email(email):
    return bool(_EMAIL.match(text(email)))


def linkedin_key(url):
    """Canonical LinkedIn profile path (host, scheme, query and trailing slash ignored), or None if empty/not LinkedIn."""
    u = text(url).lower()
    if not u:
        return None
    parsed = urlparse(u if "//" in u else "https://" + u)
    host = parsed.netloc.removeprefix("www.")
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return None
    path = parsed.path.rstrip("/")
    return f"linkedin.com{path}" if path and path != "/" else None


def to_date(value, field="date"):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(text(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{field} must be a date (YYYY-MM-DD)") from None


def to_number(value, field, minimum=0.0, maximum=None):
    try:
        x = float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        raise ValidationError(f"{field} must be a number") from None
    if x != x or x in (float("inf"), float("-inf")):
        raise ValidationError(f"{field} must be a finite number")
    if x < minimum or (maximum is not None and x > maximum):
        raise ValidationError(f"{field} must be between {minimum:g} and {maximum:g}" if maximum is not None else f"{field} must be at least {minimum:g}")
    return x


def one_of(value, allowed, field):
    v = text(value)
    if v not in allowed:
        raise ValidationError(f"{field} must be one of: {', '.join(allowed)}")
    return v


def collect(checks):
    """Run several (callable) checks and raise one ValidationError with every message."""
    problems, results = [], []
    for check in checks:
        try:
            results.append(check())
        except ValidationError as exc:
            problems.extend(exc.messages)
            results.append(None)
    if problems:
        raise ValidationError(problems)
    return results
