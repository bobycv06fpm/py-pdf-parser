from typing import TYPE_CHECKING, Any, List, Dict, Optional

from itertools import chain

from .exceptions import (
    TableExtractionError,
    NoElementFoundError,
    InvalidTableError,
    InvalidTableHeaderError,
)

if TYPE_CHECKING:
    from .filtering import ElementList
    from .components import PDFElement


def extract_simple_table(elements: "ElementList") -> List[List[Optional["PDFElement"]]]:
    """
    Returns elements structured as a table.

    Given an ElementList, tries to extract a structured table by examining which
    elements are aligned. To use this function, the table must contain no gaps, i.e.
    should be a full N x M table with an element in each cell. There must be a clear
    gap between each row and between each column which contains no elements, and
    a single cell cannot contian multiple elements.

    If your table has empty cells, you can use `extract_table` instead. If you fail
    to satisfy any of the other conditions listed above, that case is not yet supported.

    Returns a list of rows, which are lists of PDFElements.
    """
    first_row = elements.to_the_right_of(elements[0], inclusive=True)
    first_column = elements.below(elements[0], inclusive=True)

    table: List[List[Optional["PDFElement"]]] = []
    for left_hand_element in first_column:
        row: List[Optional["PDFElement"]] = []
        for top_element in first_row:
            element = elements.to_the_right_of(left_hand_element, inclusive=True).below(
                top_element, inclusive=True
            )
            try:
                row.append(element.extract_single_element())
            except NoElementFoundError:
                row.append(None)
        table.append(row)

    table_size = sum(len(row) for row in table)
    if table_size != len(elements):
        raise TableExtractionError(
            f"Number of elements in table ({table_size}) does not match number of "
            f"elements passed {len(elements)}. Perhaps try extract_table instead of "
            "extract_simple_table."
        )

    _validate_table_shape(table)
    return table


def extract_table(elements: "ElementList") -> List[List[Optional["PDFElement"]]]:
    """
    Returns elements structured as a table.

    Given an ElementList, tries to extract a structured table by examining which
    elements are aligned. There must be a clear gap between each row and between each
    column which contains no elements, and a single cell cannot contian multiple
    elements.

    If you fail to satisfy any of the other conditions listed above, that case is not
    yet supported.

    Returns a list of rows, which are lists of PDFElements.
    """
    table = []
    rows = set()
    cols = set()
    for element in elements:
        row = elements.horizontally_in_line_with(element, inclusive=True)
        rows.add(row)
        col = elements.vertically_in_line_with(element, inclusive=True)
        cols.add(col)

    # Check no element is in multiple rows or columns
    if sum([len(row) for row in rows]) != len(set(chain.from_iterable(rows))):
        raise TableExtractionError("An element is in multiple rows")
    if sum([len(col) for col in cols]) != len(set(chain.from_iterable(cols))):
        raise TableExtractionError("An element is in multiple columns")

    sorted_rows = sorted(
        rows, key=lambda row: min([elem.bounding_box.y0 for elem in row]), reverse=True
    )
    sorted_cols = sorted(
        cols, key=lambda col: min([elem.bounding_box.x0 for elem in col])
    )

    for row in sorted_rows:
        table_row = []
        for col in sorted_cols:
            try:
                element = (row & col).extract_single_element()
            except NoElementFoundError:
                element = None
            table_row.append(element)
        table.append(table_row)

    _validate_table_shape(table)
    return table


def extract_text_from_simple_table(elements: "ElementList") -> List[List[str]]:
    """
    Given an ElementList, extracts a simple table (see `extract_simple_table`), but
    instead of the table containing PDFElements, it will extract the text from each
    element.
    """
    return _extract_text_from_table(extract_simple_table(elements))


def extract_text_from_table(elements: "ElementList") -> List[List[str]]:
    """
    Given an ElementList, extracts a simple table (see `extract_table`), but instead of
    the table containing PDFElements, it will extract the text from each element.
    """
    return _extract_text_from_table(extract_table(elements))


def add_header_to_table(
    table: List[List[str]], header: Optional[List[str]] = None
) -> List[Dict[str, str]]:
    """
    Given a table (list of lists) of strings, returns a list of dicts mapping the
    table header to the values.

    Given a table, a list of rows which are lists of strings, returns a new table
    which is a list of rows which are dictionaries mapping the header values to the
    table values.

    Args:
        table: The table (a list of lists of strings).
        header (list, optional): The header to use. If not provided, the first row of
            the table will be used instead. Your header must be the same width as your
            table, and cannot contain the same entry multiple times.

    Returns: A list of dictionaries, where each entry in the list is a row in the table,
        and a row in the table is represented as a dictionary mapping the header to the
        values.

    Raises:
        InvalidTableHeaderError: If the width of the header does not match the width of
            the table, or if the header contains duplicate entries.
    """
    _validate_table_shape(table)
    header_provided = bool(header)
    if header is None:
        header = table[0]
    elif len(header) != len(table[0]):
        raise InvalidTableHeaderError(
            f"Header length of {len(header)} does not match the width of the table "
            f"({len(table[0])})"
        )
    elif len(header) != len(set(header)):
        raise InvalidTableHeaderError("Header contains repeated elements")
    new_table = []
    for row in table:
        new_row = {header[idx]: element for idx, element in enumerate(row)}
        new_table.append(new_row)

    if not header_provided:
        # The first row was the header, and we still mapped it. Remove it.
        # Note: We don't want to do table.pop(0) at the top as that would modify the
        # object that we were passed.
        new_table.pop(0)
    return new_table


def _extract_text_from_table(
    table: List[List[Optional["PDFElement"]]],
) -> List[List[str]]:
    """
    Given a table (of PDFElements or None), returns a table (of element.text or '').
    """
    _validate_table_shape(table)
    new_table = []
    for row in table:
        new_row = [element.text if element is not None else "" for element in row]
        new_table.append(new_row)
    return new_table


def _validate_table_shape(table: List[List[Any]]):
    """
    Checks that all rows (and therefore all columns) are the same length.
    """
    first_row_len = len(table[0])
    for idx, row in enumerate(table[1:]):
        if not len(row) == first_row_len:
            raise InvalidTableError(
                f"Table not rectangular, row 0 has {first_row_len} elements but row "
                f"{idx + 1} has {len(row)}."
            )