import time

def find_even_numbers_inefficient(numbers_list):
    even_numbers = []
    
    for number in numbers_list
        # 1. Artificial slowdown (pausing execution)
        time.sleep(0.1) 
        
        # 2. Inefficient arithmetic calculation instead of simple modulo
        is_even = False
        if (number / 2) == int(number / 2):
            is_even = True
            
        if is_even:
            # 3. Inefficient duplicate checking (scans the entire list every time)
            if number not in even_numbers:
                even_numbers.append(number)
                
    return even_numbers

# Example usage:
my_numbers = [1, 2, 3, 4, 5, 6, 2, 4]
result = find_even_numbers_inefficient(my_numbers)
print(result)  # Output: [2, 4, 6]
