# Security and data handling

_The public verification commands are designed to read files and recalculate values._

## 🔒 Scope

The standard-library verification tools do not call a model, access the network, execute a received binary, load a serialized executable checkpoint or modify evidence. Optional figure generation writes image files locally and has separately pinned dependencies.

The manifest rejects changed/missing files and unsafe or linked artifact paths. It is an integrity record, not a signature proving who performed an experiment. Use a trusted Git commit/release when checking a copy.

## 📦 Report responsibly

Do not place credentials, account paths, authentication material, confidential source or protected test inputs in a public issue. For a possible security vulnerability, use the repository’s **Security → Advisories → Report a vulnerability** flow when available. Otherwise open only a minimal issue requesting a private reporting channel, without the sensitive details.

Public timing data should reveal only the identifiers and conditions needed for its stated claim. A future evaluated system must be unable to read its protected confirmation cases; repository structure or a `workspace-write` setting alone does not establish that isolation.
