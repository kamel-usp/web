from PriorityQueue import PriorityQueue
import time

container_id = 0

def createContainer():
    global container_id
    container_id += 1
    return container_id - 1

def deleteContainer(container_id):
    return 0

class containerManager:
    def __init__(self, lifetime):
        self.container_lifetime = lifetime
        self.lifetime_pq = PriorityQueue()
        self.user_id_to_container_id = dict()

    def activeContainerCount(self):
        return len(self.user_id_to_container_id)

    def getContainer(self, user_id):
        if self.user_id_to_container_id.get(user_id) != None:
            return self.user_id_to_container_id[user_id]
        else:
            container_id = createContainer()
            self.user_id_to_container_id[user_id] = container_id

            self.lifetime_pq.insert((container_id, user_id), time.time() + self.container_lifetime)
            return container_id

    def pruneContainers(self):
        while not self.lifetime_pq.is_empty() and self.lifetime_pq.top_prio() < time.time():
            container_id, user_id = self.lifetime_pq.top()
            self.lifetime_pq.pop()
            self.user_id_to_container_id.pop(user_id)
            deleteContainer(container_id)
        


