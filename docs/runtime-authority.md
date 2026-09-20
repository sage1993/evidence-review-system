# Runtime authority

The CLI bootstrap distinguishes installed wheel authority from development
checkout identity. `doctor` reports the actual interpreter, command path,
imported package root, distribution version and package root, and nearby
repository root/HEAD separately. Repository HEAD is not a wheel build commit.

An installed package is checked against its distribution RECORD: all packaged
runtime files must match their SHA-256, size and inventory. The resulting
`package_source_sha256` identifies the package content. RECORD is a local
consistency check, not a publisher signature. Pin a candidate using a digest
recorded during isolated wheel qualification; the wheel archive SHA-256 remains
a separate release acceptance identity.

```powershell
evidence-review --runtime-mode installed doctor
evidence-review --runtime-mode installed --expected-package-sha256 <package-content-sha256> workspace active --repository-root <control-directory>
```

The control directory stores the explicit active workspace binding; it need not
contain source code or Git. A nearby checkout does not override a verified wheel.
The binding continues to verify the finalized evidence logical snapshot and
exact closed-file database hash.

`auto` selects installed mode when wheel package files are owned by distribution
metadata. Otherwise it selects development mode, retaining checkout/import path
matching. `--runtime-mode development` explicitly selects development checks;
it is not production acceptance. An expected content digest always requires
installed mode, even if development was requested.

Installed mode rejects nonempty `PYTHONPATH` with `BYPASS_DETECTED`, including
when the injected path has not yet shadowed a module. Missing wheel ownership,
editable/source imports, modified or extra package files, and a different
expected candidate digest produce `SOURCE_MISMATCH`. Error diagnostics include
actual and distribution paths, expected digest and an identity explanation.
No import path is repaired or injected automatically. Use a clean Python 3.13
venv with the candidate wheel installed and `PYTHONPATH` unset for acceptance.

`--help` and `--version` remain dependency-safe informational commands; their
successful exit is not runtime acceptance. Full qualification still requires
the clean exact-SHA repository gate and isolated wheel/scenario evidence.
