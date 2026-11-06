from collections.abc import Iterable
from typing import Any


def set_sequential_indexes(
    items: Iterable[Any],
    *,
    index_field: str = 'index',
    start: int = 0,
) -> None:
    """ Sets consecutive indexes to items in provided order """
    for index, item in enumerate(items, start=start):
        setattr(item, index_field, index)
