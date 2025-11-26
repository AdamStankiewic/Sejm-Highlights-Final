# Fix for pkg_resources Deprecation Warning

## Problem

You may see this warning when running the application:

```
UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html.
The pkg_resources package is slated for removal as early as 2025-11-30.
Refrain from using this package or pin to Setuptools<81.
  import pkg_resources
```

## Root Cause

This warning comes from the `ctranslate2` package (a dependency of `faster-whisper`), which still uses the deprecated `pkg_resources` API. The issue is tracked upstream:
- [CTranslate2 PR #1911 - Fixed pkg_resources Deprecated Warning](https://github.com/OpenNMT/CTranslate2/pull/1911)
- [faster-whisper Issue #1360](https://github.com/SYSTRAN/faster-whisper/issues/1360)

## Solution

We've pinned `setuptools` to version `<81` as a temporary workaround. To apply this fix:

### Windows (PowerShell)

```powershell
# Activate your virtual environment
.\venv\Scripts\Activate.ps1

# Downgrade setuptools
pip install "setuptools<81"

# Verify the version
pip show setuptools
```

### Linux/Mac (bash)

```bash
# Activate your virtual environment
source venv/bin/activate

# Downgrade setuptools
pip install "setuptools<81"

# Verify the version
pip show setuptools
```

## Verification

After applying the fix, run your application again:

```powershell
python apps\stream_app.py
```

The warning should no longer appear.

## Future

Once CTranslate2 merges the fix and releases a new version, we can remove the setuptools version constraint and upgrade to the latest version.

## References

- [Stack Overflow: pkg_resources is deprecated as an API](https://stackoverflow.com/questions/76043689/pkg-resources-is-deprecated-as-an-api)
- [Python Discussions: Pkg_resources is deprecated warning](https://discuss.python.org/t/pkg-resources-is-deprecated-warning/59517)
- [Setuptools Documentation on pkg_resources](https://setuptools.pypa.io/en/latest/pkg_resources.html)
