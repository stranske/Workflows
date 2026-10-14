# Supplied diff snapshot identity guard

Before this repair, changed raw diff bytes or a missing diff_sha256 snapshot field reached evaluator invocation. Six new evaluate/compare cases reproduced the missing guard and uncaught invalid UTF-8: RED6, controls GREEN2. The repair checks the exact raw diff hash before any snapshot enrichment and compares loaded normalized text with newly read raw bytes. Rejected inputs preserve context/diff/snapshot bytes and never invoke evaluation. CRLF hash and evaluator-LF controls remain valid.

Deliberately disabling only the production diff hash guard produces RED4/GREEN4; byte-identical restoration produces GREEN8. Raw logs and production hash are adjacent. The two other negative cases test UTF-8 rejection rather than that hash guard. No count, provider generation, paid invocation, partition acceptance or native-fit claim is made. Source/template copies match.
