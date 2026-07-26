import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

_download_unavailable = set()


def ensure_nltk_punkt(timeout=8):
    import nltk

    for resource in ('punkt', 'punkt_tab'):
        try:
            nltk.data.find(f'tokenizers/{resource}')
            continue
        except LookupError:
            pass

        if resource in _download_unavailable:
            return False

        try:
            subprocess.run(
                [sys.executable, '-c', f"import nltk; nltk.download({resource!r}, quiet=True)"],
                timeout=timeout,
                capture_output=True,
                check=True,
            )
        except Exception:
            logger.exception(
                "Could not download NLTK resource '%s' within %ss; "
                "sentence chunking will fall back to a simple splitter for this process.",
                resource, timeout
            )
            _download_unavailable.add(resource)

            return False

    return True
