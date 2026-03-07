import socket
import threading
import configparser
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.protocol import *
from server.client_session import ClientSession
from server.handlers import HandlerFactory
from server.database import Database

class Server:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Server, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.clients = {} # username -> ClientSession
        self.sessions = [] # List of all ClientSession objects (authenticated or not)
        self.lock = threading.Lock()
        self.running = True
        self._load_config()

    def _load_config(self):
        config = configparser.ConfigParser()
        config.read(os.path.join(os.path.dirname(__file__), '../config.ini'))
        self.host = config['SERVER']['host']
        self.tcp_port = int(config['SERVER']['tcp_port'])
        self.udp_port = int(config['SERVER']['udp_port'])

    def start(self):
        print(f"Starting server on {self.host}...")
        
        # TCP Socket
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.bind((self.host, self.tcp_port))
        self.tcp_sock.listen(5)
        
        # UDP Socket
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind((self.host, self.udp_port))

        # Threads
        threading.Thread(target=self._accept_tcp_clients, daemon=True).start()
        threading.Thread(target=self._handle_udp_traffic, daemon=True).start()
        
        print(f"Server listening on TCP {self.tcp_port} and UDP {self.udp_port}")
        
        try:
            while self.running:
                pass # Main thread keeps running
        except KeyboardInterrupt:
            print("Stopping server...")
            self.running = False
            self.tcp_sock.close()
            self.udp_sock.close()

    def _accept_tcp_clients(self):
        while self.running:
            try:
                conn, addr = self.tcp_sock.accept()
                print(f"New connection from {addr}")
                session = ClientSession(conn, addr)
                with self.lock:
                    self.sessions.append(session)
                threading.Thread(target=self._handle_tcp_client, args=(session,), daemon=True).start()
            except Exception as e:
                print(f"Error accepting client: {e}")

    def _handle_tcp_client(self, session):
        try:
            while self.running:
                msg = Protocol.receive_tcp_message(session.conn)
                if msg is None:
                    break
                
                cmd = msg.get('cmd')
                data = msg.get('data')
                
                handler = HandlerFactory.get_handler(cmd)
                if handler:
                    handler.handle(self, session, cmd, data)
                else:
                    print(f"Unknown command: {cmd}")
        except Exception as e:
            print(f"Client disconnected {session.addr}: {e}")
        finally:
            self._remove_client(session)

    def _handle_udp_traffic(self):
        print(f"UDP Listener started on {self.udp_port}")
        while self.running:
            try:
                data, addr = self.udp_sock.recvfrom(65535)
                # print(f"Server received UDP from {addr}, len: {len(data)}")
                
                # Check if it's a Hello packet (JSON)
                try:
                    msg = json.loads(data.decode('utf-8'))
                    if msg.get('type') == 'HELLO':
                        username = msg.get('username')
                        with self.lock:
                            if username in self.clients:
                                self.clients[username].udp_addr = addr
                                print(f"Registered UDP for {username}: {addr}")
                        continue
                except:
                    pass # Not a JSON hello, likely media packet
                
                # Parse Media Packet
                parsed = Protocol.parse_udp_packet(data)
                if parsed:
                    packet_type, session_id, sender_id, sequence, payload = parsed
                    
                    # Find sender session by addr to verify identity (optional but good)
                    sender_session = None
                    with self.lock:
                        for s in self.clients.values():
                            if s.udp_addr == addr:
                                sender_session = s
                                break
                    
                    if sender_session:
                        # Rewrite Sender ID with trusted User ID from session
                        # This prevents spoofing
                        sender_id = sender_session.user_id
                        # print(f"Forwarding UDP from {sender_session.username} (ID: {sender_id})")
                        
                        # Re-pack with trusted sender_id
                        new_header = Protocol.create_udp_packet(packet_type, session_id, sender_id, sequence, b"")
                        forward_data = new_header + payload
                        
                        # Logic:
                        # If session_id matches a Group ID, forward to all group members.
                        # If session_id matches a Call ID (for 1-on-1), forward to partner.
                        
                        db = Database()
                        members = db.get_group_members(session_id)
                        
                        if members:
                            # It's a group! Forward to all members EXCEPT sender
                            with self.lock:
                                for uid in members:
                                    if uid != sender_session.user_id:
                                        # Find session for this uid
                                        target_session = None
                                        for s in self.clients.values():
                                            if s.user_id == uid:
                                                target_session = s
                                                break
                                        
                                        if target_session and target_session.udp_addr:
                                            self.udp_sock.sendto(forward_data, target_session.udp_addr)
                        else:
                            # Not a group, maybe 1-on-1 call?
                            # Fallback to old logic: check call_partner
                            if sender_session.call_partner and sender_session.call_partner.udp_addr:
                                self.udp_sock.sendto(forward_data, sender_session.call_partner.udp_addr)
                                # print(f"Forwarded to {sender_session.call_partner.username}")
                    else:
                        print(f"Unknown UDP sender: {addr}")

            except Exception as e:
                if self.running:
                    print(f"UDP Error: {e}")

    def _find_session_by_udp_addr(self, addr):
        with self.lock:
            for session in self.sessions:
                if session.udp_addr == addr:
                    return session
        return None

    def add_authenticated_client(self, session):
        with self.lock:
            self.clients[session.username] = session
            print(f"User {session.username} authenticated.")
        # Broadcast outside lock
        self._broadcast_user_list()

    def _remove_client(self, session):
        with self.lock:
            if session in self.sessions:
                self.sessions.remove(session)
            if session.username and session.username in self.clients:
                del self.clients[session.username]
                print(f"User {session.username} disconnected.")
        # Broadcast outside lock
        self._broadcast_user_list()

    def get_client(self, username):
        with self.lock:
            return self.clients.get(username)

    def get_online_users(self):
        with self.lock:
            return list(self.clients.keys())

    def _broadcast_user_list(self):
        # Get a snapshot of clients to avoid holding lock during I/O
        with self.lock:
            sessions = list(self.clients.values())
            users = list(self.clients.keys())
        
        for session in sessions:
            try:
                Protocol.send_tcp_message(session.conn, CMD_USER_LIST, {"users": users})
            except:
                pass
