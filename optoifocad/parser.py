"""Optocad parser."""

# NOTE: do not run black on this file!

import logging
from io import StringIO
from .tokenizer import OptocadTokenizer
from .memoize import memoize, memoize_left_rec
from .containers import (
    OptocadScript,
    OptocadCommand,
    OptocadSecondarySurfaceCommand,
    OptocadUnaryExpression,
    OptocadBinaryExpression
)
from .exceptions import OptocadSyntaxError

LOGGER = logging.getLogger(__name__)


class __empty_cls:
    """Internal class representing an empty line."""

EMPTY = __empty_cls()


class OptocadParser:
    """Optocad script parser.

    This uses so-called *packrat* parsing to reduce, via productions, tokens yielded
    from a token stream generated from an input file or string to
    :class:`.OptocadScriptItem` objects containing the associated :class:`tokens
    <.Token>`.
    """

    def __init__(self):
        self.tokens = None
        self.pos = None
        self.memos = None
        self.optocad_script = None
        self._filename = None
        self._tokenizer = None
        self._token_stream = None

    @property
    def script(self):
        return self._tokenizer.script

    def parse(self, string):
        """Parse the contents of `string`.

        Parameters
        ----------
        string : :class:`str`
            The string to parse Optocad script from.

        Returns
        -------
        :class:`.OptocadScript`
            The parsed Optocad script.
        """
        return self.parse_file(StringIO(string))

    def parse_file(self, fobj):
        """Parse the contents of the specified file.

        Parameters
        ----------
        fobj : :class:`io.FileIO`
            The file object to parse Optocad script from. This should be opened in text
            mode.

        Returns
        -------
        :class:`.OptocadScript`
            The parsed Optocad script.
        """
        # Reset parser state.
        self.tokens = []
        self.pos = 0
        self.memos = {}
        self.optocad_script = OptocadScript()
        self._filename = fobj.name
        self._log_stack = []

        # Perform parse.
        self._tokenizer = OptocadTokenizer()
        self._token_stream = self._tokenizer.tokenize_file(fobj)

        if (script := self.expect_production("start")) is not None:
            return script

        # There was an error.
        self._diagnose_error()

    def _diagnose_error(self):
        if not self.tokens:
            error_token = self.peek_token()
        else:
            error_token = self.tokens[-1]

        raise OptocadSyntaxError(
            "syntax error",
            self._filename,
            error_token.lineno,
            error_token.start_index,
            error_token.value,
            error_token.lineno,
            error_token.stop_index
        )

    def mark(self):
        return self.pos

    def reset(self, pos):
        if pos == self.pos:
            return
        self.pos = pos

    def get_token(self):
        token = self.peek_token()
        self.pos += 1
        return token

    def peek_token(self):
        if self.pos == len(self.tokens):
            self.tokens.append(next(self._token_stream))
        return self.tokens[self.pos]

    def positive_lookahead(self, token_type):
        pos = self.mark()
        token = self.peek_token()
        self.reset(pos)
        return token.type == token_type

    def negative_lookahead(self, token_type):
        return not self.positive_lookahead(token_type)

    def maybe_token(self, token_type):
        pos = self.mark()
        if (
            True
            and (TOKEN := self.expect_token(token_type)) is not None
        ):
            return TOKEN
        self.reset(pos)
        return EMPTY

    def maybe_trailing_comma(self):
        pos = self.mark()
        if (
            True
            and (COMMA := self.expect_token("COMMA")) is not None
            and (self.positive_lookahead("NEWLINE") or self.positive_lookahead("COMMENT"))
        ):
            return COMMA
        self.reset(pos)
        return EMPTY

    @memoize
    def expect_token(self, arg):
        self._log_stack.append(arg)
        path = "->".join(self._log_stack)
        # path = arg
        LOGGER.debug(f"{path}?")
        token = self.peek_token()

        if token.type == arg:
            LOGGER.debug(f"{path} = {token!r}!")
            result = self.get_token()
            self._log_stack.pop()
            return result

        LOGGER.debug(f"{arg} not found")
        self._log_stack.pop()

    def expect_production(self, production):
        self._log_stack.append(production)
        path = "->".join(self._log_stack)
        # path = production
        LOGGER.debug(f"{path}?")

        result = getattr(self, production)()

        if result is not None:
            LOGGER.debug(f"{path} = {result!r}!")
            self._log_stack.pop()
            return result

        LOGGER.debug(f"{production} not found")
        self._log_stack.pop()

    def loop_token(self, token, nonempty):
        mark = self.mark()
        nodes = []
        while (node := self.expect_token(token)) is not None:
            nodes.append(node)
        if len(nodes) >= nonempty:
            return nodes
        self.reset(mark)

    def loop_production(self, production, nonempty):
        mark = self.mark()
        nodes = []
        while (node := self.expect_production(production)) is not None:
            nodes.append(node)
        if len(nodes) >= nonempty:
            return nodes
        self.reset(mark)

    def start(self):
        pos = self.mark()

        if (
            True
            and self.loop_production("script_line", False) is not None
            and self.expect_token("ENDMARKER") is not None
        ):
            return self.optocad_script

        self.reset(pos)

    @memoize
    def script_line(self):
        pos = self.mark()

        # script_line -> command COMMENT? NEWLINE
        if (
            True
            and (command := self.expect_production("command")) is not None
            and self.maybe_token("COMMENT") is not None
            and self.expect_token("NEWLINE") is not None
        ):
            if isinstance(command, OptocadSecondarySurfaceCommand):
                # Append to previous command.
                try:
                    self.optocad_script[-1].secondary_surfaces.append(command)
                except IndexError:
                    raise OptocadSyntaxError(
                        "secondary surface missing primary surface",
                        (
                            self._filename,
                            self._tokenizer.lineno,
                            self._tokenizer.index,
                            None
                        )
                    )
            else:
                self.optocad_script.append(command)

            return command

        self.reset(pos)

        # script_line -> COMMENT? NEWLINE
        if (
            True
            and self.maybe_token("COMMENT") is not None
            and self.expect_token("NEWLINE") is not None
        ):
            return EMPTY

        self.reset(pos)

    @memoize
    def command(self):
        pos = self.mark()

        # command -> NAME command_params
        if (
            True
            and (COMMAND := self.expect_token("NAME")) is not None
            and (command_params := self.expect_production("command_params")) is not None
        ):
            args, kwargs = command_params
            return OptocadCommand(directive=COMMAND.value, args=args, kwargs=kwargs)

        self.reset(pos)

        # command -> PLUS command_params
        if (
            True
            and self.expect_token("PLUS") is not None
            and (command_params := self.expect_production("command_params")) is not None
        ):
            args, kwargs = command_params
            return OptocadSecondarySurfaceCommand(args=args, kwargs=kwargs)

        self.reset(pos)

    @memoize
    def command_params(self):
        pos = self.mark()

        # command_params -> command_value_list ',' command_key_value_list ','?
        if (
            True
            and (command_value_list := self.expect_production("command_value_list")) is not None
            and self.expect_token("COMMA") is not None
            and (command_key_value_list := self.expect_production("command_key_value_list")) is not None
            and self.maybe_trailing_comma() is not None
        ):
            return command_value_list, command_key_value_list

        self.reset(pos)

        # command_params -> command_value_list ','?
        if (
            True
            and (command_value_list := self.expect_production("command_value_list")) is not None
            and self.maybe_trailing_comma() is not None
        ):
            return command_value_list, {}

        self.reset(pos)

        # command_params -> command_key_value_list ','?
        if (
            True
            and (command_key_value_list := self.expect_production("command_key_value_list")) is not None
            and self.maybe_trailing_comma() is not None
        ):
            return [], command_key_value_list

        self.reset(pos)

    @memoize
    def command_value_list(self):
        pos = self.mark()

        # command_value_list -> positional_value ',' command_value_list
        if (
            True
            and (positional_value := self.expect_production("positional_value")) is not None
            and self.expect_token("COMMA") is not None
            and (command_value_list := self.expect_production("command_value_list")) is not None
        ):
            return [positional_value, *command_value_list]

        self.reset(pos)

        # command_value_list -> positional_value
        if (positional_value := self.expect_production("positional_value")) is not None:
            return [positional_value]

        self.reset(pos)

    @memoize_left_rec
    def command_key_value_list(self):
        pos = self.mark()

        # command_key_value_list -> command_key_value_list ',' command_key_value_list
        if (
            True
            and (command_key_value_list1 := self.expect_production("command_key_value_list")) is not None
            and self.loop_token("COMMA", True) is not None
            and (command_key_value_list2 := self.expect_production("command_key_value_list")) is not None
        ):
            return {**command_key_value_list1, **command_key_value_list2}

        self.reset(pos)

        # command_key_value_list -> key_value
        if (key_value := self.expect_production("key_value")) is not None:
            return key_value

        self.reset(pos)

    @memoize
    def positional_value(self):
        pos = self.mark()

        # Don't match values followed by '=', which are kwarg keys.
        if (
            True
            and (value := self.expect_production("value")) is not None
            and self.negative_lookahead("EQUALS")
        ):
            return value

        self.reset(pos)

    @memoize
    def value(self):
        pos = self.mark()

        # value -> action
        if (action := self.expect_production("action")) is not None:
            return action

        self.reset(pos)

        # value -> expr
        if (expr := self.expect_production("expr")) is not None:
            return expr

        self.reset(pos)

    @memoize
    def key_value(self):
        pos = self.mark()

        # key_value -> NAME '=' value
        if (
            True
            and (NAME := self.expect_token("NAME")) is not None
            and self.expect_token("EQUALS") is not None
            and (value := self.expect_production("value")) is not None
        ):
            return {NAME.value: value}

        self.reset(pos)

        if (
            True
            and (NAME := self.expect_token("NAME")) is not None
            and (EQUALS := self.expect_token("EQUALS")) is not None
            and self.expect_production("value") is None  # !
        ):
            raise OptocadSyntaxError(
                "missing value",
                (
                    self._filename,
                    self._tokenizer.lineno,
                    self._tokenizer.index,
                    EQUALS.value
                )
            )

        self.reset(pos)

    @memoize_left_rec
    def action(self):
        pos = self.mark()

        # action -> action action
        if (
            True
            and (action1 := self.expect_production("action")) is not None
            and (action2 := self.expect_production("action")) is not None
        ):
            return action1 + action2

        self.reset(pos)

        # action -> '{' action '}' NUMBER?
        if (
            True
            and self.expect_token("LBRACE") is not None
            and (action := self.expect_production("action")) is not None
            and self.expect_token("RBRACE") is not None
            and (NUMBER := self.maybe_token("NUMBER")) is not None
        ):
            try:
                if NUMBER is not None and NUMBER is not EMPTY:
                    NUMBER = int(NUMBER.value)
            except ValueError:
                # Not an integer.
                pass
            else:
                if NUMBER is None or NUMBER is EMPTY:
                    NUMBER = ""

                return "{" + action + "}" + NUMBER

        self.reset(pos)

        # action -> '[' action ']'
        if (
            True
            and self.expect_token("LBRACKET") is not None
            and (action := self.expect_production("action")) is not None
            and self.expect_token("RBRACKET") is not None
        ):
            return "[" + action + "]"

        self.reset(pos)

        # action -> '(' action ')'
        if (
            True
            and self.expect_token("LPAREN") is not None
            and (action := self.expect_production("action")) is not None
            and self.expect_token("RPAREN") is not None
        ):
            return "(" + action + ")"

        self.reset(pos)

        # action -> ('c' | 'd' | 'h' | 'i' | 'n' | 'r' | 's' | 't' | 'v')+
        if (
            True
            and (NAME := self.expect_token("NAME")) is not None
        ):
            if set(NAME.value) <= set("cdhinrstv"):
                return NAME.value

        self.reset(pos)

    @memoize_left_rec
    def expr(self):
        pos = self.mark()

        # NOTE: operator precedence is set by defining productions within productions.
        # expr -> expr ( '+' / '-' ) expr1
        for operator in ("PLUS", "MINUS"):
            if (
                True
                and (lhs := self.expect_production("expr")) is not None
                and (operator := self.expect_token(operator)) is not None
                and (rhs := self.expect_production("expr1")) is not None
            ):
                return OptocadBinaryExpression(
                    operator=operator.value, lhs=lhs, rhs=rhs
                )

            self.reset(pos)

        # expr -> expr1
        if (expr1 := self.expect_production("expr1")) is not None:
            return expr1

        self.reset(pos)

    @memoize_left_rec
    def expr1(self):
        """Times, divide and floordivide operators."""
        pos = self.mark()

        # expr1 -> expr1 ( '*' / '/' / '//' ) expr2
        for operator in ("TIMES", "DIVIDE", "FLOORDIVIDE"):
            if (
                True
                and (lhs := self.expect_production("expr1")) is not None
                and (operator := self.expect_token(operator)) is not None
                and (rhs := self.expect_production("expr2")) is not None
            ):
                return OptocadBinaryExpression(
                    operator=operator.value, lhs=lhs, rhs=rhs
                )

            self.reset(pos)

        # expr1 -> expr2
        if (expr2 := self.expect_production("expr2")) is not None:
            return expr2

        self.reset(pos)

    @memoize
    def expr2(self):
        """Unary operators."""
        pos = self.mark()

        # expr2 -> ( '+' / '-' ) expr2
        for unary_operator in ("PLUS", "MINUS"):
            if (
                True
                and (operator := self.expect_token(unary_operator)) is not None
                and (expr2 := self.expect_production("expr2")) is not None
            ):
                return OptocadUnaryExpression(operator=operator.value, argument=expr2)

            self.reset(pos)

        # expr2 -> expr3
        if (expr3 := self.expect_production("expr3")) is not None:
            return expr3

        self.reset(pos)

    @memoize
    def expr3(self):
        """Power operator."""
        pos = self.mark()

        # expr3 -> expr4 '**' expr2
        if (
            True
            and (expr4 := self.expect_production("expr4")) is not None
            and (power := self.expect_token("POWER")) is not None
            and (expr2 := self.expect_production("expr2")) is not None
        ):
            return OptocadBinaryExpression(operator=power.value, lhs=expr4, rhs=expr2)

        self.reset(pos)

        # expr3 -> expr4
        if (expr4 := self.expect_production("expr4")) is not None:
            return expr4

        self.reset(pos)

    @memoize
    def expr4(self):
        """Parentheses, references, names and numbers.

        Names are allowed here to support keywords and copy-/read-by-value parameters
        like l1.P.
        """
        pos = self.mark()

        # expr4 -> '(' expr ')'
        if (
            True
            and self.expect_token("LPAREN") is not None
            and (expr := self.expect_production("expr")) is not None
            and self.expect_token("RPAREN") is not None
        ):
            return expr

        self.reset(pos)

        # expr4 -> NUMBER
        # Disallow matching of subsequent numbers, which indicates the tokenizer failed
        # to group two numbers together, and therefore a syntax error (handled later).
        if (
            True
            and (TOKEN := self.expect_token("NUMBER")) is not None
            and self.negative_lookahead("NUMBER")
        ):
            return TOKEN.value

        self.reset(pos)

        if (error := self.expect_production("invalid_expr4")) is not None:
            raise error

        self.reset(pos)

    @memoize
    def invalid_expr4(self):
        pos = self.mark()

        # Invalid number: two numbers tokenized in a row, indicating a failure to match
        # the number with the tokenizer's regex.
        if (
            True
            and (NUMBER1 := self.expect_token("NUMBER"))
            and (NUMBER2 := self.expect_token("NUMBER"))
        ):
            if isinstance(NUMBER1.value, int) and isinstance(NUMBER2.value, int):
                # Leading zeros (as per the to-number operation of the IBM
                # specification; same behaviour as Python itself, see
                # https://docs.python.org/3/library/decimal.html).
                return OptocadSyntaxError(
                    "leading zeros in integers are not permitted", self.script, NUMBER1
                )

            # Some other run-together, e.g. `0.1.1`.
            return OptocadSyntaxError("invalid number syntax", self.script, NUMBER2)

        self.reset(pos)
