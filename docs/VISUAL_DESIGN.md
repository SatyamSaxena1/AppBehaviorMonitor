# Visual reviews and session history

2026-11-12: User wants to see findings rather than read a report, and earlier sessions must not return as fresh warnings.

Research: Apple HIG [Charting data](https://developer.apple.com/design/human-interface-guidelines/charting-data), [Disclosure controls](https://developer.apple.com/design/human-interface-guidelines/disclosure-controls), [Tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars).

Chosen patterns:
- App-to-resource tiles show relationships in cited evidence. Tapping opens explanation/evidence; it does not contact the domain or perform a recommended action.
- Labeled horizontal bars show category composition of cited evidence, not total usage or risk. VoiceOver receives counts and denominators. All categories use the same teal, with text identifying their meaning.
- A short takeaway and numbered next moves stay visible. Longer interpretation and evidence expand on demand. Confidence and limitations remain visible even when collapsed.
- Four stable destinations: Overview (status/latest preview), Insights (latest session), History (previous sessions), Settings (review request/preferences). Developer Mode adds a fifth diagnostic destination.
- History uses neutral cards and one open session at a time. No alert badges or red threat labels. Viewed status is persisted locally by finding ID; viewed does not mean resolved.

Sessions currently group adjacent reviews from the same author with gaps of at most 30 minutes. This is a UI heuristic, not an MCP conversation identifier. Latest session appears in Insights for 24 hours; previous sessions and older reviews appear in History. Underlying records, evidence, priorities, and seven-day retention are unchanged. No automatic AI calls or uploads.

Rejected for now: safety/risk rings (no calibrated score), trend charts (cited evidence is not an unbiased activity sample), force-directed network graphs (complex with little evidence), and newer OS-only glass/tab APIs (device targets iOS 15).

Validation: native compiler/signing and isolated Foundation session-group tests; package/collector smoke test. Actual installed layout, Dynamic Type, VoiceOver interaction, and taps need device observation.
