"""Task 3.2: Local rule-based safety engine for shell commands."""

import re

# Patterns that are ALWAYS blocked (high risk)
DENY_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\b",  # rm -rf /
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f",            # rm -rf
    r"\bmkfs\b",                                  # format filesystem
    r"\bdd\s+if=",                                # dd raw disk write
    r"\b:(){ :\|:& };:",                          # fork bomb
    r"\bsudo\s+rm\b",                             # sudo rm
    r"\bchmod\s+-R\s+777\s+/",                    # chmod -R 777 /
    r"\bDROP\s+(TABLE|DATABASE)\b",               # SQL drop
    r"\bTRUNCATE\s+TABLE\b",                      # SQL truncate
    r">\s*/dev/sd[a-z]",                          # overwrite disk
    r"\bshutdown\b",                              # shutdown
    r"\breboot\b",                                # reboot
    r"\binit\s+0\b",                              # init 0
    r"\bkill\s+-9\s+(-1|1)\b",                    # kill all processes
]

# Patterns that require user confirmation (medium risk)
WARN_PATTERNS = [
    (r"\bsudo\b", "uses sudo (elevated privileges)"),
    (r"\brm\s", "removes files"),
    (r"\bmv\s", "moves/renames files"),
    (r"\bchmod\b", "changes file permissions"),
    (r"\bchown\b", "changes file ownership"),
    (r"\bkill\b", "kills a process"),
    (r"\bpkill\b", "kills processes by name"),
    (r"\bgit\s+push\s+.*--force", "force pushes to git"),
    (r"\bgit\s+reset\s+--hard", "hard resets git"),
    (r"\bcurl\b.*\|\s*(ba)?sh", "pipes download to shell"),
    (r"\bwget\b.*\|\s*(ba)?sh", "pipes download to shell"),
    (r">\s", "redirects output (may overwrite files)"),
]


def check_command(command: str) -> dict:
    """Check a shell command for safety risks.

    Returns:
        {"level": "safe"|"warn"|"deny", "reasons": [...]}
    """
    # Check deny patterns first
    for pattern in DENY_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return {
                "level": "deny",
                "reasons": [f"Blocked: matches dangerous pattern `{pattern}`"],
            }

    # Check warn patterns
    reasons = []
    for pattern, reason in WARN_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            reasons.append(reason)

    if reasons:
        return {"level": "warn", "reasons": reasons}

    return {"level": "safe", "reasons": []}
