import time
from typing import List, Tuple, Set

def find_pairs_efficiently(numbers: List[int], target_sum: int) -> List[Tuple[int, int]]:
    """
    Finds all unique pairs in a list that add up to a target sum.
    
    Time Complexity: O(N) - Single pass lookup using a hash set.
    Space Complexity: O(N) - Storage for the visited elements set.
    """
    visited_numbers: Set[int] = set()
    found_pairs: List[Tuple[int, int]] = []
    
    for num in numbers:
        complement = target_sum - num
        if complement in visited_numbers:
            found_pairs.append((complement, num))
        visited_numbers.add(num)
        
    return found_pairs

def execute_benchmark():
    # Generate a large dataset of 50,000 numbers for stress testing
    large_dataset = list(range(50000))
    target = 49999
    
    print("⚡ Running high-efficiency lookup test...")
    start_time = time.perf_counter()
    
    results = find_pairs_efficiently(large_dataset, target)
    
    end_time = time.perf_counter()
    duration = end_time - start_time
    
    print(f"✅ Processed {len(large_dataset):,} items successfully.")
    print(f"⏱️ Total Execution Time: {duration:.6f} seconds")

if __name__ == "__main__":
    execute_benchmark()
