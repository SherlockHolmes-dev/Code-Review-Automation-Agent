"""A clean, well-structured example: FizzBuzz implementation.

This file should pass all checks with minimal or no findings.
"""


def fizzbuzz(n: int) -> list[str]:
    """Return FizzBuzz results for numbers 1 through n.

    Args:
        n: Upper bound (inclusive). Must be a positive integer.

    Returns:
        List of strings: "Fizz", "Buzz", "FizzBuzz", or the number.

    Raises:
        ValueError: If n is not a positive integer.
    """
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"n must be a positive integer, got {n!r}")

    results: list[str] = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            results.append("FizzBuzz")
        elif i % 3 == 0:
            results.append("Fizz")
        elif i % 5 == 0:
            results.append("Buzz")
        else:
            results.append(str(i))
    return results


def main() -> None:
    """Print FizzBuzz for 1-20."""
    for item in fizzbuzz(20):
        print(item)


if __name__ == "__main__":
    main()
