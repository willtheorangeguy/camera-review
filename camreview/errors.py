class CamReviewError(Exception):
    """Base class for expected application errors."""


class ConfigurationError(CamReviewError):
    """A command-line or configuration value is invalid."""


class NoRecordingsError(CamReviewError):
    """No matching recordings were found."""


class StrictRecordingError(CamReviewError):
    """A recording failed while strict mode was active."""


class DetectorUnavailableError(CamReviewError):
    """The requested object detector or accelerator is unavailable."""


class ExtractionError(CamReviewError):
    """An extraction operation failed."""
