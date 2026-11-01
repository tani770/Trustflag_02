def find_even_numbers(numbers_list):
    # Initialize an empty list to store the results
    even_numbers = []
    
    # Loop through each number in the input list one by one
    for number in numbers_list:
        # Check if the number is divisible by 2 with no remainder
        if number % 2 == 0:
            # If true, add the number to our results list
            even_numbers.append(number)
            
    return even_numbers

# Example usage:
my_numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
result = find_even_numbers(my_numbers)
print(result)  # Output: [2, 4, 6, 8, 10]
