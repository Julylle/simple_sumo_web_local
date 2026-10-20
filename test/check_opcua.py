import socket

HOST = "127.0.0.1"
PORT = 49320

try:
    with socket.create_connection((HOST, PORT), timeout=5):
        print("TCP connection successful!")

except socket.timeout:
    print("TCP connection timed out!")

except ConnectionRefusedError:
    print("Connection refused!")

except OSError as e:
    print(f"Connection failed: {e}")