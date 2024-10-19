import socket

HOST = '192.168.1.35'  # Adresse IP de l'interface
PORT = 5000        # Port à utiliser

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()
    conn, addr = s.accept()
    with conn:
        print('Connected by', addr)
        while True:
            data = conn.recv(1024)
            if not data:
                break
            print(data.decode('latin-1'))