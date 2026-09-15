# PRD: emailvalidate

## Overview
A Python CLI script that bulk-validates a list of email addresses using three-layer verification: format checking, DNS MX record lookup, and SMTP handshake. Splits input into valid, invalid and unknown output files; inconclusive checks are never treated as proof of invalidity. Target user: marketers or developers who need to clean an email list before a send campaign.

## Goals
- Accept a flat list of email addresses (one per line in `emails.txt`)
- Validate each address via format, DNS, and SMTP checks
- Write results to fresh `true emails.txt`, `false emails.txt` and `unknown emails.txt` files while preserving all prior outputs
- Show a progress bar during processing

## Non-Goals
- Web UI or API endpoint
- Deduplication of input list
- Handling email formats other than plain `user@domain.tld`
- Rate limiting / bulk SMTP throttling
- Output formats other than plaintext

## User Stories
- As a marketer, I have a CSV export of 10,000 emails and want to remove invalid ones before a campaign.
- As a developer, I want to test which addresses in a collected list actually have working mail servers.

## Tech Stack
- **Language**: Python 3.11+
- **Libraries**: `py3-validate-email` (pip), `tqdm` (pip)
- **Runtime**: any OS with Python 3 and internet access

## Architecture
```
emailvalidate/
├── validateemail.py   # main script
├── emails.txt         # input file (user-provided)
├── true emails.txt    # output: valid addresses
└── false emails.txt   # output: invalid addresses
```

Single-file script:
1. Read `emails.txt` line by line
2. For each address, call `validate_email()` with format + DNS + SMTP flags
3. Write and flush each result to its exclusively created output file
4. Update `tqdm` progress bar

## Features (detailed)

### Format Validation
- Checks email conforms to RFC format (local@domain.tld)
- Acceptance criteria: malformed strings return `False`

### DNS Validation
- Looks up MX records for the email's domain
- Timeout: 3 seconds
- Acceptance criteria: domains with no MX records return `False`

### SMTP Validation
- Opens SMTP connection and checks if the mailbox exists
- Timeout: 3 seconds
- Does not send actual email
- Acceptance criteria: explicit recipient rejection returns `False`; temporary, ambiguous, TLS and communication failures remain unknown. A passing probe cannot guarantee future delivery.

### Progress Display
- `tqdm` progress bar showing current index and total count
- Handles `KeyboardInterrupt` by stopping processing, closing the bar and retaining completed results without classifying the interrupted address

## Data / Config
| File | Purpose |
|------|---------|
| `emails.txt` | Input — one email per line, UTF-8 |
| `true emails.txt` | Output — addresses that passed all checks |
| `false emails.txt` | Output — definitive validation failures |
| `unknown emails.txt` | Output — inconclusive or operational failures |

No config file is needed. `--input` selects the UTF-8 input file and `--output-dir` selects an existing directory without prior result files. Validation settings retain the original format/DNS/SMTP checks and timeouts.

## Deployment / Run
```bash
python -m pip install -r requirements.txt
# place your email list in emails.txt
python validateemail.py
```

## Constraints & Notes
- **Speed**: Checks are sequential. Three-second timeout settings apply to DNS/SMTP operations; multiple mail servers can increase per-address duration.
- **Blacklist**: `check_blacklist=False` — disposable email domains are not filtered
- **SMTP accuracy**: some valid servers reject SMTP probes (false negatives expected)
- **Network required**: DNS and SMTP checks need internet access

## Verified repair (2026-09-15)

The package/API mismatch, import-time processing, swallowed interruption and ambiguous-as-invalid behavior are repaired. Repeated runs refuse previous output files instead of appending duplicate results; duplicate occurrences within an input list remain supported. The unused provider blacklist updater is disabled. The current CLI contract and recovery limits are documented in README. Twenty-two offline tests cover the real dependency with mocked provider replies; hosted Linux/Windows checks are required before release.
