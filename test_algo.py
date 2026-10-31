def find_matching_pairs(users, transactions):
    # Optimized: O(N) lookup using a set hash table
    user_ids = {user['id'] for user in users}
    return [tx for tx in transactions if tx['user_id'] in user_ids]
