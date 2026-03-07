class ClientSession:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.username = None
        self.user_id = None
        self.udp_addr = None  # To be set when UDP packet is received
        self.in_call_with = None # Username of the user they are in a call with
        self.call_partner = None # ClientSession object of the partner (for 1-on-1 UDP forwarding)

    def is_authenticated(self):
        return self.username is not None
