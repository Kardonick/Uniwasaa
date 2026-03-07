import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from server.network import Server

if __name__ == "__main__":
    server = Server()
    server.start()
