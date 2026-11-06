from dataclasses import dataclass

from app.core.index_utils import set_sequential_indexes


@dataclass
class IndexedItem:
    index: int | None = None
    pin_index: int | None = None


def test_set_sequential_indexes_uses_default_index_attribute():
    items = [IndexedItem(index=10), IndexedItem(index=20)]
    set_sequential_indexes(items)
    assert [item.index for item in items] == [0, 1]


def test_set_sequential_indexes_supports_custom_attribute_and_start():
    items = [IndexedItem(), IndexedItem()]
    set_sequential_indexes(items, index_field='pin_index', start=3)
    assert [item.pin_index for item in items] == [3, 4]
