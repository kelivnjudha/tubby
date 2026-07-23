# Tubby Release Packaging

Tubby uses PyInstaller for self-contained desktop binaries, Inno Setup for the Windows
installer, and `hdiutil` for macOS disk images.

## Release Outputs

- `Tubby-VERSION-Windows-x64-Setup.exe`
- `Tubby-VERSION-macOS-arm64.dmg`
- `Tubby-VERSION-macOS-x64.dmg`
- `SHA256SUMS.txt`

The GitHub Actions workflow can be run manually to build downloadable artifacts without
creating a release. A matching version tag, such as `v0.10.0`, publishes the artifacts as a
GitHub release.

The packaged app includes a bundled FFmpeg executable through `imageio-ffmpeg`. After
installation, Tubby's first-run assistant installs Ollama from its official distribution
when needed, starts the service, and downloads the report and speech models selected by the
user. Multi-gigabyte model files remain on-demand downloads and are not duplicated inside
each installer.

## Windows Local Build

Install Python 3.10 or newer, the Tubby build extra, and Inno Setup:

```powershell
python -m pip install -e ".[build]"
python -m PyInstaller --noconfirm --clean tubby.spec
python packaging\windows\create_icon.py `
    public\logo\tubby_logo.png `
    build\installer\tubby_logo.ico
```

Compile `packaging\windows\Tubby.iss` with `ISCC.exe`, passing `AppVersion`, `SourceExe`,
`OutputDir`, and `SetupIcon` preprocessor definitions. The release workflow contains the
canonical invocation and smoke-tests the resulting installer.

## macOS Local Build

Use the target architecture natively:

```sh
python -m pip install -e ".[build]"
python -m PyInstaller --noconfirm --clean tubby.spec
version="$(python -c 'from tubby import __version__; print(__version__)')"
bash packaging/macos/build_dmg.sh dist/Tubby.app "$version" arm64 release
```

Use `x64` instead of `arm64` on an Intel Mac.

## Windows Signing Secrets

- `WINDOWS_CERTIFICATE_PFX`: Base64-encoded code-signing PFX
- `WINDOWS_CERTIFICATE_PASSWORD`: PFX password

When configured, the workflow signs both `Tubby.exe` and the final installer with SHA-256
and a trusted timestamp.

## macOS Signing And Notarization Secrets

- `MACOS_CERTIFICATE_P12`: Base64-encoded Developer ID Application `.p12`
- `MACOS_CERTIFICATE_PASSWORD`: Certificate password
- `MACOS_SIGNING_IDENTITY`: Full identity, for example
  `Developer ID Application: Example Company (TEAMID)`
- `APPLE_ID`: Apple developer account email
- `APPLE_TEAM_ID`: Apple Developer team ID
- `APPLE_APP_PASSWORD`: App-specific password for `notarytool`

The signing certificate is imported into a temporary keychain. PyInstaller signs the app
with hardened runtime options, the workflow signs the DMG, `notarytool` submits it to Apple,
and `stapler` attaches and validates the notarization ticket.
