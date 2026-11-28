# AGENTS.md — Exam Arena Engineering Rules

- **Owner:** Exam Arena Maintainer (Student Capstone Developer)
- **Review Cadence:** Reviewed prior to each release or exam-engine update.
- **Change Process:** Updates require a Pull Request with clear rationale and human review.

## Repository Rules & Rationale
1. **Source of Truth:** Always read `app.py` and `templates/` before adding routes or database queries. *Rationale: Ensures new endpoints match existing SQLite schemas (`exam_arena.db`) and template variables.*
2. **Scope Control:** Do not modify `Procfile`, `requirements.txt`, or `exam_arena.db` schema unprompted. *Rationale: Protects live Render deployment stability and prevents data loss.*
3. **Security & Exam Integrity:** Never pass correct answer keys into HTML `templates/` or client-side JavaScript during an active exam, and use parameterized SQL queries. *Rationale: Prevents SQL injection and stops students from inspecting page source to cheat.*
4. **Verification Standard:** Add unit tests in `test_app.py` covering scoring, routes, and edge cases before merging. *Rationale: Ensures reliable exam grading.*