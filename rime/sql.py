# This software is released under the terms of the GNU GENERAL PUBLIC LICENSE.
# See LICENSE.txt for full details.
# Copyright 2023 Telemarq Ltd

"""
Thin wrapper around pypika with methods to perform subsetting and helpers in sqlite databases.
"""
import itertools
import re
import sys
from typing import Any, Union

import pypika
import pypika.utils
import pypika.queries
from pypika.terms import Term, Field, Star, Function, ArithmeticExpression
from pypika.queries import QueryException
import sqlite3

Table = pypika.Table
# Query is defined below (we use a custom one)
Column = pypika.Column
Parameter = pypika.Parameter
Connection = sqlite3.Connection


def _sqlite3_regexp_search(pattern, input):
    return bool(re.search(pattern, input))


def sqlite3_connect(db_path, uri=False):
    """
    Connect to an sqlite3 database and add support for regular expression matching.
    If db_path is a file: URI, then set uri=True
    """
    # We current do not, but in future may, support caching connections across threads.
    check_same_thread = False

    if uri is False and db_path.startswith('file:'):
        raise ValueError(f"Supplied a URI-looking db_path of {db_path} but uri is False")

    try:
        conn = sqlite3.connect(db_path, uri=uri, check_same_thread=check_same_thread)
        conn.create_function('REGEXP', 2, _sqlite3_regexp_search)
    except sqlite3.OperationalError as e:
        print(f"Error connecting to database {db_path} (uri={uri}): {e}", file=sys.stderr)
        raise

    return conn


def sqlite3_connect_filename(path, read_only=True):
    if sys.platform == 'win32':
        # If it's an absolute path, we need to add a leading slash to make it a URI
        if re.match(r'^[a-zA-Z]:', path):
            path = '/' + path

        # Also, switch to forward slashes.
        path = path.replace('\\', '/')

    params = "?mode=ro&immutable=1" if read_only else ""
    return sqlite3_connect(f"file://{path}{params}", uri=True)


def get_field_indices(query):
    return {select.alias or select.name: idx for idx, select in enumerate(query._selects)}


# Custom query builder for sqlite supporting RETURNING
class SqliteQuery(pypika.queries.Query):
    @classmethod
    def _builder(cls, **kwargs) -> "SqliteQueryBuilder":
        return SqliteQueryBuilder(**kwargs)


class SqliteQueryBuilder(pypika.queries.QueryBuilder):
    # Most of the following copied from PostgresQueryBuilder in pypika.
    def __init__(self):
        super().__init__()
        self._returns = []
        self._return_star = False

    def _validate_returning_term(self, term: Term) -> None:
        for field in term.fields_():
            if not any([self._insert_table, self._update_table, self._delete_from]):
                raise QueryException("Returning can't be used in this query")

            table_is_insert_or_update_table = field.table in {self._insert_table, self._update_table}
            join_tables = set(itertools.chain.from_iterable([j.criterion.tables_ for j in self._joins]))
            join_and_base_tables = set(self._from) | join_tables
            table_not_base_or_join = bool(term.tables_ - join_and_base_tables)
            if not table_is_insert_or_update_table and table_not_base_or_join:
                raise QueryException("You can't return from other tables")

    @pypika.utils.builder
    def returning(self, *terms: Any) -> "SqliteQueryBuilder":  # type: ignore
        for term in terms:
            if isinstance(term, Field):
                self._return_field(term)
            elif isinstance(term, str):
                self._return_field_str(term)
            elif isinstance(term, (Function, ArithmeticExpression)):
                if term.is_aggregate:
                    raise QueryException("Aggregate functions are not allowed in returning")
                self._return_other(term)
            else:
                self._return_other(self.wrap_constant(term, self._wrapper_cls))

    def _return_other(self, function: Term) -> None:
        self._validate_returning_term(function)
        self._returns.append(function)

    def _return_field(self, term: Union[str, Field]) -> None:
        if self._return_star:
            # Do not add select terms after a star is selected
            return

        self._validate_returning_term(term)

        if isinstance(term, Star):
            self._set_returns_for_star()

        self._returns.append(term)

    def _return_field_str(self, term: Union[str, Field]) -> None:
        if term == "*":
            self._set_returns_for_star()
            self._returns.append(Star())
            return

        if self._insert_table:
            self._return_field(Field(term, table=self._insert_table))
        elif self._update_table:
            self._return_field(Field(term, table=self._update_table))
        elif self._delete_from:
            self._return_field(Field(term, table=self._from[0]))
        else:
            raise QueryException("Returning can't be used in this query")

    def _returning_sql(self, **kwargs: Any) -> str:
        return " RETURNING {returning}".format(
            returning=",".join(term.get_sql(with_alias=True, **kwargs) for term in self._returns),
        )

    def get_sql(self, with_alias: bool = False, subquery: bool = False, **kwargs: Any) -> str:
        self._set_kwargs_defaults(kwargs)

        querystring = super().get_sql(with_alias, subquery, **kwargs)

        if self._returns:
            kwargs['with_namespace'] = self._update_table and self.from_
            querystring += self._returning_sql(**kwargs)

        return querystring


Query = SqliteQuery
