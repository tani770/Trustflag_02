import itertools
import time

def find_efficient_pairs(data_list, target_sum):
    """
    Efficiently finds pairs that sum up to a target value.
    Replaces a traditional nested loop O(N^2) with an O(N) lookup approach,
    or uses optimized combinations.
    """
    seen = set()
    matching_pairs = []
    
    # O(N) linear scan instead of nested loops
    for item in data_list:
        complement = target_sum - item
        if complement in seen:
            matching_pairs.append((complement, item))
        seen.add(item)
        
    return matching_pairs

def run_performance_test():
    # Generate test dataset: 0 to 10,000
    test_data = list(range(10000))
    target = 9999
    
    print(f"🚀 Starting test on branch: test-nested-loop")
    start_time = time.perf_counter()
    
    # Execute the efficient search
    results = find_efficient_pairs(test_data, target)
    
    end_time = time.perf_counter()
    execution_time = end_time - start_time
    
    print(f"✅ Found {len(results)} matching pairs.")
    print(f"⏱️ Execution time: {execution_time:.6f} seconds")

if __name__ == "__main__":
    run_performance_test()
