# Exit Codes

| Code | Meaning                           | Status            |
|------|-----------------------------------|-------------------|
| 0    | Success                           | implemented       |
| 1    | Unhandled exception               | Python OS default |
| 2    | CLI usage error                   | implemented       |
| 3    | Config / cache error              | implemented       |
| 4    | Network / TLS / HTTP error        | implemented       |
| 5    | HTTP protocol error (4xx / 5xx)   | planned           |

**Notes:**
- Code 1 is never returned explicitly — Python raises it automatically for uncaught exceptions outside `main()`.
- Code 5 is planned to distinguish HTTP-level errors (4xx/5xx responses) from network/TLS errors (code 4).
  Currently both map to code 4 via the catch-all `except Exception` handler in `main.py`.
