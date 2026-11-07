# A collection of deliberate Python errors

def calculate_average(numbers)
    # Syntax Error: Missing colon at the end of the function definition
    
    total = 0
    for i in range(len(numbers)):
    total += numbers[i]
    # Indentation Error: The loop body is not indented
    
    # Name Error: 'count' is never defined
    average = total / count 
    
    return average

def process_data():
    greeting = "Hello, user!"
    print(greeting + 123) 
    # Type Error: Cannot concatenate a string and an integer
    
    numbers_list = [10, 20, 30]
    print(numbers_list[5]) 
    # Index Error: Index 5 is out of bounds for a list of length 3
    
    my_dict = {"name": "Alice", "age": 25}
    print(my_dict["job"]) 
    # Key Error: The key 'job' does not exist in the dictionary

# Syntax Error: Using a single '=' instead of '==' for comparison in an if statement
if __name__ = "__main__":
    
    # ZeroDivision Error: Attempting to divide by zero
    result = 10 / 0 
    
    print(calculate_average([1, 2, 3]))
