"""Abstract base class for all translation backends."""


class TranslationBackend:
    """All backends must implement translate() and is_available()."""

    name: str = ""

    async def translate(
        self,
        text: str,
        source: str = "ja",
        target: str = "en",
    ) -> str:
        """Translate text from source language to target language.

        Returns translated string, or empty string on failure.
        Must never raise — catch all exceptions internally.
        """
        raise NotImplementedError

    async def is_available(self) -> bool:
        """Return True if this backend is reachable and functional.

        Must never raise — return False on any error.
        """
        raise NotImplementedError
