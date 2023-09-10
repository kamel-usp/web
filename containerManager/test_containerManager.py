from containerManager import containerManager
import time

def test_containerManager():
    containers = containerManager (0)
    list_id = []

    for i in range (5):
        list_id.append(containers.getContainer (i))
    for i in range (5):
        assert containers.getContainer (i) == list_id[i]
    
    time.sleep (1)

    containers.pruneContainers ()

    assert containers.activeContainerCount () != 5
    print (containers.activeContainerCount ())

def main():
    test_containerManager ()

if __name__ == "__main__":
    main()
