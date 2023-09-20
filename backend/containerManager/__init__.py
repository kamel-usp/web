from .PriorityQueue import PriorityQueue
import time
import docker
from collections import deque


class dockerApi:
    def __init__(self):
        self.client = docker.from_env()
        self.assert_image_is_built()

    def assert_image_is_built(self):
        self.image_id = self.client.images.build(
            path="./dPaspRunner", tag="dpasp-runner"
        )

    def createContainer(self):
        container = self.client.containers.run(
            "dpasp-runner",  # Specify the Docker image to use
            detach=True,  # Run the container in detached mode
        )
        net = self.client.networks.list(names="dpasp-instances")[0]
        net.connect(container, aliases=[f"dpasp-instance-{container.short_id}"])
        print(f"Created container with ID: {container.short_id}")
        return container.short_id

    def deleteContainer(self, container_id):
        container = self.client.containers.get(container_id)
        container.stop()


class containerManager:
    def __init__(self, lifetime, pre_allocate=1, docker_api=dockerApi()):
        self.docker_api = docker_api
        self.container_lifetime = lifetime
        self.lifetime_pq = PriorityQueue()
        self.user_id_to_container_id = dict()

        self.pre_allocated_containers = deque()
        for i in range(pre_allocate):
            self.pre_allocated_containers.append(self.docker_api.createContainer())

    def activeContainerCount(self):
        return len(self.user_id_to_container_id)

    def getContainer(self, user_id):
        if self.user_id_to_container_id.get(user_id) != None:
            return self.user_id_to_container_id[user_id]
        else:
            self.pre_allocated_containers.append(self.docker_api.createContainer())
            container_id = self.pre_allocated_containers.popleft()
            self.user_id_to_container_id[user_id] = container_id

            self.lifetime_pq.insert(
                (container_id, user_id), time.time() + self.container_lifetime
            )
            return container_id

    def pruneContainers(self):
        while (
            not self.lifetime_pq.is_empty()
            and self.lifetime_pq.top_prio() < time.time()
        ):
            container_id, user_id = self.lifetime_pq.top()
            self.lifetime_pq.pop()
            self.user_id_to_container_id.pop(user_id)
            self.docker_api.deleteContainer(container_id)

    def stopAllContainers(self):
        for user_id, container_id in self.user_id_to_container_id.items():
            print(f"Stopping container {container_id} from {user_id}")
            self.docker_api.deleteContainer(container_id)

        for container_id in self.pre_allocated_containers:
            print(f"Stoppin pre allocated container {container_id}")
            self.docker_api.deleteContainer(container_id)
