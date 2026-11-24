"""Exact closed rational convex sets in the lag plane."""

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Sequence

Point = tuple[Fraction, Fraction]


def _as_point(point: Sequence[Fraction | int]) -> Point:
    x, y = point
    return (Fraction(x), Fraction(y))


def cross(origin: Point, first: Point, second: Point) -> Fraction:
    return (first[0] - origin[0]) * (second[1] - origin[1]) - (
        first[1] - origin[1]
    ) * (second[0] - origin[0])


def convex_hull(points: Iterable[Sequence[Fraction | int]]) -> tuple[Point, ...]:
    """Return the vertices of the closed convex hull in counter-clockwise order.

    Collinear interior points are dropped; a fully collinear set collapses to
    its two extreme points and a single point stays a single point.
    """
    unique = sorted({_as_point(point) for point in points})
    if len(unique) <= 1:
        return tuple(unique)
    lower: list[Point] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[Point] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    hull = lower[:-1] + upper[:-1]
    return tuple(hull)


@dataclass(frozen=True)
class ConvexRegion:
    """A nonempty closed convex subset given by its hull vertices.

    One vertex is an isolated point, two vertices are a segment, and three or
    more vertices describe a (possibly lower-dimensional) convex polygon.  The
    vertices are canonicalised to counter-clockwise hull order on construction.
    """

    vertices: tuple[Point, ...]

    def __post_init__(self) -> None:
        hull = convex_hull(self.vertices)
        if not hull:
            raise ValueError('a convex region requires at least one vertex')
        object.__setattr__(self, 'vertices', hull)

    @property
    def dimension(self) -> int:
        if len(self.vertices) == 1:
            return 0
        if len(self.vertices) == 2:
            return 1
        return 2

    def contains(self, point: Sequence[Fraction | int]) -> bool:
        x, y = _as_point(point)
        vertices = self.vertices
        if len(vertices) == 1:
            return x == vertices[0][0] and y == vertices[0][1]
        if len(vertices) == 2:
            first, second = vertices
            if cross(first, second, (x, y)) != 0:
                return False
            return (
                min(first[0], second[0]) <= x <= max(first[0], second[0])
                and min(first[1], second[1]) <= y <= max(first[1], second[1])
            )
        for index, origin in enumerate(vertices):
            target = vertices[(index + 1) % len(vertices)]
            if cross(origin, target, (x, y)) < 0:
                return False
        return True


def is_subset(inner: ConvexRegion, outer: ConvexRegion) -> bool:
    """Whether every point of ``inner`` lies in ``outer``.

    Both sets are convex, so checking the vertices of ``inner`` is sufficient.
    """
    return all(outer.contains(vertex) for vertex in inner.vertices)


def _gcd(a: int, b: int) -> int:
    a, b = abs(a), abs(b)
    while b:
        a, b = b, a % b
    return a or 1


def _line_key(first: Point, second: Point) -> tuple[int, int, Fraction]:
    """Unoriented line identity plus the direction used to order points on it."""
    dx = second[0] - first[0]
    dy = second[1] - first[1]
    if dx == 0 and dy == 0:
        raise ValueError('a segment requires two distinct endpoints')
    denominator = dx.denominator * dy.denominator // _gcd(dx.denominator, dy.denominator)
    ix, iy = int(dx * denominator), int(dy * denominator)
    divisor = _gcd(ix, iy)
    ix, iy = ix // divisor, iy // divisor
    if ix < 0 or (ix == 0 and iy < 0):
        ix, iy = -ix, -iy
    # Line through the two points: -iy*x + ix*y = offset.
    offset = ix * first[1] - iy * first[0]
    return ix, iy, offset


def _parameter(point: Point, direction: tuple[int, int]) -> Fraction:
    return point[0] * direction[0] + point[1] * direction[1]


def _point_at(
    direction: tuple[int, int], offset: Fraction, parameter: Fraction,
) -> Point:
    ix, iy = direction
    scale = ix * ix + iy * iy
    x = (ix * parameter - iy * offset) / scale
    y = (iy * parameter + ix * offset) / scale
    return (x, y)


def _merge_segments(regions: list[ConvexRegion]) -> list[ConvexRegion]:
    groups: dict[tuple[int, int, Fraction], list[tuple[Fraction, Fraction]]] = {}
    output: list[ConvexRegion] = []
    for region in regions:
        if region.dimension != 1:
            output.append(region)
            continue
        key = _line_key(*region.vertices)
        direction = (key[0], key[1])
        low, high = sorted(_parameter(vertex, direction) for vertex in region.vertices)
        groups.setdefault(key, []).append((low, high))
    for key, members in groups.items():
        direction = (key[0], key[1])
        offset = key[2]
        members.sort()
        current_start, current_end = members[0]
        for start, end in members[1:]:
            if start <= current_end:
                current_end = max(current_end, end)
                continue
            output.append(_segment_on_line(direction, offset, current_start, current_end))
            current_start, current_end = start, end
        output.append(_segment_on_line(direction, offset, current_start, current_end))
    return output


def _segment_on_line(
    direction: tuple[int, int], offset: Fraction, start: Fraction, end: Fraction,
) -> ConvexRegion:
    return ConvexRegion((
        _point_at(direction, offset, start),
        _point_at(direction, offset, end),
    ))


def normalize_regions(regions: Iterable[ConvexRegion]) -> tuple[ConvexRegion, ...]:
    """Canonicalise a union of convex sets.

    Duplicate shapes are collapsed, touching collinear segments are merged, and
    any set contained in another member is dropped.  The result keeps genuinely
    separate regions, segments and isolated points.
    """
    unique = []
    seen = set()
    for region in regions:
        if region.vertices in seen:
            continue
        seen.add(region.vertices)
        unique.append(region)
    merged = _merge_segments(unique)
    keep = []
    for index, region in enumerate(merged):
        redundant = False
        for other_index, other in enumerate(merged):
            if other_index == index or not is_subset(region, other):
                continue
            if is_subset(other, region):
                # Equal shapes: keep only the earliest surviving copy.
                if other_index < index:
                    redundant = True
                    break
            else:
                redundant = True
                break
        if not redundant:
            keep.append(region)
    return tuple(keep)
