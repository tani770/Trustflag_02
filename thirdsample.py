def bubble_sort(items):
    n = len(items)
    # Outer loop tracks the number of passes
    for i in range(n):
        # Flag to optimize: stop early if list is already sorted
        swapped = False
        
        # Inner loop compares adjacent elements; shrinks as largest items "bubble" to the end
        for j in range(0, n - i - 1):
            if items[j] > items[j + 1]:
                # Swap adjacent elements in place
                items[j], items[j + 1] = items[j + 1], items[j]
                swapped = True
                
        # If no two elements were swapped in this pass, the list is already sorted
        if not swapped:
            break
