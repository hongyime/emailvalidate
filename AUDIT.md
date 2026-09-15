# Audit — emailvalidate

Updated: 2026-09-15

The original requirements installed `validate-email==1.3`, while the script called the distinct `py3-validate-email` API. Importing the module immediately opened an address list and started processing. Ambiguous results and a swallowed keyboard interrupt were sent to the invalid-address file, and repeat runs appended duplicates. The prior generic audit did not detect these defects.

The repair pins the intended provider, loads it only when the CLI runs, disables its unused blacklist updater and validates its function signature before opening output files. Definitive validation failures remain distinct from operational/inconclusive results. Input is streamed, completed lines are flushed, existing outputs are refused and interruption stops processing. Duplicate occurrences within the input are intentionally preserved.

All 22 synthetic tests pass locally on Python 3.12; installed dependencies are compatible. Cases cover the actual provider API with mocked DNS/SMTP, known/unknown failures, interruption, import behavior, updater suppression, output races and reruns. Linux and Windows hosted checks must pass before release. The existing label workflow is also corrected to use `.github/labels.yml`.

No real address list or existing result file was read or changed, and no live DNS/SMTP validation was performed. SMTP replies do not guarantee future delivery. Tests establish the mocked contract and file behavior, not deliverability for any real address. This is a local CLI with static GitHub Pages instructions; no Vercel CPU reduction or monthly quota headroom is claimed.
