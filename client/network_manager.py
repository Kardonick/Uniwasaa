import socket
import threading
import json
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.protocol import *

class NetworkManager:
    def __init__(self):
        self.tcp_sock = None
        self.udp_sock = None
        self.observers = []
        self.username = None
        self.running = False
        self.udp_addr = None # (ip, port) of server UDP

    def connect(self, host, tcp_port, udp_port):
        try:
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.connect((host, tcp_port))
            
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.bind(('0.0.0.0', 0))
            self.udp_addr = (host, udp_port)
            
            self.running = True
            threading.Thread(target=self._listen_tcp, daemon=True).start()
            threading.Thread(target=self._listen_udp, daemon=True).start()
            
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def register_observer(self, observer):
        if observer not in self.observers:
            self.observers.append(observer)

    def notify_observers(self, event, data):
        for observer in self.observers:
            observer.update(event, data)

    def login(self, username, password):
        self.username = username # Store username tentatively
        Protocol.send_tcp_message(self.tcp_sock, CMD_LOGIN, {"username": username, "password": password})
        # We wait for response in _listen_tcp

    def register(self, username, password):
        Protocol.send_tcp_message(self.tcp_sock, CMD_REGISTER, {"username": username, "password": password})

    def send_message(self, to_user, message):
        Protocol.send_tcp_message(self.tcp_sock, CMD_CHAT_MSG, {"to": to_user, "message": message})

    def send_user_list_request(self):
        Protocol.send_tcp_message(self.tcp_sock, CMD_USER_LIST, {})

    def send_file_offer(self, to_user, filename, filesize):
        Protocol.send_tcp_message(self.tcp_sock, CMD_FILE_OFFER, {"to": to_user, "filename": filename, "filesize": filesize})

    def send_file_accept(self, from_user):
        Protocol.send_tcp_message(self.tcp_sock, CMD_FILE_ACCEPT, {"from": from_user})

    def send_file_reject(self, from_user):
        Protocol.send_tcp_message(self.tcp_sock, CMD_FILE_REJECT, {"from": from_user})

    def send_file_data(self, to_user, filename, data_chunk):
        Protocol.send_tcp_message(self.tcp_sock, CMD_FILE_DATA, {"to": to_user, "filename": filename, "data": data_chunk})

    def send_call_invite(self, to_user):
        Protocol.send_tcp_message(self.tcp_sock, CMD_CALL_INVITE, {"to": to_user})

    def send_call_accept(self, from_user):
        Protocol.send_tcp_message(self.tcp_sock, CMD_CALL_ACCEPT, {"from": from_user})

    def send_call_reject(self, from_user):
        Protocol.send_tcp_message(self.tcp_sock, CMD_CALL_REJECT, {"from": from_user})

    def send_call_end(self):
        Protocol.send_tcp_message(self.tcp_sock, CMD_CALL_END)

    def send_udp_frame(self, packet_type, session_id, sequence, payload):
        # Client sends sender_id = 0, Server will overwrite it with trusted ID
        packet = Protocol.create_udp_packet(packet_type, session_id, 0, sequence, payload)
        if self.udp_addr:
            self.udp_sock.sendto(packet, self.udp_addr)
            # print(f"Sent UDP frame type {packet_type} to {self.udp_addr}") # Too noisy for video

    def create_group(self, name, members):
        Protocol.send_tcp_message(self.tcp_sock, CMD_GROUP_CREATE, {"name": name, "members": members})

    def send_group_list_request(self):
        Protocol.send_tcp_message(self.tcp_sock, CMD_GROUP_LIST, {})

    def send_group_message(self, group_id, message):
        Protocol.send_tcp_message(self.tcp_sock, CMD_GROUP_MSG, {"group_id": group_id, "message": message})

    def send_group_file_offer(self, group_id, filename, filesize):
        Protocol.send_tcp_message(self.tcp_sock, CMD_GROUP_FILE_OFFER, {"group_id": group_id, "filename": filename, "filesize": filesize})

    def _listen_tcp(self):
        print("Listening for TCP messages...")
        while self.running:
            try:
                msg = Protocol.receive_tcp_message(self.tcp_sock)
                if msg is None:
                    print("Server disconnected (None received)")
                    self.notify_observers("DISCONNECTED", None)
                    break
                
                print(f"Received TCP: {msg}")
                cmd = msg.get('cmd')
                data = msg.get('data')
                
                if cmd == CMD_OK:
                    if data.get('message') == "Login successful":
                        # self.username is already set in login()
                        # Send UDP Hello
                        if self.username:
                            self.send_udp_hello(self.username)
                
                self.notify_observers(cmd, data)
            except Exception as e:
                print(f"TCP Listen Error: {e}")
                break

    def _listen_udp(self):
        print("Listening for UDP packets...")
        while self.running:
            try:
                data, addr = self.udp_sock.recvfrom(65535)
                # print(f"Received UDP packet from {addr}, len: {len(data)}")
                parsed = Protocol.parse_udp_packet(data)
                if parsed:
                    packet_type, session_id, sender_id, sequence, payload = parsed
                    # print(f"Parsed UDP: Type={packet_type}, Session={session_id}, Sender={sender_id}")
                    self.notify_observers("UDP_FRAME", {
                        "type": packet_type,
                        "session_id": session_id,
                        "sender_id": sender_id,
                        "sequence": sequence,
                        "payload": payload
                    })
                else:
                    print("Failed to parse UDP packet")
            except Exception as e:
                print(f"UDP Listen Error: {e}")

    def send_udp_hello(self, username):
        if self.udp_sock and self.udp_addr:
            msg = json.dumps({"type": "HELLO", "username": username})
            self.udp_sock.sendto(msg.encode('utf-8'), self.udp_addr)
            print(f"Sent UDP HELLO for {username}")
