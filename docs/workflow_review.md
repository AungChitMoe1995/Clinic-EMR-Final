# Workflow review, 15 October 2026

## Corrections

- GET navigation no longer writes encounters, starts appointments or logs out. Forms carry session CSRF tokens.
- Appointment conversion returns an existing linked visit, rejects cancelled/no-show/completed appointments without a linked visit, and copies the previous completed history.
- Existing clinician assignment survives other staff editing. The form displays the assigned clinician, with explicit selection for reassignment.
- Height and RBS now persist. Clearing vital inputs clears their saved values. BMI calculation has labelled units. Prescription autocomplete stores the medicine name without stock information appended to it.
- Version counters detect concurrent encounter, appointment and voucher updates. Clinical save snapshots include histories, vital rows, diagnoses, prescriptions and investigations/procedures, before and after editing. They commit with the clinical change.
- Payment validation rejects overpayments, invalid methods and cancelled vouchers. Decimal calculations round financial totals to two places, including display formatting.
- Conditional stock updates avoid read/modify/write balance losses. Non-finite, negative and invalid movements are rejected. Prescription writing does not issue stock.
- Registration counters use compare-and-swap updates rather than relying on SQLite row locks. Number gaps remain possible and documented.
- Stale/deactivated sessions lose access. First-clinic registration is explicit and cannot create unrelated clinic accounts in an occupied installation.
- Static assets load locally, browser history/prefetch no longer carries clinical page snapshots, and HTML responses use no-store caching.

## Architecture decision

The review retains one clinic per database with shared trusted-user access, following the existing application design. Account is a login identity, not a tenant boundary. Do not market this as a multi-clinic SaaS.

## Evidence and limits

The local SQLite database had no Alembic tracking table. The upgrade tool checked required baseline columns, backed up the database, stamped the baseline and applied the additive migration. No remote schema was changed. Python/Jinja/JavaScript syntax checks and a separate fictitious UI preview were completed. The automated suite was not rerun for this revision. This document does not claim clinical or production validation.

Technical references: [SQLAlchemy version counters](https://docs.sqlalchemy.org/en/20/orm/versioning.html), [SQLite foreign keys](https://www.sqlite.org/foreignkeys.html).
