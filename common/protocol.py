import struct
import json
import socket

# TCP Protocol Constants
HEADER_SIZE = 4

# Command Constants
CMD_LOGIN = "LOGIN"
CMD_REGISTER = "REGISTER"
CMD_CHAT_MSG = "CHAT_MSG"
CMD_FILE_OFFER = "FILE_OFFER"
CMD_FILE_ACCEPT = "FILE_ACCEPT"
CMD_FILE_REJECT = "FILE_REJECT"
CMD_FILE_DATA = "FILE_DATA"
CMD_CALL_INVITE = "CALL_INVITE"
CMD_CALL_ACCEPT = "CALL_ACCEPT"
CMD_CALL_REJECT = "CALL_REJECT"
CMD_CALL_END = "CALL_END"
CMD_USER_LIST = "USER_LIST"
CMD_ERROR = "ERROR"
CMD_OK = "OK"

# Group Commands
CMD_GROUP_CREATE = "GROUP_CREATE"
CMD_GROUP_LIST = "GROUP_LIST" # List groups user belongs to
CMD_GROUP_MSG = "GROUP_MSG"
CMD_GROUP_FILE_OFFER = "GROUP_FILE_OFFER"

# UDP Protocol Constants
UDP_TYPE_VIDEO = 0
UDP_TYPE_AUDIO = 1

class Protocol:
    @staticmethod
    def send_tcp_message(sock, cmd, data=None):
        """Sends a JSON message over TCP with a length header."""
        if data is None:
            data = {}
        payload = json.dumps({"cmd": cmd, "data": data}).encode('utf-8')
        length = len(payload)
        try:
            sock.sendall(struct.pack('!I', length) + payload)
        except Exception as e:
            print(f"Error sending TCP message: {e}")
            raise

    @staticmethod
    def receive_tcp_message(sock):
        """Receives a JSON message from TCP."""
        try:
            header = b""
            while len(header) < HEADER_SIZE:
                chunk = sock.recv(HEADER_SIZE - len(header))
                if not chunk:
                    return None
                header += chunk
            
            length = struct.unpack('!I', header)[0]
            
            payload = b""
            while len(payload) < length:
                chunk = sock.recv(min(4096, length - len(payload)))
                if not chunk:
                    raise ConnectionError("Socket closed mid-message")
                payload += chunk
            
            return json.loads(payload.decode('utf-8'))
        except Exception as e:
            print(f"Error receiving TCP message: {e}")
            return None

    @staticmethod
    def create_udp_packet(packet_type, session_id, sender_id, sequence, payload):
        """Creates a UDP packet for media streaming."""
        # Header: Type (1B) | Session ID (4B) | Sender ID (4B) | Sequence (8B)
        # Sender ID is added so clients know who is talking/showing video in a group call.
        header = struct.pack('!BIIQ', packet_type, session_id, sender_id, sequence)
        return header + payload

    @staticmethod
    def parse_udp_packet(data):
        """Parses a UDP packet."""
        if len(data) < 17: # 1+4+4+8
            return None
        header = data[:17]
        payload = data[17:]
        packet_type, session_id, sender_id, sequence = struct.unpack('!BIIQ', header)
        return packet_type, session_id, sender_id, sequence, payload
