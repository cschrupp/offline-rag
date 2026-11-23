# Earlier successful local rehearsal — superseded

This 36-send synthetic rehearsal passed with full restoration, but it used a
two-second global deadline for ordinary requests. That does not represent the
accepted 180-second load setting and a later attempt exposed the cold-arm
preparation timeout edge case. Do not use this run as the final driver
qualification.

The corrected final run is
[`../51c14191c20a4084`](../51c14191c20a4084), where ordinary loads use 180
seconds and only the explicit deadline lifecycle test has the local two-second
override. Both runs remain preserved as historical engineering evidence.
