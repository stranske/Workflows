#!/usr/bin/env python3
"""Reproduce the two validated CodeRabbit defects in actual production files."""

from deliberate_red_green import JS, NODE, PYTEST, PYTHON, RECOVERY, SUITE, main

MUTATIONS = [
    (
        "decoded-string-byte-accounting",
        JS,
        """        const rawValue = execFile('unzip', ['-p', archivePath, entry], {
          maxBuffer: Math.min(contentBudget * 4 + 1, remainingBytes),
        });
        remainingBytes -= rawValue.length;
        const value = rawValue.toString('utf8');""",
        """        const value = execFile('unzip', ['-p', archivePath, entry], {
          encoding: 'utf8',
          maxBuffer: Math.min(contentBudget * 4 + 1, remainingBytes),
        });
        remainingBytes -= Buffer.byteLength(value, "utf8");""",
        NODE + ["--test-name-pattern=counts raw bytes before", SUITE],
    ),
    (
        "receipt-io-masks-capacity-and-enters-auth-fallback",
        PYTHON,
        """            try:
                with Path(report).open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(receipt, sort_keys=True) + "\\n")
            except OSError as exc:
                LOGGER.warning(
                    "Verifier capacity receipt write failed (%s): %s", type(exc).__name__, exc
                )""",
        """            with Path(report).open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(receipt, sort_keys=True) + "\\n")""",
        PYTEST + [RECOVERY, "-k", "receipt_io_failure or receipt_permission_error"],
    ),
]

if __name__ == "__main__":
    main(MUTATIONS, "review-deliberate-red-green.json", require_capture=False)
