class PriorityQueue():
	@staticmethod
	def is_root(i: int) -> bool:
		return i == 0

	@staticmethod
	def parent(i: int) -> int:
		return (i - 1)//2

	@staticmethod
	def left(i: int) -> int:
		return 2 * i + 1

	@staticmethod
	def right(i: int) -> int:
		return PriorityQueue.left(i) + 1

	def swap(self, i: int, j: int):
		self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
		self.dict[self.heap[i][0]] = i
		self.dict[self.heap[j][0]] = j


	def __init__(self, has_priority_over = lambda a, b: a < b):
		self.heap = []
		self.dict = dict()
		self.has_priority_over_raw = has_priority_over
		self.has_priority_over = lambda a, b: has_priority_over(self.heap[a][1], self.heap[b][1])

	def rise(self, i: int):
		while not PriorityQueue.is_root(i):
			p = PriorityQueue.parent(i)

			if not self.has_priority_over(i, p):
				break

			self.swap(i, p)
			i = p

	def sink(self, i: int):
		size = len(self.heap)
		while True:
			candidate = i
			left = PriorityQueue.left(i)
			right = PriorityQueue.right(i)

			if left < size and self.has_priority_over(left, candidate):
				candidate = left

			if right < size and self.has_priority_over(right, candidate):
				candidate = right

			if i == candidate:
				break

			self.swap(i, candidate)
			i = candidate

	def insert(self, val, prio):
		pos = len(self.heap)
		self.heap.append([val, prio]);
		self.dict[val] = pos
		self.rise(pos)

	def pop(self):
		self.swap(0, len(self.heap) - 1)
		self.heap.pop()
		self.sink(0)

	def top(self):
		return self.heap[0][0]

	def top_prio(self):
		return self.heap[0][1]

	def set_prio(self, val, new_prio):
		pos = self.dict[val]
		old_prio = self.heap[pos][1]
		self.heap[pos][1] = new_prio
		if self.has_priority_over_raw(new_prio, old_prio):
			self.rise(pos)
		else:
			self.sink(pos)
