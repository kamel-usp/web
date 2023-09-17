from PriorityQueue import *
from random import shuffle

def test_heap_comum():
	n = 1000

	pq = PriorityQueue()

	v = list(range(n))
	shuffle(v)

	for i in v:
		pq.insert(i, i)

	for i in range(n):
		assert pq.top() == i
		pq.pop()



def test_heap_funcao_comparadora():
	n = 1000

	pq = PriorityQueue(lambda a, b: b < a)

	v = list(range(n))
	shuffle(v)

	for i in v:
		pq.insert(i, i)

	for i in range(n):
		assert pq.top() == n - i - 1
		pq.pop()

def test_set_prio():
	n = 1000

	pq = PriorityQueue()

	v = list(range(n))
	shuffle(v)

	for i in v:
		pq.insert(i, 1)

	for i in range(n):
		pq.set_prio(i, 0)
		assert pq.top() == i
		pq.set_prio(i, i + 2)

	for i in range(n):
		assert pq.top() == i
		pq.pop()


def main():
	test_heap_comum()
	test_heap_funcao_comparadora()
	test_set_prio()

if __name__ == "__main__":
    main()
