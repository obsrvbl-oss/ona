# Changelog

## 5.1.4 - 2026-10-20

- Hardened privileged packet capture by routing capture tools through root-owned
  wrappers that validate arguments and moving the `pna` executable to
  `/usr/libexec/obsrvbl-ona/pna`, outside the service-owned installation tree.
- **Installation prerequisite:** Python 3.13 is required. Before installing a
  native package, configure an external package repository that supplies a
  `python3.13` DEB or RPM package with the interpreter at `/usr/bin/python3.13`.
  Older Python versions are no longer supported.
- **Upgrade note:** the first rollout to an existing RHEL sensor must be a
  reinstall, not an upgrade. The pre-5.1.4 RPM removal scriptlet can delete the
  newly installed files during an upgrade.
