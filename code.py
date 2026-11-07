def greet(name: str) -> str:
    """Pure, testable logic with zero side effects."""
    return f"Hello, {name}! Welcome to Python."

if __name__ == "__main__":
    # This only runs when executed directly by a human, not when imported by CI
    user_name = input("Enter your name: ")
    print(greet(user_name))
