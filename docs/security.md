# Security and ownership

The public launchers execute repository code fetched over HTTPS. Their archive downloads use TLS, but `main` is mutable and there is no independent publisher signature in this milestone. A checksum from the same compromised source is not an independent trust guarantee. Inspect a clone or pin **both** the launcher URL and `DEV_COCKPIT_REF` to the same reviewed commit for reproducible source execution. Versioned, verified release bundles remain an open milestone.

Package installation delegates to Homebrew/WinGet. Their repositories and installers become part of the trust chain; versions are not currently locked by this project. WinGet's source/package agreement flags apply only with explicit `--install`. Installation is not a transaction: a later failure does not uninstall previously completed packages.

Config application enumerates a fixed set of destinations. It creates absent files, hashes its own outputs, and updates/removes only content still matching the ownership ledger. Existing unmanaged files and edited managed files are preserved. Symlink/reparse targets are rejected. Writes use temporary sibling files and atomic replacement; interrupted writes may leave an unmanaged file, which a retry preserves. Concurrent setup is refused by an exclusive, per-home `configuration.lock` (fail-closed, so a second installer never races an active one); interrupted writes still leave unmanaged files preserved on retry.

Shell profiles, Git settings, SSH files, private keys, tokens and provider authentication are not modified. No project telemetry, scheduled updater, background indexer, memory service or hosted sync is added. Upstream tools can have their own network behavior and telemetry; those policies require separate review when enabled.

Only licensed theme data is vendored. The initial setup installs no third-party Herdr/OMP plugins, skills, hooks or MCP servers. Herdr's marketplace is unreviewed and plugins execute host commands; OMP's config discovery can load integrations already present in other agent directories. Inspect those configurations before enabling them.

Existing SSH authentication, host-key checks and YubiKey touch/PIN requirements remain unchanged. No agent forwarding, unattended identity or altered SSH connection policy is configured. Remote acceptance requires the actual host and hardware key.
