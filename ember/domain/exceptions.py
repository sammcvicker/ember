"""Domain exceptions for Ember business logic.

These exceptions represent business rule violations and domain-level errors.
They should be caught at the application boundary (CLI, API) and converted
to appropriate user-facing error messages.
"""


class EmberDomainError(Exception):
    """Base exception for all domain errors.

    Attributes:
        message: User-facing error message.
        hint: Optional actionable suggestion.
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class PathNotInRepositoryError(EmberDomainError):
    """Raised when a path is outside the repository boundaries."""

    pass


class ConflictingFiltersError(EmberDomainError):
    """Raised when mutually exclusive filter options are provided."""

    pass
