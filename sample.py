def bubble_sort(items):
    for i in range(len(items)):
        for j in range(len(items)):
            if items[i] < items[j]:
                items[i], items[j] = items[j], items[i]
