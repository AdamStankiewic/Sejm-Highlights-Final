# Fix for pkg_resources Deprecation Warning

## Problem

You may see this warning when running the application:

```
UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html.
The pkg_resources package is slated for removal as early as 2025-11-30.
Refrain from using this package or pin to Setuptools<81.
  import pkg_resources
```

This warning appears at line 8 of `ctranslate2/__init__.py`.

## Root Cause

This warning comes from the `ctranslate2` package (a dependency of `faster-whisper`), which still uses the deprecated `pkg_resources` API. The issue is tracked upstream:
- [CTranslate2 PR #1911 - Fixed pkg_resources Deprecated Warning](https://github.com/OpenNMT/CTranslate2/pull/1911) (open, not yet merged)
- [faster-whisper Issue #1360](https://github.com/SYSTRAN/faster-whisper/issues/1360) (closed, deferred to ctranslate2)

The warning was introduced in setuptools v67.5.0 (April 2023) and has been present in all versions since then. Simply pinning setuptools to a version `<81` does **not** suppress the warning because the warning was added much earlier (v67.5.0).

## Solution

**✅ The fix has been implemented in the codebase.**

We've added warning filters in two locations to suppress this specific warning:

1. **`pipeline/__init__.py`** - Suppresses the warning early in the import chain
2. **`pipeline/stage_03_transcribe.py`** - Suppresses the warning before importing `faster_whisper`

The fix uses Python's built-in `warnings` module:

```python
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)
```

## For Users

**No action required!** The warning is now suppressed automatically when you run the application. Simply:

```powershell
# Windows
python apps\stream_app.py

# Or run the GUI
python app.py
```

The warning should no longer appear.

## For Developers

If you're adding new files that import `faster-whisper` or `ctranslate2`, add this warning filter at the top of your file before the import:

```python
# Suppress pkg_resources deprecation warning from ctranslate2
# See: https://github.com/OpenNMT/CTranslate2/pull/1911
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)

# Now safe to import
from faster_whisper import WhisperModel
```

## Future

Once CTranslate2 merges PR #1911 and releases a new version that removes the `pkg_resources` dependency, we can:
1. Remove the warning filters from the codebase
2. Update the `faster-whisper` dependency to use the fixed version

## Technical Details

### Why Pinning setuptools Doesn't Work

- setuptools v67.5.0 (April 2023): Initial `DeprecationWarning` introduced for `pkg_resources`
- setuptools v70.0.0 (May 2024): Removed `packaging` module from `pkg_resources`
- setuptools v80.9.0 (current): Enhanced warning message added
- setuptools v81.0.0 (future): `pkg_resources` will be completely removed

Pinning to `setuptools<81` only ensures `pkg_resources` is still available but **does not suppress the warning**.

### Why warnings.filterwarnings() Works

The warning is a `UserWarning` emitted when `pkg_resources` is imported. By adding a filter before the import, we tell Python to ignore warnings matching:
- Category: `UserWarning`
- Message pattern: `"pkg_resources is deprecated"`

This is a safe, targeted suppression that only affects this specific warning.

## References

- [Stack Overflow: pkg_resources is deprecated as an API](https://stackoverflow.com/questions/76043689/pkg-resources-is-deprecated-as-an-api)
- [Python Discussions: Pkg_resources is deprecated warning](https://discuss.python.org/t/pkg-resources-is-deprecated-warning/59517)
- [Python Discussions: How to silence pkg_resources warnings](https://discuss.python.org/t/how-to-silence-pkg-resources-warnings/28629)
- [Stack Overflow: How to disable Python warnings](https://stackoverflow.com/questions/14463277/how-to-disable-python-warnings)
- [Setuptools Documentation on pkg_resources](https://setuptools.pypa.io/en/latest/pkg_resources.html)
- [Python warnings module documentation](https://docs.python.org/3/library/warnings.html)
