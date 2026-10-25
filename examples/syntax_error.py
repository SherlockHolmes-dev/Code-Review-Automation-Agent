"""Example with a syntax error for testing."""


def greet(name):
    print(f"Hello, {name}!"
    # Missing closing parenthesis above — SyntaxError
    return name
