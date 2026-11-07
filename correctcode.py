def calculate_average(numbers: list[float]) -> float:
    """Calculates the average of a list of numbers efficiently."""
    if not numbers:
        return 0.0  # Prevents DivisionByZero error if the list is empty
    
    # Efficient: Uses Python's built-in C-optimized sum() instead of a manual loop
    return sum(numbers) / len(numbers)


def process_data():
    """Demonstrates safe data handling and type conversions."""
    greeting = "Hello, user!"
    # Fixed Type Error: Explicitly converted the integer to a string
    print(greeting + str(123)) 
    
    # Fixed Syntax & Index Errors: Properly defined the list and used a valid index
    numbers_list = [10, 20, 30]
    print(f"First item: {numbers_list[0]}") 
    
    my_dict = {"name": "Alice", "age": 25}
    # Fixed Key Error: Used .get() to provide a safe default value if the key is missing
    print(f"Job: {my_dict.get('job', 'Not Specified')}") 


# Fixed Syntax Error: Used '==' for comparison
if __name__ == "__main__":
    # Fixed ZeroDivision Error: Guarded the division with a condition
    denominator = 0
    result = 10 / denominator if denominator != 0 else 0
    print(f"Division result: {result}")
    
    # Run the processed data demo
    process_data()
    
    # Test the average function with a valid list
    sample_data = [10, 20, 30, 40, 50]
    avg = calculate_average(sample_data)
    print(f"The average is: {avg}")
