import pytest

from pipeline import layout


def _heavy_hex_like() -> tuple[int, list[tuple[int, int]]]:
    """Two rows of five (0-4 and 7-11) joined by bridges 5 (2-9) and 6 (4-11): the
    numbering pattern IBM uses, with the second row shifted one column left."""
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (7, 8), (8, 9), (9, 10), (10, 11)]
    edges += [(2, 5), (5, 8), (4, 6), (6, 10)]
    return 12, layout.undirected_edges(edges)


def test_undirected_edges_dedupes_and_orders() -> None:
    assert layout.undirected_edges([(1, 0), (0, 1), (2, 2), (3, 1)]) == [(0, 1), (1, 3)]


def test_heavy_hex_coordinates_places_rows_and_bridges() -> None:
    n, edges = _heavy_hex_like()
    coords = layout.heavy_hex_coordinates(n, edges)
    assert coords is not None
    assert coords[0] == (0, 0)
    assert coords[4] == (4, 0)
    assert coords[5] == (2, 1)  # under qubit 2
    assert coords[6] == (4, 1)  # under qubit 4
    assert coords[8] == (2, 2)  # the second row lines up under its bridges
    assert coords[7] == (1, 2)


def test_heavy_hex_coordinates_rejects_other_graphs() -> None:
    # A triangle is not a heavy-hex lattice: refuse rather than draw something misleading.
    assert layout.heavy_hex_coordinates(3, [(0, 1), (0, 2), (1, 2)]) is None
    # A bridge that joins rows two apart.
    edges = [(0, 1), (1, 2), (4, 5), (5, 6), (8, 9), (9, 10), (0, 3), (3, 8)]
    assert layout.heavy_hex_coordinates(11, layout.undirected_edges(edges)) is None


def test_fez_layout_from_bundled_description() -> None:
    found = layout.device_layout("ibm_fez")
    assert found is not None
    assert found.device == "FakeFez"
    assert found.num_qubits == 156
    assert len(found.edges) == 176
    points = found.coordinates
    assert len(points) == 156
    assert len(set(points)) == 156  # no two qubits overlap
    for a, b in found.edges:  # every coupling is one grid step long
        (xa, ya), (xb, yb) = points[a], points[b]
        assert abs(xa - xb) + abs(ya - yb) == 1
    assert min(x for x, _ in points) == 0
    assert min(y for _, y in points) == 0


@pytest.mark.parametrize("name", [None, "ibm_nonexistent", "simulator", "ibm_fez2", ""])
def test_no_layout_without_a_bundled_description(name: str | None) -> None:
    assert layout.device_layout(name) is None
