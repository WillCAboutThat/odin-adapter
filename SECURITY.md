# Security

Odin runs locally. The Core writes only inside the knowledge-base directory
you point it at; the plugin stores no credentials and makes no network calls
of its own — outward reaches happen through your own connectors, only on your
instruction.

If you believe you've found a vulnerability — for example, a crafted document
or MCP call that writes outside the base, executes code, or corrupts
provenance records — please email **william@willcaboutthat.com** rather than
opening a public issue. Include reproduction steps and your plugin version.
You'll get a response within a few days.
