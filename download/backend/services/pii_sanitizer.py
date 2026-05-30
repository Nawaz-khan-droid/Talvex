"""
TALVEX PII Sanitization Module
Detects, scrubs, and rehydrates Personally Identifiable Information (PII)
from text payloads before they reach LLM endpoints or external services.

Supported PII types (Layer 1 — Regex):
  - Email addresses
  - Phone numbers (US, international formats)
  - Social Security Numbers (SSN)
  - Dates of birth
  - Street / mailing addresses
  - LinkedIn profile URLs
  - GitHub profile URLs
  - Full names (heuristic-based detection)
  - Portfolio / personal website URLs
  - Company / employer IDs
  - Government IDs (non-SSN: passport, driver license, tax ID)
  - University / student IDs
  - GPS coordinates

Supported PII types (Layer 2 — spaCy NER):
  - PERSON entities (names not caught by heuristic)
  - ORG entities (company/organization names)

All scrubbed values are replaced with semantic placeholders,
e.g. [EMAIL_ADDRESS_1], making round-trip rehydration reliable.

PII vault stores encrypted mappings in **Redis** with configurable TTL
(default 1 hour).  Falls back to in-memory storage if Redis is
unavailable (local dev only — not safe for multi-worker production).
"""

import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ===================================================================
# Redis + Fernet encryption imports (graceful degradation)
# ===================================================================

_REDIS_AVAILABLE = False
_FERNET_AVAILABLE = False
_SPACY_AVAILABLE = False

try:
    import redis
    _REDIS_AVAILABLE = True
except ImportError:
    logger.warning("redis package not installed — PII vault will use in-memory fallback (unsafe for multi-worker).")

try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    logger.warning("cryptography package not installed — PII vault data will be stored unencrypted.")

try:
    import spacy
    _nlp = spacy.load("en_core_web_sm")
    _SPACY_AVAILABLE = True
    logger.info("spaCy NER loaded (en_core_web_sm) — NER Layer 2 active.")
except ImportError:
    _nlp = None
    logger.warning("spacy not installed — NER Layer 2 disabled. Install spacy and run: python -m spacy download en_core_web_sm")
except OSError:
    _nlp = None
    logger.warning("en_core_web_sm model not found — NER Layer 2 disabled. Run: python -m spacy download en_core_web_sm")


# ===================================================================
# Redis-backed PII Vault with Fernet encryption + TTL
# ===================================================================

class PIIVault:
    """PII vault backed by **Redis** with Fernet encryption.

    Why Redis (not in-memory)?
    ─────────────────────────
    FastAPI in production runs via Uvicorn with **multiple worker
    processes** (``--workers 4``).  An in-memory Python dict lives
    inside a single process.  If Worker A scrubs a resume and the
    rehydration request lands on Worker B, the vault is NULL and the
    resume is permanently broken.  Redis is external to the workers —
    every process shares the same vault.

    Encryption:
    ───────────
    The PII mapping dict is serialized to JSON, then encrypted with a
    Fernet symmetric key before being stored in Redis.  The key is
    derived from the ``PII_VAULT_ENCRYPTION_KEY`` environment variable
    (or generated once at module load and persisted for the lifetime
    of the process).

    TTL:
    ────
    Entries auto-expire via Redis ``SETEX`` (default 3600 seconds).
    """

    _DEFAULT_TTL = 3600  # 1 hour in seconds
    _REDIS_KEY_PREFIX = "talvex:pii:vault:"
    _FERNET_KEY_FILE = ".pii_vault_key"

    def __init__(self, ttl: int | None = None) -> None:
        self._ttl = ttl or self._DEFAULT_TTL
        self._redis: redis.Redis | None = None
        self._fernet: Fernet | None = None
        self._using_redis = False

        # --- Initialise Redis connection ---
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        if _REDIS_AVAILABLE:
            try:
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()  # verify connectivity
                self._using_redis = True
                logger.info("PIIVault connected to Redis at %s", redis_url)
            except Exception as exc:
                logger.warning(
                    "PIIVault: Redis connection failed (%s) — falling back to in-memory vault. "
                    "This is NOT safe for multi-worker production deployments.",
                    exc,
                )
                self._redis = None
        else:
            logger.warning("PIIVault: Redis not available — using in-memory fallback.")

        # --- Initialise Fernet encryption ---
        if _FERNET_AVAILABLE:
            key = self._get_or_create_encryption_key()
            self._fernet = Fernet(key)
        else:
            self._fernet = None
            logger.warning("PIIVault: Fernet not available — vault data stored UNENCRYPTED.")

        # --- In-memory fallback (thread-safe) ---
        self._lock = threading.Lock()
        self._memory: dict[str, dict[str, str]] = OrderedDict()
        self._memory_expires: dict[str, float] = {}

    # ----------------------------------------------------------
    # Encryption key management
    # ----------------------------------------------------------

    @staticmethod
    def _get_or_create_encryption_key() -> bytes:
        """Load or create a persistent Fernet key for this deployment.

        Strategy:
        1. Check ``PII_VAULT_ENCRYPTION_KEY`` env var (base64-encoded Fernet key).
        2. Check ``.pii_vault_key`` file in the working directory.
        3. Generate a new key and write to ``.pii_vault_key``.
        """
        # 1. Environment variable
        env_key = os.environ.get("PII_VAULT_ENCRYPTION_KEY", "")
        if env_key:
            try:
                Fernet(env_key.encode())  # validate it's a real Fernet key
                return env_key.encode()
            except Exception:
                logger.warning("PII_VAULT_ENCRYPTION_KEY is invalid — generating new key.")

        # 2. File-based key
        key_path = os.path.join(os.getcwd(), PIIVault._FERNET_KEY_FILE)
        if os.path.exists(key_path):
            try:
                with open(key_path, "rb") as f:
                    key = f.read()
                Fernet(key)  # validate
                return key
            except Exception:
                logger.warning("Existing .pii_vault_key file is corrupt — regenerating.")

        # 3. Generate new key
        key = Fernet.generate_key()
        try:
            with open(key_path, "wb") as f:
                f.write(key)
            # Restrict file permissions to owner-only
            os.chmod(key_path, 0o600)
            logger.info("Generated new PII vault encryption key at %s", key_path)
        except OSError as exc:
            logger.warning("Could not persist encryption key to %s: %s. Key will be ephemeral.", key_path, exc)
        return key

    # ----------------------------------------------------------
    # Public API (identical interface as before)
    # ----------------------------------------------------------

    def store(
        self,
        session_id: str,
        mapping: dict[str, str],
        ttl: int | None = None,
    ) -> None:
        """Store a PII mapping under *session_id* with TTL."""
        effective_ttl = ttl or self._ttl

        if self._using_redis and self._redis is not None:
            self._store_redis(session_id, mapping, effective_ttl)
        else:
            self._store_memory(session_id, mapping, effective_ttl)

    def retrieve(self, session_id: str) -> dict[str, str]:
        """Return the PII mapping for *session_id*, excluding expired entries."""
        if self._using_redis and self._redis is not None:
            return self._retrieve_redis(session_id)
        return self._retrieve_memory(session_id)

    def delete_session(self, session_id: str) -> int:
        """Remove a session and return the number of entries deleted."""
        if self._using_redis and self._redis is not None:
            return self._delete_redis(session_id)
        return self._delete_memory(session_id)

    def clear_expired(self) -> int:
        """Clear expired entries.  For Redis, TTL is handled natively.
        For in-memory fallback, manually evict stale sessions."""
        if self._using_redis:
            return 0  # Redis handles TTL natively via EXPIRE
        return self._clear_expired_memory()

    @property
    def session_count(self) -> int:
        if self._using_redis and self._redis is not None:
            try:
                keys = self._redis.keys(f"{self._REDIS_KEY_PREFIX}*")
                return len(keys)
            except Exception:
                return 0
        with self._lock:
            return len(self._memory)

    # ----------------------------------------------------------
    # Redis-backed storage
    # ----------------------------------------------------------

    def _store_redis(self, session_id: str, mapping: dict[str, str], ttl: int) -> None:
        """Serialize, encrypt, and store in Redis with SETEX."""
        redis_key = f"{self._REDIS_KEY_PREFIX}{session_id}"
        payload = json.dumps(mapping, ensure_ascii=False)

        if self._fernet is not None:
            try:
                payload = self._fernet.encrypt(payload.encode()).decode()
            except Exception as exc:
                logger.error("PIIVault: Fernet encryption failed — storing unencrypted: %s", exc)

        try:
            self._redis.setex(redis_key, ttl, payload)
        except Exception as exc:
            logger.error("PIIVault: Redis SETEX failed — falling back to memory: %s", exc)
            self._store_memory(session_id, mapping, ttl)

    def _retrieve_redis(self, session_id: str) -> dict[str, str]:
        """Fetch, decrypt, and deserialize from Redis."""
        redis_key = f"{self._REDIS_KEY_PREFIX}{session_id}"

        try:
            payload = self._redis.get(redis_key)
        except Exception as exc:
            logger.error("PIIVault: Redis GET failed: %s", exc)
            return self._retrieve_memory(session_id)

        if payload is None:
            return {}

        if self._fernet is not None:
            try:
                payload = self._fernet.decrypt(payload.encode()).decode()
            except Exception as exc:
                logger.error("PIIVault: Fernet decryption failed: %s", exc)
                return {}

        try:
            mapping = json.loads(payload)
            if isinstance(mapping, dict):
                return mapping
        except json.JSONDecodeError:
            logger.error("PIIVault: Failed to deserialize vault payload for session %s", session_id)

        return {}

    def _delete_redis(self, session_id: str) -> int:
        redis_key = f"{self._REDIS_KEY_PREFIX}{session_id}"
        try:
            result = self._redis.delete(redis_key)
            return result or 0
        except Exception:
            return 0

    # ----------------------------------------------------------
    # In-memory fallback (identical to the old implementation)
    # ----------------------------------------------------------

    def _store_memory(self, session_id: str, mapping: dict[str, str], ttl: int) -> None:
        expires_at = time.monotonic() + ttl
        with self._lock:
            self._memory[session_id] = mapping
            self._memory_expires[session_id] = expires_at

    def _retrieve_memory(self, session_id: str) -> dict[str, str]:
        with self._lock:
            if session_id not in self._memory:
                return {}
            if time.monotonic() > self._memory_expires.get(session_id, 0):
                del self._memory[session_id]
                del self._memory_expires[session_id]
                return {}
            return dict(self._memory[session_id])

    def _delete_memory(self, session_id: str) -> int:
        with self._lock:
            if session_id in self._memory:
                count = len(self._memory[session_id])
                del self._memory[session_id]
                del self._memory_expires[session_id]
                return count
            return 0

    def _clear_expired_memory(self) -> int:
        removed = 0
        with self._lock:
            now = time.monotonic()
            stale = [
                sid for sid, exp in self._memory_expires.items()
                if now > exp
            ]
            for sid in stale:
                removed += len(self._memory[sid])
                del self._memory[sid]
                del self._memory_expires[sid]
        return removed


# Module-level vault singleton
pii_vault = PIIVault()


# ============================================================
# PII Data Classes
# ============================================================

@dataclass
class PIIEntity:
    """Represents a single detected PII item."""

    pii_type: str
    value: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "type": self.pii_type,
            "value": self.value,
            "start": self.start,
            "end": self.end,
        }


# ============================================================
# Regex Patterns
# ============================================================

# Email: standard RFC-5322-ish pattern (practical subset)
RE_EMAIL = re.compile(
    r"(?:[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,})"
)

# Phone numbers — explicit format patterns to avoid false positives on years.
# Matches: +CC NNN NNNNN, (NNN) NNN-NNNN, 1-NNN-NNN-NNNN, NNNNNNN+ consecutive.
# Does NOT match bare 4-digit years like 2015 or 2023.
RE_PHONE = re.compile(
    r"(?:\+\d{1,3}[\s.-]\d{1,5}[\s.-]\d{3,10})"      # +CC NNN... NNN...
    r"|(?:\(?\d{3,4}\)?[\s.-]\d{3,4}[\s.-]\d{3,4})"    # (NNN) NNN-NNNN
    r"|(?:1[\s.-]\(?\d{3}\)?[\s.-]\d{3,4}[\s.-]\d{4})" # US 1-NNN-NNN-NNNN
    r"|(\d{7,})"                                          # 7+ consecutive digits
    r"|(?:\+\d{7,15})"                                    # +NNNNNNNNNNNN
)

# SSN: XXX-XX-XXXX or XXX XX XXXX (with word boundaries to avoid matching inside longer strings)
RE_SSN = re.compile(
    r"\b(?!000|666|9\d{2})\d{3}[-\s]\d{2}[-\s]\d{4}\b"
)

# Date of birth patterns — common formats:
#   MM/DD/YYYY, MM-DD-YYYY, YYYY-MM-DD, DD/MM/YYYY,
#   Month DD, YYYY, DD Month YYYY, etc.
RE_DOB_DATE = re.compile(
    r"\b(?:(?:0?[1-9]|1[0-2])[/\-.](?:0?[1-9]|[12]\d|3[01])[/\-.]\d{4}"
    r"|(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.]\d{4}"
    r"|\d{4}[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:0?[1-9]|[12]\d|3[01])"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s.,]+"
    r"(?:0?[1-9]|[12]\d|3[01])[,\s]+\d{2,4}"
    r"|(?:0?[1-9]|[12]\d|3[01])[,\s]+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s.,]+\d{2,4})\b",
    re.IGNORECASE,
)

# Street / mailing address — US-style heuristic:
#   123 Main St, 456 Oak Avenue, Suite 200, Apt 4B, etc.
# Matches number + street name + optional unit/suite, with or without city/state/zip tail.
RE_ADDRESS = re.compile(
    r"\b\d{1,6}\s+[\w\s]{2,40}(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|"
    r"Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Circle|Cir|Trail|Trl|"
    r"Parkway|Pkwy|Highway|Hwy|Terrace|Ter|Crescent|Cres)\b[.,]?"
    r"(?:\s*(?:Suite|Ste|Unit|Apt|Apartment|Floor|Fl|Rm|Room|#)\s*\w+)?"
    r"(?:\s*,?\s*(?:[A-Za-z\s]+,\s*)?(?:[A-Z]{2}\s*\d{5}(?:-\d{4})?))?",
    re.IGNORECASE,
)

# LinkedIn URL
RE_LINKEDIN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_]+/?"
)

# GitHub URL
RE_GITHUB = re.compile(
    r"https?://(?:www\.)?github\.com/[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,38}[a-zA-Z0-9])/?"
)

# Portfolio / personal website URL — generic personal site patterns.
# Matches URLs that are NOT LinkedIn/GitHub/Twitter and look like portfolio sites.
RE_PORTFOLIO_URL = re.compile(
    r"https?://(?:www\.)?"
    r"(?!linkedin\.com|github\.com|twitter\.com|x\.com|facebook\.com|instagram\.com)"
    r"[a-zA-Z0-9][a-zA-Z0-9\-_.]+\.[a-zA-Z]{2,}(?:/[^\s]*)?"
)

# Government ID — non-SSN identifiers:
#   - US passport: 9 digits (no dashes)
#   - Driver license: 1-2 letters + 6-14 digits (varies by state)
#   - Tax ID / EIN: XX-XXXXXXX format
#   - Aadhaar (India): XXXX XXXX XXXX (12 digits with spaces)
RE_GOV_ID = re.compile(
    r"(?:\b[A-Z]{1,2}[\s-]?\d{6,14}\b)"           # Driver license: letter prefix + digits
    r"|(?:\b\d{2}[\s-]?\d{7}\b)"                    # Tax ID / EIN
    r"|(?:\b\d{4}[\s]?\d{4}[\s]?\d{4}\b)"          # Aadhaar: 4+4+4 digits
    r"|(?:\b\d{9}\b)"                                 # US passport: 9 consecutive digits
    , re.IGNORECASE,
)

# Company / Employer ID — common formats:
#   - Employee ID: EMP-XXXXX, EID-XXX, etc.
#   - Company registration: various formats
RE_COMPANY_ID = re.compile(
    r"\b(?:EMP|EID|EMPID|EMPL)[\s\-_#]?\d{3,10}\b"
    r"|\b(?:COMP|CID|COID)[\s\-_#]?\d{3,10}\b",
    re.IGNORECASE,
)

# University / Student ID — common formats:
#   - Student ID: STU-XXXXXX, SID-XXXX, etc.
#   - Roll number: numeric with optional prefix
RE_UNIVERSITY_ID = re.compile(
    r"\b(?:STU|SID|ROLL|REG|UNI)[\s\-_#]?\d{3,12}\b"
    r"|\b(?:STUDENT|REGNO)[\s\-_#]?\d{3,12}\b",
    re.IGNORECASE,
)

# GPS coordinates — lat/long pairs:
#   - Decimal: 40.7128, -74.0060
#   - DMS: 40°42'46.0"N 74°0'21.6"W
RE_GPS_COORDINATES = re.compile(
    r"(?:-?\d{1,3}\.\d+[,\s]+-?\d{1,3}\.\d+)"       # Decimal degrees
    r"|(?:\d{1,3}°\d{1,2}'\d{1,2}(?:\.\d+)?\"?[NS]"   # DMS latitude
    r"[,\s]+\d{1,3}°\d{1,2}'\d{1,2}(?:\.\d+)?\"?[EW])"  # + DMS longitude
)

# Common first names for heuristic full-name detection (top ~200 US names).
_COMMON_FIRST_NAMES: set[str] = {
    "james", "john", "robert", "michael", "david", "william", "richard",
    "joseph", "thomas", "charles", "christopher", "daniel", "matthew",
    "anthony", "mark", "donald", "steven", "paul", "andrew", "joshua",
    "kenneth", "kevin", "brian", "george", "timothy", "ronald", "edward",
    "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas", "eric",
    "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin",
    "samuel", "raymond", "gregory", "frank", "alexander", "patrick", "jack",
    "dennis", "jerry", "tyler", "aaron", "jose", "nathan", "henry",
    "peter", "adam", "douglas", "zachary", "walter", "mary", "patricia",
    "jennifer", "linda", "barbara", "elizabeth", "susan", "jessica", "sarah",
    "karen", "lisa", "nancy", "betty", "margaret", "sandra", "ashley",
    "dorothy", "kimberly", "emily", "donna", "michelle", "carol", "amanda",
    "melissa", "deborah", "stephanie", "rebecca", "sharon", "laura", "cynthia",
    "kathleen", "amy", "angela", "shirley", "anna", "brenda", "pamela",
    "emma", "nicole", "helen", "samantha", "katherine", "christine",
    "debra", "rachel", "carolyn", "janet", "catherine", "maria", "heather",
    "diane", "ruth", "julie", "olivia", "joyce", "virginia", "victoria",
    "kelly", "lauren", "christina", "joan", "evelyn", "judith", "megan",
    "andrea", "cheryl", "hannah", "jacqueline", "martha", "gloria", "teresa",
    "ann", "sara", "madison", "frances", "kathryn", "janice", "jean",
    "abigail", "alice", "judy", "sophia", "grace", "denise", "amber",
    "doris", "marilyn", "danielle", "bianca", "lily", "natalie", "diana",
}

# Common last names (top ~100 for heuristic).
_COMMON_LAST_NAMES: set[str] = {
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller",
    "davis", "rodriguez", "martinez", "hernandez", "lopez", "gonzalez",
    "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin",
    "lee", "perez", "thompson", "white", "harris", "sanchez", "clark",
    "ramirez", "lewis", "robinson", "walker", "young", "allen", "king",
    "wright", "scott", "torres", "nguyen", "hill", "flores", "green",
    "adams", "nelson", "baker", "hall", "rivera", "campbell", "mitchell",
    "carter", "roberts", "gomez", "phillips", "evans", "turner", "diaz",
    "parker", "cruz", "edwards", "collins", "reyes", "stewart", "morris",
    "morales", "murphy", "cook", "rogers", "gutierrez", "ortiz", "morgan",
    "cooper", "peterson", "bailey", "reed", "kelly", "howard", "ramos",
    "kim", "cox", "ward", "richardson", "watson", "brooks", "chavez",
    "wood", "james", "bennett", "gray", "mendoza", "ruiz", "hughes",
    "price", "alvarez", "castillo", "sanders", "patel", "myers", "long",
    "ross", "foster", "jimenez", "powell", "jenkins", "perry", "russell",
    "sullivan", "bell", "coleman", "butler", "henderson", "barnes",
    "gonzales", "fisher", "vasquez", "simmons", "griffin", "acharya",
    "sharma", "patel", "singh", "kumar", "gupta", "agrawal", "chopra",
}


# ============================================================
# PIISanitizer
# ============================================================

class PIISanitizer:
    """
    Comprehensive PII detection, scrubbing, and rehydration engine.

    Two-layer architecture:
    - Layer 1: Regex-based pattern matching (fast, deterministic).
    - Layer 2: spaCy NER for PERSON and ORG entities (catches names
      like "Rahul Sharma" or orgs like "Tata Consultancy Services"
      that regex cannot reliably detect).

    Usage::

        sanitizer = PIISanitizer()

        # Scrub PII from text
        clean_text, mapping = sanitizer.scrub(raw_text)

        # Send clean_text to LLM...

        # Restore original text
        original = sanitizer.rehydrate(clean_text, mapping)

        # Just detect what PII is present
        items = sanitizer.detect(raw_text)

        # Extract structured contact information (useful for resume parsing)
        contact = sanitizer.get_contact_info(resume_text)
    """

    def __init__(self, detect_names: bool = True) -> None:
        """
        Args:
            detect_names: When True, both heuristic-based name detection
                          AND spaCy NER are enabled. Set to False to
                          disable all name/NER detection.
        """
        self.detect_names: bool = detect_names
        # Ordered list of (pii_type, compiled_regex, label_prefix) tuples.
        # Order matters: run more specific patterns first; phone last because it
        # is the most permissive and can accidentally match SSN/DOB fragments.
        self._patterns: list[tuple[str, re.Pattern[str], str]] = [
            ("email", RE_EMAIL, "EMAIL_ADDRESS"),
            ("linkedin", RE_LINKEDIN, "LINKEDIN_PROFILE"),
            ("github", RE_GITHUB, "GITHUB_PROFILE"),
            ("portfolio", RE_PORTFOLIO_URL, "PORTFOLIO_URL"),
            ("ssn", RE_SSN, "SSN"),
            ("gov_id", RE_GOV_ID, "GOVERNMENT_ID"),
            ("dob", RE_DOB_DATE, "DATE_OF_BIRTH"),
            ("address", RE_ADDRESS, "STREET_ADDRESS"),
            # company_id and university_id MUST come before phone because
            # phone's (\\d{7,}) alternation would otherwise consume their digits.
            ("company_id", RE_COMPANY_ID, "COMPANY_ID"),
            ("university_id", RE_UNIVERSITY_ID, "UNIVERSITY_ID"),
            ("gps", RE_GPS_COORDINATES, "GPS_COORDINATES"),
            ("phone", RE_PHONE, "PHONE_NUMBER"),
        ]
        # Counter for semantic placeholder numbering (per-scrub call)
        self._counters: dict[str, int] = {}
        logger.info(
            "PIISanitizer initialised (name detection=%s, NER=%s).",
            self.detect_names, _SPACY_AVAILABLE,
        )

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def scrub(self, text: str) -> tuple[str, dict[str, str]]:
        """
        Replace every detected PII occurrence with a semantic placeholder.

        Two-layer detection:
        1. Regex patterns (Layer 1)
        2. Heuristic name detection (Layer 2a — if detect_names)
        3. spaCy NER for PERSON/ORG (Layer 2b — if spacy available)

        The placeholder format is ``[TYPE_N]`` where TYPE is a human-readable
        label (e.g. EMAIL_ADDRESS, PHONE_NUMBER, PERSON_NAME, ORG_NAME) and
        N is a sequential counter per type within a single scrub call.  The
        same PII value appearing multiple times gets the same placeholder.

        Args:
            text: Raw text that may contain PII.

        Returns:
            A 2-tuple of (sanitized_text, pii_mapping_dict) where the mapping keys
            are placeholder strings and values are the original PII strings.
        """
        if not text:
            return "", {}

        # Reset counters for this scrub call
        self._counters = {}
        mapping: dict[str, str] = {}
        result = text

        # 1. Regex-based patterns (Layer 1)
        for pii_type, pattern, label in self._patterns:
            result = self._scrub_pattern(result, pattern, pii_type, label, mapping)

        # 2. Heuristic name detection (Layer 2a)
        if self.detect_names:
            result = self._scrub_names(result, mapping)

        # 3. spaCy NER (Layer 2b)
        if self.detect_names and _SPACY_AVAILABLE and _nlp is not None:
            result = self._scrub_ner(result, mapping)

        logger.info(
            "Scrubbed %d PII items from text (%d chars) — regex: %d, NER: %d.",
            len(mapping), len(text),
            sum(1 for v in mapping.values() if not v.startswith("_ner:")),
            sum(1 for v in mapping.values() if v.startswith("_ner:")),
        )
        return result, mapping

    def scrub_with_vault(
        self,
        text: str,
        session_id: str,
        ttl: int | None = None,
    ) -> tuple[str, dict[str, str]]:
        """Scrub PII and automatically store the mapping in the vault.

        Args:
            text: Raw text that may contain PII.
            session_id: Unique session identifier for vault storage.
            ttl: Optional per-session TTL override (seconds).

        Returns:
            (sanitized_text, pii_mapping) — same as scrub(), but also
            persists the mapping to the Redis-backed vault.
        """
        clean, mapping = self.scrub(text)
        pii_vault.store(session_id, mapping, ttl=ttl)
        return clean, mapping

    def rehydrate_from_vault(self, session_id: str, text: str) -> str:
        """Rehydrate text using the vault mapping for a given session.

        Args:
            session_id: The session whose PII mapping to use.
            text: Text containing semantic placeholders.

        Returns:
            The rehydrated text with original PII values restored.
        """
        mapping = pii_vault.retrieve(session_id)
        return self.rehydrate(text, mapping)

    def rehydrate(self, sanitized_text: str, pii_mapping: dict[str, str]) -> str:
        """
        Restore the original PII values into a sanitized string using the mapping
        produced by :meth:`scrub`.

        The longest placeholders are replaced first to avoid partial-match corruption.
        NER-tagged values (prefixed with ``_ner:``) have the prefix stripped
        during rehydration.

        Args:
            sanitized_text: Text with ``[TYPE_<hash>]`` placeholders.
            pii_mapping: The mapping dict returned by :meth:`scrub`.

        Returns:
            The rehydrated (original) text.
        """
        if not sanitized_text or not pii_mapping:
            return sanitized_text

        # Build a clean mapping that strips NER tags
        _NER_PREFIX = "_ner:"
        clean_mapping: dict[str, str] = {}
        for placeholder, value in pii_mapping.items():
            if value.startswith(_NER_PREFIX):
                clean_mapping[placeholder] = value[len(_NER_PREFIX):]
            else:
                clean_mapping[placeholder] = value

        result = sanitized_text
        # Replace longest keys first to prevent partial-match issues
        for placeholder in sorted(clean_mapping, key=len, reverse=True):
            result = result.replace(placeholder, clean_mapping[placeholder])

        return result

    def detect(self, text: str) -> list[dict[str, Any]]:
        """
        Scan *text* for PII and return a list of detected entities.

        Each entity is a dict with keys: ``type``, ``value``, ``start``, ``end``.

        Args:
            text: Raw text to scan.

        Returns:
            List of PII entity dicts, sorted by position in the text.
        """
        if not text:
            return []

        entities: list[PIIEntity] = []

        # Regex-based detections
        for pii_type, pattern, _label in self._patterns:
            for match in pattern.finditer(text):
                entities.append(PIIEntity(
                    pii_type=pii_type,
                    value=match.group(),
                    start=match.start(),
                    end=match.end(),
                ))

        # Heuristic name detection
        if self.detect_names:
            for match in self._find_name_candidates(text):
                # Skip if this span overlaps with an already-detected entity
                if not any(
                    not (match.end() <= e.start or match.start() >= e.end)
                    for e in entities
                ):
                    entities.append(PIIEntity(
                        pii_type="name",
                        value=match.group(),
                        start=match.start(),
                        end=match.end(),
                    ))

        # spaCy NER detection
        if self.detect_names and _SPACY_AVAILABLE and _nlp is not None:
            doc = _nlp(text)
            for ent in doc.ents:
                if ent.label_ in ("PERSON", "ORG"):
                    # Skip if this span overlaps with an already-detected entity
                    if not any(
                        not (ent.end_char <= e.start or ent.start_char >= e.end)
                        for e in entities
                    ):
                        entities.append(PIIEntity(
                            pii_type="ner_person" if ent.label_ == "PERSON" else "ner_org",
                            value=ent.text,
                            start=ent.start_char,
                            end=ent.end_char,
                        ))

        # Sort by position and deduplicate overlapping spans
        entities.sort(key=lambda e: e.start)
        deduped = self._deduplicate_entities(entities)

        return [e.to_dict() for e in deduped]

    def get_contact_info(self, text: str) -> dict[str, str | None]:
        """
        Extract structured contact information from text. Designed for resume /
        cover-letter parsing where contact details are typically at the top.

        Args:
            text: Raw text (e.g. extracted resume content).

        Returns:
            Dict with keys ``email``, ``phone``, ``linkedin``, ``github``.
            Values are the first match found (or ``None`` if not present).
        """
        if not text:
            return {"email": None, "phone": None, "linkedin": None, "github": None}

        email_match = RE_EMAIL.search(text)
        phone_match = RE_PHONE.search(text)
        linkedin_match = RE_LINKEDIN.search(text)
        github_match = RE_GITHUB.search(text)

        return {
            "email": email_match.group() if email_match else None,
            "phone": phone_match.group() if phone_match else None,
            "linkedin": linkedin_match.group() if linkedin_match else None,
            "github": github_match.group() if github_match else None,
        }

    # ----------------------------------------------------------
    # FastAPI Integration
    # ----------------------------------------------------------

    def scrub_dict(self, data: Any, pii_mapping: dict[str, str] | None = None) -> tuple[Any, dict[str, str]]:
        """
        Recursively scrub PII from all string values in a dict/list structure.
        Useful for sanitising entire JSON request bodies before forwarding to LLMs.

        Args:
            data: A JSON-serialisable structure (dict, list, str, or primitive).
            pii_mapping: Optional existing mapping to merge into.

        Returns:
            A 2-tuple of (scrubbed_data, merged_pii_mapping).
        """
        mapping = dict(pii_mapping) if pii_mapping else {}

        if isinstance(data, str):
            scrubbed, new_mapping = self.scrub(data)
            mapping.update(new_mapping)
            return scrubbed, mapping

        if isinstance(data, dict):
            scrubbed_dict: dict[str, Any] = {}
            for key, value in data.items():
                scrubbed_val, mapping = self.scrub_dict(value, mapping)
                scrubbed_dict[key] = scrubbed_val
            return scrubbed_dict, mapping

        if isinstance(data, list):
            scrubbed_list: list[Any] = []
            for item in data:
                scrubbed_item, mapping = self.scrub_dict(item, mapping)
                scrubbed_list.append(scrubbed_item)
            return scrubbed_list, mapping

        # Primitives (int, float, bool, None) pass through unchanged
        return data, mapping

    # ----------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------

    def _make_placeholder(self, value: str, label: str) -> str:
        """
        Generate a semantic, sequential placeholder for a PII value.

        Format: ``[LABEL_N]`` where N is a per-type counter (1-based).
        The same value always gets the same placeholder within a scrub call.
        """
        if label not in self._counters:
            self._counters[label] = 0
        self._counters[label] += 1
        return f"[{label}_{self._counters[label]}]"

    def _get_or_make_placeholder(self, value: str, label: str, mapping: dict[str, str]) -> str:
        """Return existing placeholder for *value* or create a new one."""
        for existing_ph, existing_val in mapping.items():
            if existing_val == value:
                return existing_ph
        return self._make_placeholder(value, label)

    # Regex that matches any already-inserted placeholder, e.g. [EMAIL_ADDRESS_1]
    _RE_PLACEHOLDER = re.compile(r"\[[A-Z_]+_\d+\]")

    def _scrub_pattern(
        self,
        text: str,
        pattern: re.Pattern[str],
        pii_type: str,
        label: str,
        mapping: dict[str, str],
    ) -> str:
        """
        Find all matches of *pattern* in *text*, create semantic placeholders,
        and accumulate them into *mapping*.

        Matches that overlap with existing placeholders are skipped so that
        earlier scrub passes are never corrupted.

        Returns the text with all matches replaced by placeholders.
        """
        result = text

        # Build a set of character ranges already occupied by placeholders
        protected_ranges: list[tuple[int, int]] = [
            (m.start(), m.end()) for m in self._RE_PLACEHOLDER.finditer(result)
        ]

        def _overlaps_placeholder(start: int, end: int) -> bool:
            return any(not (end <= ps or start >= pe) for ps, pe in protected_ranges)

        # Iterate in reverse so that earlier character positions are not
        # shifted by later replacements.
        matches = list(pattern.finditer(result))
        for match in reversed(matches):
            if _overlaps_placeholder(match.start(), match.end()):
                continue
            value = match.group()
            placeholder = self._get_or_make_placeholder(value, label, mapping)
            mapping[placeholder] = value
            result = result[:match.start()] + placeholder + result[match.end():]
            # Update protected ranges with the new placeholder
            protected_ranges.append((match.start(), match.start() + len(placeholder)))

        return result

    def _find_name_candidates(self, text: str) -> list[re.Match[str]]:
        """
        Heuristic name finder: looks for two consecutive capitalized words
        where at least one appears in the common-name sets.
        """
        name_pattern = re.compile(
            r"\b([A-Z][a-zA-Z'-]+)\s+([A-Z][a-zA-Z'-]+)\b"
        )
        candidates: list[re.Match[str]] = []
        for match in name_pattern.finditer(text):
            first = match.group(1).lower()
            last = match.group(2).lower()
            if first in _COMMON_FIRST_NAMES or last in _COMMON_LAST_NAMES:
                candidates.append(match)
        return candidates

    def _scrub_names(self, text: str, mapping: dict[str, str]) -> str:
        """Replace heuristic-detected names with semantic placeholders."""
        result = text
        matches = self._find_name_candidates(result)

        existing_placeholders = set(mapping.keys())

        for match in reversed(matches):
            span_text = match.group()
            if any(ph in span_text for ph in existing_placeholders):
                continue

            placeholder = self._get_or_make_placeholder(span_text, "CANDIDATE_NAME", mapping)
            mapping[placeholder] = span_text
            result = result[:match.start()] + placeholder + result[match.end():]

        return result

    def _scrub_ner(self, text: str, mapping: dict[str, str]) -> str:
        """Replace spaCy-detected PERSON and ORG entities with placeholders.

        This runs AFTER regex and heuristic layers, so it only catches
        entities that those layers missed.  spaCy can detect names like
        "Rahul Sharma" (non-Western names not in our heuristic list) and
        organizations like "Tata Consultancy Services" that regex cannot
        reliably match.

        Entities are tagged with a ``_ner:`` prefix in the mapping value
        to distinguish them from regex-detected entities.

        Strict filtering to avoid false positives:
        - Skip entities that overlap with already-scrubbed placeholders
        - Skip single-word ORG entities (usually labels like "SSN", "Email")
        - Skip entities that are entirely uppercase (likely labels, not names)
        - Skip entities shorter than 3 characters
        """
        if not _SPACY_AVAILABLE or _nlp is None:
            return text

        result = text
        existing_placeholders = set(mapping.keys())

        # Build a set of character ranges covered by already-scrubbed placeholders
        # in the current result text (which may differ from original text positions)
        protected_ranges: list[tuple[int, int]] = []
        for ph in existing_placeholders:
            idx = result.find(ph)
            while idx >= 0:
                protected_ranges.append((idx, idx + len(ph)))
                idx = result.find(ph, idx + len(ph))

        def _in_protected(start: int, end: int) -> bool:
            return any(not (end <= ps or start >= pe) for ps, pe in protected_ranges)

        doc = _nlp(text)
        # Collect all PERSON and ORG entities with strict filtering
        ner_entities = []
        for ent in doc.ents:
            if ent.label_ not in ("PERSON", "ORG"):
                continue
            span_text = ent.text

            # Skip single-character entities
            if len(span_text.strip()) <= 1:
                continue

            # Skip very short entities (< 3 chars) — likely labels
            if len(span_text.strip()) < 3:
                continue

            # Skip single-word ORG entities — these are almost always labels
            # like "SSN", "Email", "Phone", "LinkedIn" etc.
            if ent.label_ == "ORG" and len(span_text.split()) == 1:
                continue

            # Skip entities that are entirely uppercase (labels, not names)
            if span_text.isupper():
                continue

            # Skip if this span overlaps with an already-scrubbed placeholder
            if _in_protected(ent.start_char, ent.end_char):
                continue

            # Skip if the entity text contains an already-placed placeholder
            if any(ph in span_text for ph in existing_placeholders):
                continue

            ner_entities.append((ent.start_char, ent.end_char, span_text, ent.label_))

        # Process in reverse to preserve character positions
        for start, end, ent_text, ent_label in reversed(ner_entities):
            if ent_label == "PERSON":
                label = "PERSON_NAME"
            else:
                label = "ORG_NAME"

            placeholder = self._get_or_make_placeholder(ent_text, label, mapping)
            mapping[placeholder] = f"_ner:{ent_text}"
            result = result[:start] + placeholder + result[end:]
            existing_placeholders.add(placeholder)
            # Update protected ranges
            protected_ranges.append((start, start + len(placeholder)))

        return result

    @staticmethod
    def _deduplicate_entities(entities: list[PIIEntity]) -> list[PIIEntity]:
        """
        Remove overlapping entities, keeping the longer match when two entities
        overlap at the same position.
        """
        if not entities:
            return []

        deduped: list[PIIEntity] = [entities[0]]
        for entity in entities[1:]:
            prev = deduped[-1]
            if entity.start < prev.end:
                if (entity.end - entity.start) > (prev.end - prev.start):
                    deduped[-1] = entity
            else:
                deduped.append(entity)

        return deduped


# ============================================================
# FastAPI Dependency / Middleware Helpers
# ============================================================

def get_pii_sanitizer() -> PIISanitizer:
    """
    FastAPI dependency that returns a :class:`PIISanitizer` instance.

    Usage in an endpoint::

        from fastapi import Depends

        @router.post("/generate")
        async def generate(
            request: MyRequest,
            sanitizer: PIISanitizer = Depends(get_pii_sanitizer),
        ):
            scrubbed, mapping = sanitizer.scrub(request.user_text)
            # ... call LLM with scrubbed text ...
            result = sanitizer.rehydrate(llm_output, mapping)
            return {"result": result}
    """
    return PIISanitizer()


class PIIScrubMiddleware:
    """
    ASGI middleware that auto-scrubs JSON request bodies before they reach
    LLM-related endpoints. Only targets paths that contain ``/llm/`` or
    ``/api/llm/``.

    The raw request body is stored in ``request.state.raw_body`` so that
    downstream code can access the original if needed. The mapping is stored
    in ``request.state.pii_mapping`` for rehydration of responses.

    Usage in ``main.py``::

        from services.pii_sanitizer import PIIScrubMiddleware

        app.add_middleware(PIIScrubMiddleware)
    """

    EXCLUDED_PATHS: set[str] = {"/", "/health"}

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> Any:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        if not any(seg in path for seg in ("/llm/", "/api/llm/")):
            await self.app(scope, receive, send)
            return

        if path in self.EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return

        # Read the request body
        body_parts: list[bytes] = []
        async def receive_with_capture():
            message = await receive()
            if "body" in message:
                body_parts.append(message["body"])
            return message

        original_receive = receive
        body = b""
        more_body = True
        while more_body:
            message = await original_receive()
            if "body" in message:
                body += message["body"]
            more_body = message.get("more_body", False)

        # Scrub JSON body
        sanitizer = PIISanitizer()
        try:
            json_body = json.loads(body) if body else {}
            scrubbed_data, pii_mapping = sanitizer.scrub_dict(json_body)
            scrubbed_body = json.dumps(scrubbed_data).encode("utf-8")

            scope["state"] = getattr(scope, "state", {})
            scope["state"]["pii_mapping"] = pii_mapping
            scope["state"]["raw_body"] = body

            logger.info(
                "PII middleware scrubbed request body for %s (%d PII items).",
                path, len(pii_mapping),
            )
        except (json.JSONDecodeError, Exception):
            scrubbed_body = body
            logger.warning("PII middleware: request body is not JSON, passing through.")

        async def patched_receive():
            return {
                "type": "http.request",
                "body": scrubbed_body,
                "more_body": False,
            }

        await self.app(scope, patched_receive, send)


# ============================================================
# Convenience wrappers (used by resume_optimizer and other services)
# ============================================================

# Module-level singleton
pii_sanitizer = PIISanitizer()


def sanitize_pii(text: str) -> tuple[str, dict[str, str]]:
    """Convenience wrapper: scrub PII from text. Returns (sanitized_text, mapping)."""
    return pii_sanitizer.scrub(text)


def restore_pii(text: str, mapping: dict[str, str]) -> str:
    """Convenience wrapper: rehydrate PII into sanitized text."""
    return pii_sanitizer.rehydrate(text, mapping)
