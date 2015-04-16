#  Copyright 2007-2014 University Of Southern California
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

__author__ = 'Rajiv Mayani'

import StringIO

from plex import Range, Lexicon, Rep, Rep1, Str, Any, IGNORE, Scanner, State, Begin, AnyBut, NoCase, Opt
from plex.errors import UnrecognizedInput


class BaseSerializer(object):
    """
    Base Serializer class provides a template used to serialize objects to/from JSON
    """

    def __init__(self, fields, pretty_print=False):
        self._fields = fields

        self._pretty_print = pretty_print

        if self._pretty_print is True:
            self._pretty_print_opts = {
                'indent': 4,
                'separators': (',', ': ')
            }
        else:
            self._pretty_print_opts = {}

    def encode_collection(self, records, records_total, records_filtered):
        raise NotImplementedError('Method not implemented')

    def encode_record(self, record):
        raise NotImplementedError('Method not implemented')

    def decode_collection(self, records):
        raise NotImplementedError('Method not implemented')

    def decode_record(self, record):
        raise NotImplementedError('Method not implemented')

    def _links(self, record):
        raise NotImplementedError('Method not implemented')


class ServiceError(Exception):
    pass


class InvalidQueryError(ServiceError):
    pass


class InvalidOrderError(ServiceError):
    pass


class BaseQueryParser(object):
    """
    Base Query Parser class provides a basic implementation to parse the `query` argument
    i.e. Basic WHERE clause as used in SQL.

    Note: The base class only provides a partial implementation of the SQL where clause.
    """
    whitespace = Rep1(Any(' \t\n'))
    open_parenthesis = Str('(')
    close_parenthesis = Str(')')

    letter = Range('AZaz')
    digit = Range('09')
    prefix = letter + Rep(letter) + Str('.')

    reserved_word = NoCase(Str('AND', 'OR', 'LIKE')) | Str('NULL')

    identifier = Opt(prefix) + letter + Rep(letter | digit | Str('_'))
    comparators = NoCase(Str('=', '!=', 'like'))
    integer_literal = Rep1(digit)
    string_literal = Str('\'') + Rep(AnyBut('\'') | Str(' ') | Str("\\'")) + Str('\'')

    operands = NoCase(Str('AND', 'OR'))
    null = Str('NULL')

    OPEN_PARENTHESIS = 1
    CLOSE_PARENTHESIS = 2
    NULL = 3
    OPERAND = 4
    IDENTIFIER = 5
    COMPARATOR = 7
    INTEGER_LITERAL = 8
    STRING_LITERAL = 9

    lexicon = Lexicon([
        (whitespace, IGNORE),
        (open_parenthesis, OPEN_PARENTHESIS),
        (close_parenthesis, CLOSE_PARENTHESIS),
        (null, NULL),
        (operands, OPERAND),
        (comparators, COMPARATOR),
        (integer_literal, INTEGER_LITERAL),
        (string_literal, STRING_LITERAL),
        (identifier, IDENTIFIER)
    ])

    def __init__(self, expression):
        self.expression = expression

        self._state = 0
        self._parenthesis_count = 0

        self._operator_stack = []
        self._postfix_result = []
        self._condition = [0, 0, 0]

        self._scanner = None

        try:
            self._parse_expression()
        except UnrecognizedInput, e:
            raise InvalidQueryError(str(e))

    def _parse_expression(self):
        """
        Uses postfix evaluation of filter string.
        http://www.sunshine2k.de/coding/java/SimpleParser/SimpleParser.html
        """

        f = StringIO.StringIO(self.expression)
        self._scanner = Scanner(self.lexicon, f, 'query')

        while 1:
            token = self._scanner.read()

            if token[0] in self.mapper:
                self.mapper[token[0]](self, token[1])

            elif token[0] is None:
                break

        if self._parenthesis_count != 0:
            raise InvalidQueryError('Invalid parenthesis count')

        while len(self._operator_stack) > 0:
            self._postfix_result.append(self._operator_stack.pop())

        f.close()

    def open_parenthesis_handler(self, text):
        self._parenthesis_count += 1
        self._operator_stack.append('(')

    def close_parenthesis_handler(self, text):
        if self._parenthesis_count <= 0:
            file, line, char_pos = self._scanner.position()
            msg = 'Invalid parenthesis order: Line: %d Char: %d' % (line, char_pos)
            raise InvalidQueryError(msg)
        else:
            self._parenthesis_count -= 1

        while len(self._operator_stack) > 0:
            operator = self._operator_stack.pop()

            if operator == '(':
                break
            else:
                self._postfix_result.append(operator)

    def identifier_handler(self, text):
        if self._state == 0:
            self._condition[0] = text
            self._state = 1
        else:
            file, line, char_pos = self._scanner.position()
            msg = 'Field %r found out of order: Line: %d Char: %d' % (text, line, char_pos)
            raise InvalidQueryError(msg)

    def comparator_handler(self, text):
        if self._state == 1:
            self._condition[1] = text.upper()
            self._state = 2
        else:
            file, line, char_pos = self._scanner.position()
            msg = 'Comparator %r found out of order: Line: %d Char: %d' % (text, line, char_pos)
            raise InvalidQueryError(msg)

    def integer_literal_handler(self, text):
        if self._state == 2:
            self._condition[2] = text.strip()
            self._postfix_result.append(tuple(self._condition))
            self._state = 0
        else:
            file, line, char_pos = self._scanner.position()
            msg = 'Integer literal %d found out of order: Line: %d Char: %d' % (text, line, char_pos)
            raise InvalidQueryError(msg)

    def string_literal_handler(self, text):
        if self._state == 2:
            self._condition[2] = text.strip("'")
            self._postfix_result.append(tuple(self._condition))
            self._state = 0
        else:
            file, line, char_pos = self._scanner.position()
            msg = 'String literal %r found out of order: Line: %d Char: %d' % (text, line, char_pos)
            raise InvalidQueryError(msg)

    def null_handler(self, text):
        if self._state == 2:
            self._condition[2] = None
            self._postfix_result.append(tuple(self._condition))
            self._state = 0
        else:
            file, line, char_pos = self._scanner.position()
            msg = 'NULL found out of order: Line: %d Char: %d' % (line, char_pos)
            raise InvalidQueryError(msg)

    def operand_handler(self, text):
        self._operator_stack.append(text.upper())

    mapper = {
        OPEN_PARENTHESIS: open_parenthesis_handler,
        CLOSE_PARENTHESIS: close_parenthesis_handler,
        IDENTIFIER: identifier_handler,
        COMPARATOR: comparator_handler,
        INTEGER_LITERAL: integer_literal_handler,
        STRING_LITERAL: string_literal_handler,
        NULL: null_handler,
        OPERAND: operand_handler
    }

    def evaluate(self):
        return self._postfix_result

    def __str__(self):
        s = StringIO.StringIO()

        for i in self._postfix_result:
            s.write(str(i))
            s.write(' ')

        out = s.getvalue()
        s.close()

        return out


class BaseOrderParser(object):
    """
    Base Order Parser class provides a basic implementation to parse the `order` argument
    i.e. ORDER clause as used in SQL.
    """
    whitespace = Rep1(Any(' \t\n'))

    letter = Range('AZaz')
    digit = Range('09')

    prefix = letter + Rep(letter) + Str('.')
    identifier = Opt(prefix) + letter + Rep(letter | digit | Str('_'))

    order = NoCase(Str('ASC', 'DESC'))

    order_clause = identifier + Opt(Rep1(whitespace) + order)
    separator = Str(',')

    ORDER_CLAUSE = 1
    SEPARATOR = 2

    lexicon = Lexicon([
        (whitespace, IGNORE),
        (order_clause, ORDER_CLAUSE),
        (separator, SEPARATOR)
    ])

    def __init__(self, expression):
        self.expression = expression

        self._state = 0
        self._sort_order = []

        self._scanner = None

        try:
            self._parse_expression()
        except UnrecognizedInput, e:
            raise InvalidOrderError(str(e))

    def _parse_expression(self):
        f = StringIO.StringIO(self.expression)
        self._scanner = Scanner(self.lexicon, f, 'order')

        while 1:
            token = self._scanner.read()

            if token[0] in self.mapper:
                self.mapper[token[0]](self, token[1])

            elif token[0] is None:
                break

        self._sort_order = [tuple(order_clause) for order_clause in self._sort_order]

        f.close()

    def order_clause_handler(self, order_clause):
        order_clause = order_clause.strip().split()

        self.identifier_handler(order_clause[0])

        if len(order_clause) == 2:
            self.order_handler(order_clause[1])

    def identifier_handler(self, identifier):
        if self._state == 0:
            self._state = 1
            self._sort_order.append([identifier, 'ASC'])

        else:
            raise InvalidOrderError('Identifier %r found out of order' % identifier)

    def order_handler(self, order):
        if self._state == 1 and order.upper() in set(['ASC', 'DESC']):
            self._state = 2
            self._sort_order[len(self._sort_order) - 1][1] = order.upper()

        else:
            raise InvalidOrderError('Sorting order %r found out of order' % order)

    def separator_handler(self, separator):
        if self._state == 1 or self._state == 2:
            self._state = 0

        else:
            raise InvalidOrderError('Separator %r found out of order' % separator)

    mapper = {
        ORDER_CLAUSE: order_clause_handler,
        SEPARATOR: separator_handler
    }

    def get_sort_order(self):
        return self._sort_order

    def __str__(self):
        s = StringIO.StringIO()

        for i in self._sort_order:
            s.write(str(i))
            s.write(' ')

        out = s.getvalue()
        s.close()

        return out