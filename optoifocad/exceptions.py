"""Exceptions."""

class OptocadSyntaxError(SyntaxError):
    """Error with Optocad syntax."""
    def __init__(
        self, message, filename, lineno, index, text, end_lineno=None, end_index=None
    ):
        try:
            super().__init__(
                message, (filename, lineno, index, text, end_lineno, end_index)
            )
        except IndexError:
            # Python < 3.10
            super().__init__(
                message, (filename, lineno, index, text)
            )
