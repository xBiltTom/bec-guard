"""Conservative ASCII hostname comparison, without DNS or public-suffix guessing."""


def edit_distance(left: str, right: str) -> int:
    row = list(range(len(right) + 1))
    for i, char in enumerate(left, start=1):
        next_row = [i]
        for j, other in enumerate(right, start=1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (char != other)))
        row = next_row
    return row[-1]


def is_domain_lookalike(candidate: str, official: str) -> bool:
    candidate, official = candidate.lower().rstrip("."), official.lower().rstrip(".")
    if candidate == official:
        return False
    left, right = candidate.split("."), official.split(".")
    # Same number of labels, exactly one changed label. Shared .com/.example alone
    # is insufficient; small labels are too ambiguous to compare safely.
    if len(left) != len(right):
        return False
    changed = [(a, b) for a, b in zip(left, right, strict=True) if a != b]
    if len(changed) != 1:
        return False
    a, b = changed[0]
    if min(len(a), len(b)) < 5:
        return False
    # rn/m is a common ASCII visual substitution, even though edit distance is 2.
    return a.replace("rn", "m") == b.replace("rn", "m") or edit_distance(a, b) == 1
