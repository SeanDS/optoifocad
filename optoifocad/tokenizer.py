"""Tokenizer for Optocad script."""

import re
from io import StringIO
from dataclasses import dataclass
from typing import Any
from .tokens import (
    NEWLINE,
    COMMENT,
    NAME,
    NUMBER,
    STRING,
    LITERALS,
)
from .exceptions import OptocadSyntaxError


@dataclass
class Token:
    lineno: int
    start_index: int
    stop_index: int
    type: Any
    value: Any = None


class OptocadTokenizer:
    """Optocad token generator.

    Regular expressions define patterns to match prototypes. Prototypes are then either
    emitted as tokens as-is, or modified by callback methods defined in this class.
    """

    _TAB_SIZE = 4

    # All token rules, in order of matching precedence.
    _TOKEN_RULES = {
        "NEWLINE": NEWLINE,
        "COMMENT": COMMENT,
        "NUMBER": NUMBER,  # Has to be above NAME (since it can match "inf")
        "STRING": STRING,
        "NAME": NAME,
        **{key: re.escape(value) for key, value in LITERALS.items()},
    }

    _IGNORE = " \t"

    def __init__(self):
        self.done = None
        self.script = None
        self._filename = None
        self._lineno = None
        self._index = None
        self._matcher = None
        self._nesting = None
        self._build_rules()

    def _build_rules(self):
        """Create overall expression with named items."""
        rules = "|".join(
            [f"(?P<{name}>{pattern})" for name, pattern in self._TOKEN_RULES.items()]
        )
        self._matcher = re.compile(rules)

    def _raise_error(self, error_msg, token):
        raise OptocadSyntaxError(
            error_msg,
            self._filename,
            token.lineno,
            token.start_index,
            token.value,
            token.lineno,
            token.stop_index
        )

    def _raise_lexing_error(self, token):
        self._raise_error(f"illegal character {repr(token.value[0])}", token)

    def tokenize(self, string):
        """Tokenize specified `string`.

        Parameters
        ----------
        string : :class:`str`
            The string to tokenize Optocad script from.

        Yields
        ------
        :class:`.Token`
            The next token read from `string`.
        """
        yield from self.tokenize_file(StringIO(string))

    def tokenize_file(self, fobj):
        """Generate tokens from the given file.

        Parameters
        ----------
        fobj : :class:`io.FileIO`
            The file object to tokenize Optocad script from. This should be opened in
            text mode.

        Yields
        ------
        :class:`.Token`
            The next token read from `fobj`.
        """
        # Reset tokenizer state.
        self.done = False
        self._filename = fobj.name
        self.errors = []
        self.script = []
        self._nesting = []
        self._lineno = 1
        self._index = 0
        previous_line = ""
        line = ""

        while True:
            previous_line = line
            line = fobj.readline()

            # Lines are only empty at the end of the file (blank lines are "\n").
            if not line:
                break

            linelength = len(line)
            # Store the line for use in error messages.
            self.script.append(line)

            # The current string index on the current line. The start/stop values stored
            # in tokens are this value + 1.
            # This can be modified by the error function, so it's part of the object
            # scope. We also remember the total extra space characters used to
            # compensate for tabs, which only take up 1 character in the file but more
            # when displayed.
            self._index = 0
            self._taboffset = 0

            while self._index < linelength:
                if line[self._index] in self._IGNORE:
                    self._index += 1
                    continue

                matches = self._matcher.match(line, self._index)

                if matches:
                    value = matches.group()

                    # Compensate for tabs. Tabs only take up one character but when
                    # displayed take up whatever we decide here.
                    start_index = self._index + self._taboffset + 1
                    self._taboffset += (self._TAB_SIZE - 1) * value.count("\t")
                    stop_index = matches.end() + self._taboffset + 1

                    token_type = matches.lastgroup

                    try:
                        token = Token(
                            lineno=self._lineno,
                            start_index=start_index,
                            stop_index=stop_index,
                            type=token_type,
                            value=value,
                        )
                    except SyntaxError as e:
                        # There was an error determining the final value of the token.
                        self._raise_error(
                            e,
                            Token(
                                self._lineno,
                                start_index,
                                stop_index,
                                token_type,
                                value,
                            ),
                        )

                    if token_callback := getattr(self, f"on_{token_type}", False):
                        token_callback(token)

                    self._index = matches.end()  # Updates index for next token.
                else:
                    # A lexing error.
                    token = Token(
                        self._lineno,
                        start_index=self._index + 1,
                        stop_index=linelength + 1,
                        type="ERROR",
                        value=line[self._index :],
                    )
                    # Leave it to the error function to advance the index and/or recover
                    # the token.
                    token = self._raise_lexing_error(token)

                yield token

        if self._nesting:
            # Unclosed parenthesis/parentheses.
            for token in self._nesting:
                self._raise_error(f"unclosed '{token.value}'", token)

        # Add an implicit NEWLINE if the input doesn't end in one (this simplifies the
        # parser rules).
        if not previous_line or (previous_line and previous_line[-1] not in "\r\n"):
            yield Token(
                self._lineno, self._index + 1, self._index + 1, "NEWLINE"
            )
            self._lineno += 1
            self._index = 0

        yield Token(self._lineno, 1, 1, "ENDMARKER")
        self.done = True

    def on_NEWLINE(self, token):
        self._lineno += len(token.value)

    def on_LBRACKET(self, token):
        self._nesting.append(token)

    def on_RBRACKET(self, token):
        try:
            assert self._nesting.pop().value == "["
        except (IndexError, AssertionError):
            self._raise_error("extraneous ']'", token)

    def on_LPAREN(self, token):
        self._nesting.append(token)

    def on_RPAREN(self, token):
        try:
            assert self._nesting.pop().value == "("
        except (IndexError, AssertionError):
            self._raise_error("extraneous ')'", token)
