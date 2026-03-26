---
name: unit-testing
description: Ensure code reliability without external testing frameworks — using Python's built-in unittest module and manual assertion helpers to validate bot logic before any real money is at risk.
---

### Purpose
Ensure code reliability without external testing frameworks — using Python's built-in `unittest` module and manual assertion helpers to validate bot logic before any real money is at risk.

### When to Use
- Validating safety-critical logic (kill switch, duplicate guard)
- Testing utility functions (retry logic, config validation)
- Regression checks before advancing between phases
- Verifying error handling behaves correctly for each exception type

### Mandates (REQUIRED)
1. Use Python's built-in `unittest` — no third-party testing libraries
2. Use `unittest.mock.patch` to mock the Binance client — never hit the real API in tests
3. Group tests by module (`TestConfig`, `TestDatabase`, `TestLive`, etc.)
4. Test both the happy path and edge cases for every critical function
5. Every test class must have a docstring explaining what module it covers
6. Run all tests from the project root with `python -m unittest discover`

### Prohibited (FORBIDDEN)
- No external dependencies (`pytest`, `hypothesis`, etc.)
- No tests that hit the real Binance API or write to the production DB
- Don't skip error cases — the unhappy path is where the bot breaks in production
- Never assert on log output alone — assert on state changes (DB rows, return values)
- No test that passes vacuously (e.g. asserting on a value you just set yourself)

### Running the Tests

```bash
# Run all tests from project root
python -m unittest discover

# Run a specific test class
python -m unittest tests.test_bot.TestLive

# Run with verbose output
python -m unittest discover -v
```

### Test File Location

```
dca-bot/
└── tests/
    ├── __init__.py
    └── test_bot.py     # All test classes live here
```

### Phase Gate Reminder

Before advancing from **forward_test → live**, all of the following must pass:

- [ ] `TestConfig` — all cases green
- [ ] `TestDatabase` — all cases green
- [ ] `TestLive.test_kill_switch_skips_when_balance_too_low` ✓
- [ ] `TestLive.test_duplicate_guard_blocks_second_order` ✓
- [ ] `TestLive.test_api_exception_is_not_retried` ✓
- [ ] `TestLive.test_network_error_retries_up_to_max` ✓
