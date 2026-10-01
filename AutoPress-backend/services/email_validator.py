import re
import socket
import os
from typing import Tuple

# Standard RFC 5322 compliant regex for practical email validation
EMAIL_REGEX = re.compile(
    r"^(?!\\.)[a-zA-Z0-9_.+-]+(?<!\.)@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$"
)

# Common disposable, temporary, and burner email providers
DISPOSABLE_DOMAINS = {
    "10minutemail.com", "10minutemail.net", "10minutemail.org",
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "tempmail.com", "tempmail.net", "temp-mail.org", "temp-mail.io",
    "yopmail.com", "yopmail.net", "yopmail.fr",
    "trashmail.com", "trashmail.net", "trashmail.me",
    "sharklasers.com", "grr.la", "guerrillamailblock.com",
    "getnada.com", "dispostable.com", "mytemp.email", "throwawaymail.com",
    "fakemailgenerator.com", "mohmal.com", "burnermail.io", "crazymailing.com",
    "emailondeck.com", "tempail.com", "inboxkitten.com", "generator.email",
    "maildrop.cc", "tempinbox.com", "discard.email", "spambox.us",
    "fakeinbox.com", "fastmail.fm", "deadaddress.com", "byom.de",
    "dropmail.me", "nada.ltd", "armyspy.com", "cuvox.de", "dayrep.com",
    "fleckens.hu", "gustr.com", "jourrapide.com", "rhyta.com", "superrito.com",
    "teleworm.us", "einrot.com", "zetmail.com", "chacuo.net"
}

# Block obvious fake and placeholder patterns
DUMMY_DOMAINS = {
    "test.com", "example.com", "fake.com", "asdf.com", "dummy.com",
    "nowhere.com", "invalid.com", "email.com", "sample.com"
}

# Domains whitelisted for internal operations and testing
WHITELIST_DOMAINS = {
    "autopress.com", "familyacadamyschool.com", "localhost"
}

CHECK_DNS = os.environ.get("CHECK_EMAIL_DNS", "false").lower() in ("true", "1")

def validate_real_email(email: str, allow_test_domains: bool = True) -> Tuple[bool, str]:
    """
    Validates that an email address is real, well-formed, and not disposable.
    Returns: (is_valid: bool, error_message: str)
    """
    if not email or not isinstance(email, str):
        return False, "Email address is required."

    email = email.strip().lower()

    if len(email) > 254:
        return False, "Email address is too long (maximum 254 characters)."

    if not EMAIL_REGEX.match(email):
        return False, "Please provide a valid email format (e.g. name@domain.com)."

    parts = email.split("@")
    if len(parts) != 2:
        return False, "Invalid email format."

    local_part, domain = parts[0], parts[1]

    if len(local_part) > 64:
        return False, "The local part of the email exceeds 64 characters."

    if ".." in local_part or ".." in domain:
        return False, "Email cannot contain consecutive dots."

    # Verify TLD has valid letters
    tld = domain.split(".")[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False, "Email must have a valid top-level domain (e.g. .com, .org, .et)."

    # Allow whitelisted domains for system and testing
    if allow_test_domains and domain in WHITELIST_DOMAINS:
        return True, ""

    # Reject disposable / burner email domains
    if domain in DISPOSABLE_DOMAINS:
        return False, f"Disposable or temporary email addresses (@{domain}) are not permitted. Please use your real email."

    # Reject obvious dummy / test domains
    if domain in DUMMY_DOMAINS:
        return False, "Please enter a valid, active email address rather than a test domain."

    # Optional DNS MX/Host resolution check for production
    if CHECK_DNS:
        try:
            socket.gethostbyname(domain)
        except (socket.gaierror, socket.herror, Exception):
            return False, f"The email domain (@{domain}) does not exist or cannot receive mail."

    return True, ""
