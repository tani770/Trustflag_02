# ==========================================
# 🛑 THE INEFFICIENT WAY (O(N^2) Time Complexity)
# ==========================================
def find_duplicates_slow(items):
    """
    Checks for duplicates by comparing every element 
    to every other element. Sluggish and heavy.
    """
    duplicates = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            # Nested loop causes exponential slowdown as list grows
            if items[i] == items[j] and items[i] not in duplicates:
                duplicates.append(items[i])
    return duplicates

# ==========================================
# ⚡ THE EFFICIENT WAY (O(N) Time Complexity)
# ==========================================
def find_duplicates_fast(items):
    """
    Uses a hash set for instant lookups. 
    Lightning fast and scales beautifully.
    """
    seen = set()
    duplicates = set()
    
    for item in items:
        if item in seen:          # O(1) constant time lookup
            duplicates.add(item)
        else:
            seen.add(item)
            
    return list(duplicates)
