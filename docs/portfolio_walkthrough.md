# Portfolio demonstration guide

Use a separate database containing fictitious records. The prototype represents one clinic, with trusted staff sharing access.

1. Show the patient profile and explain why a stable registration number differs from demographic details that can change. Point out multiple phone numbers and a longitudinal encounter timeline.
2. Book an appointment and explain the difference between a scheduled event and a clinical visit. Start the visit through its explicit form. Reopening the conversion reuses the link.
3. Explain why prior history carries forward for review, while the presenting complaint and examination belong to the current visit. Demonstrate the labelled vital inputs and height/weight BMI calculation without treating it as decision support.
4. Explain why a doctor's prescription does not prove that medicine was dispensed. Stock changes require a separate ledger transaction and are checked against availability.
5. Create an encounter-linked voucher. Explain item quantities, price, discount, partial payment, outstanding balance and final settlement. A billed amount differs from a cash collection.
6. Show an encounter's before/after revision in the audit view. Explain concurrent-edit detection and the remaining limit: this database audit is not externally retained or tamper-evident.

Discuss the design boundaries honestly: shared clinic access, no tenant isolation, no drug interaction or dose advice, no claim of FHIR/HL7 compliance, and no production/clinical validation. Automated tests were not run for this revision.
