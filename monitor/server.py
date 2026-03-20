import socket
import time

PORT = 12345

def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', PORT))
    print(f"Research Time Server active on port {PORT}...")

    while True:
        data, addr = sock.recvfrom(1024)
        current_time = str(time.time()).encode()
        sock.sendto(current_time, addr)

if __name__ == "__main__":
    start_server()