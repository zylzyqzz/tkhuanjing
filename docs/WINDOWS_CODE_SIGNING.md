# Windows release signing

The Windows release workflow only publishes an installer after all executables
have a valid Authenticode signature. Unsigned installers must not be promoted to
the public update channel.

## Required GitHub Actions secrets

- `CODE_SIGNING_PFX_BASE64`: the complete production code-signing PFX encoded as
  a single-line Base64 value.
- `CODE_SIGNING_PFX_PASSWORD`: the PFX import password.

Configure both values in the repository's Actions secrets. Do not commit the PFX,
its password, or its Base64 representation to this repository.

On macOS or Linux, create the Base64 value locally with:

```bash
base64 < production-code-signing.pfx | tr -d '\n'
```

On PowerShell, use:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("production-code-signing.pfx"))
```

After configuring the secrets, manually run **Build Windows Client**. The job
signs and verifies the client, updater, and installer, creates SHA-256 checksums,
and uploads the artifact only if every gate succeeds.

## Certificate requirements

- The certificate must be issued for Windows code signing and include its private key.
- The certificate must be valid and trusted on supported Windows versions.
- Keep timestamping enabled so signatures remain verifiable after certificate expiry.
- Prefer an EV code-signing certificate or a hardware/cloud-backed signing service
  for stronger Microsoft SmartScreen reputation and private-key protection.
