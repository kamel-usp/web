from containerManager import containerManager
import time

class mockDocker:
	def __init__(self):
		self.container_id = 0
		
	def createContainer(self):
		self.container_id += 1
		return self.container_id - 1
	
	def deleteContainer(self, container_id):
		pass

def test_containerManager():
	containers = containerManager (0.09, mockDocker())
	list_id = []

	for i in range (5):
		list_id.append(containers.getContainer (i))
	for i in range (5):
		assert containers.getContainer (i) == list_id[i]

	time.sleep (0.1)

	for i in range (5, 10):
		list_id.append(containers.getContainer (i))

	assert containers.activeContainerCount () == 10
	containers.pruneContainers ()
	assert containers.activeContainerCount () == 5

def main():
	test_containerManager ()

if __name__ == "__main__":
	main()
