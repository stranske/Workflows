# Required Gate status publisher regression

Related to closed source #3757; no broad acceptance issue is reopened.

Incident: Inv-Man-Intake#1006 head102ebbe3a6d93275f015fe1485d2fefdbde578a6
had successful Gate attempt2 and a real successful Gate / gate status, but the
REST status object has no app foreign key. The installed reporter correctly
returned UNKNOWN rather than silently accepting an unproven required app.

The regression fixture retains the actual status/run/suite/job IDs and report
step interval. The resolver requires authenticated immutable platform publisher
identity plus exact repository/head/attempt/suite/check/step correspondence.
A URL or login alone cannot bind the app. Negative fixtures remain UNKNOWN;
a missing status stays FAIL and a failed check cannot be hidden.

Validation:184 focused tests pass; Ruff and whole-repository Black pass.
Two actual production-source controls fail their named tests when broken and
pass after byte-identical restoration (see provenance-controls.json).
Live authenticated API correspondence is retained in the adjacent JSON.
This is reviewed source only; no installed mirror was overwritten.
