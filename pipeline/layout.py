"""The backend's qubit layout, from Qiskit's bundled (offline) device description.

``qiskit_ibm_runtime.fake_provider`` ships a snapshot of each IBM device as files inside the
package. Reading one needs no account and no network. Qiskit has no drawing coordinates for
every device (none for the 156-qubit Heron chips), so ``heavy_hex_coordinates`` derives them
from the coupling graph. See SPEC.md, Section 7.1, and SCHEMA.md (``layout``).
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

DESCRIPTION = "Qiskit's bundled device description"


@dataclass(frozen=True)
class DeviceLayout:
    device: str  # the fake backend's class name, for example "FakeFez"
    num_qubits: int
    edges: list[tuple[int, int]]  # undirected, a < b, sorted
    coordinates: list[tuple[int, int]]  # (x, y) per qubit, in grid units


def undirected_edges(pairs: Iterable[Sequence[int]]) -> list[tuple[int, int]]:
    """Each coupling once, as ``(a, b)`` with ``a < b``, sorted; self-loops dropped."""
    return sorted({(min(a, b), max(a, b)) for a, b in pairs if a != b})


def heavy_hex_coordinates(
    num_qubits: int, edges: Sequence[tuple[int, int]]
) -> list[tuple[int, int]] | None:
    """Drawing coordinates for a heavy-hex device, or ``None`` if the graph is not one.

    IBM numbers a heavy-hex device in reading order: a long row of qubits joined to its
    neighbours by consecutive numbers, then the few "bridge" qubits that join that row to
    the next, then the next row. So:

    - a **row** is a maximal run of consecutively numbered qubits joined in a chain, at
      least three long; rows go on y = 0, 2, 4, ... in order and x = 0, 1, 2, ... from the
      row's first qubit, shifted so that the bridges line up;
    - a **bridge** is any other qubit; it must join exactly two qubits in consecutive rows
      and sits on the odd y between them, at their x.

    Rows can be offset from one another (on Heron, every row starts one column further
    left or right), so each row's x offset is set from the bridges above it. Anything that
    does not fit this pattern returns ``None`` rather than a misleading picture.
    """
    if num_qubits <= 0:
        return None
    edge_set = set(edges)
    neighbours: dict[int, list[int]] = {q: [] for q in range(num_qubits)}
    for a, b in edges:
        if not (0 <= a < num_qubits and 0 <= b < num_qubits):
            return None
        neighbours[a].append(b)
        neighbours[b].append(a)

    # Maximal runs q, q+1, ..., joined by an edge between each consecutive pair.
    runs: list[list[int]] = []
    current = [0]
    for q in range(1, num_qubits):
        if (q - 1, q) in edge_set:
            current.append(q)
        else:
            runs.append(current)
            current = [q]
    runs.append(current)
    rows = [run for run in runs if len(run) >= 3]
    if len(rows) < 1:
        return None
    row_of = {q: r for r, run in enumerate(rows) for q in run}
    bridges = [q for q in range(num_qubits) if q not in row_of]

    # Each bridge joins exactly two qubits in consecutive rows.
    bridge_ends: dict[int, tuple[int, int]] = {}
    for q in bridges:
        ends = sorted(neighbours[q], key=lambda n: row_of.get(n, -1))
        if len(ends) != 2 or any(n not in row_of for n in ends):
            return None
        upper, lower = ends
        if row_of[lower] != row_of[upper] + 1:
            return None
        bridge_ends[q] = (upper, lower)

    # Offset each row so the bridges above it stand straight: lower end under upper end.
    offset = [0] * len(rows)
    position = {q: i for run in rows for i, q in enumerate(run)}
    for r in range(1, len(rows)):
        shifts = {
            offset[r - 1] + position[upper] - position[lower]
            for upper, lower in bridge_ends.values()
            if row_of[lower] == r
        }
        if len(shifts) != 1:
            return None
        offset[r] = shifts.pop()
    least = min(offset)

    coordinates: dict[int, tuple[int, int]] = {}
    for r, run in enumerate(rows):
        for q in run:
            coordinates[q] = (position[q] + offset[r] - least, 2 * r)
    for q, (upper, _) in bridge_ends.items():
        x, y = coordinates[upper]
        coordinates[q] = (x, y + 1)

    # Every edge must be a unit step on the grid, and no two qubits may share a point.
    points = [coordinates[q] for q in range(num_qubits)]
    if len(set(points)) != num_qubits:
        return None
    for a, b in edges:
        (xa, ya), (xb, yb) = coordinates[a], coordinates[b]
        if abs(xa - xb) + abs(ya - yb) != 1:
            return None
    return points


def _fake_backend_class(backend_name: str) -> Any | None:
    """The bundled fake backend for ``ibm_<name>`` (``FakeName``), or ``None``."""
    if not backend_name.startswith("ibm_"):
        return None
    suffix = backend_name.removeprefix("ibm_")
    if not suffix.isalpha():
        return None
    from qiskit_ibm_runtime import fake_provider

    return getattr(fake_provider, f"Fake{suffix.capitalize()}", None)


def device_layout(backend_name: str | None) -> DeviceLayout | None:
    """The bundled layout for a backend, or ``None`` if Qiskit ships none or it can't be
    drawn. Reads only files inside the installed package; never uses an account."""
    if backend_name is None:
        return None
    cls = _fake_backend_class(backend_name)
    if cls is None:
        return None
    fake = cls()
    num_qubits = int(fake.num_qubits)
    edges = undirected_edges(fake.coupling_map.get_edges())
    coordinates = heavy_hex_coordinates(num_qubits, edges)
    if coordinates is None:
        return None
    return DeviceLayout(
        device=cls.__name__, num_qubits=num_qubits, edges=edges, coordinates=coordinates
    )


def runtime_version() -> str:
    return importlib.metadata.version("qiskit-ibm-runtime")
