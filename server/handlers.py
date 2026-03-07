import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.protocol import *
from server.database import Database

class HandlerFactory:
    @staticmethod
    def get_handler(cmd):
        if cmd in [CMD_LOGIN, CMD_REGISTER]:
            return AuthHandler()
        elif cmd in [CMD_CHAT_MSG, CMD_USER_LIST]:
            return ChatHandler()
        elif cmd in [CMD_FILE_OFFER, CMD_FILE_ACCEPT, CMD_FILE_REJECT, CMD_FILE_DATA]:
            return FileHandler()
        elif cmd in [CMD_CALL_INVITE, CMD_CALL_ACCEPT, CMD_CALL_REJECT, CMD_CALL_END]:
            return CallHandler()
        elif cmd in [CMD_GROUP_CREATE, CMD_GROUP_LIST, CMD_GROUP_MSG, CMD_GROUP_FILE_OFFER]:
            return GroupHandler()
        else:
            return None

class BaseHandler:
    def handle(self, server, session, cmd, data):
        pass

class AuthHandler(BaseHandler):
    def handle(self, server, session, cmd, data):
        db = Database()
        if cmd == CMD_REGISTER:
            success = db.register_user(data['username'], data['password'])
            if success:
                Protocol.send_tcp_message(session.conn, CMD_OK, {"message": "Registration successful"})
            else:
                Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "Username already exists"})
        elif cmd == CMD_LOGIN:
            user_id = db.login_user(data['username'], data['password'])
            if user_id:
                session.username = data['username']
                session.user_id = user_id
                server.add_authenticated_client(session)
                Protocol.send_tcp_message(session.conn, CMD_OK, {"message": "Login successful"})
                
                # Send Group List automatically
                groups = db.get_user_groups(user_id)
                Protocol.send_tcp_message(session.conn, CMD_GROUP_LIST, {"groups": groups})
            else:
                Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "Invalid credentials"})

class ChatHandler(BaseHandler):
    def handle(self, server, session, cmd, data):
        if not session.is_authenticated():
            Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "Not authenticated"})
            return

        if cmd == CMD_CHAT_MSG:
            target_username = data['to']
            message = data['message']
            target_session = server.get_client(target_username)
            if target_session:
                Protocol.send_tcp_message(target_session.conn, CMD_CHAT_MSG, {
                    "from": session.username,
                    "message": message
                })
            else:
                # Optionally store offline message
                Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "User not online"})
        
        elif cmd == CMD_USER_LIST:
            users = server.get_online_users()
            Protocol.send_tcp_message(session.conn, CMD_USER_LIST, {"users": users})

class FileHandler(BaseHandler):
    def handle(self, server, session, cmd, data):
        if not session.is_authenticated():
            return

        target_username = data.get('to')
        target_session = server.get_client(target_username)

        if cmd == CMD_FILE_OFFER:
            if target_session:
                # Forward offer to target
                Protocol.send_tcp_message(target_session.conn, CMD_FILE_OFFER, {
                    "from": session.username,
                    "filename": data['filename'],
                    "filesize": data['filesize']
                })
            else:
                Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "User not online"})
        
        elif cmd == CMD_FILE_ACCEPT:
            # Receiver accepted, notify sender to start sending
            sender_username = data['from'] # The original sender
            sender_session = server.get_client(sender_username)
            if sender_session:
                Protocol.send_tcp_message(sender_session.conn, CMD_FILE_ACCEPT, {
                    "from": session.username # The receiver who accepted
                })
        
        elif cmd == CMD_FILE_REJECT:
            sender_username = data['from']
            sender_session = server.get_client(sender_username)
            if sender_session:
                Protocol.send_tcp_message(sender_session.conn, CMD_FILE_REJECT, {
                    "from": session.username
                })

        elif cmd == CMD_FILE_DATA:
            # Forward file chunk
            if target_session:
                Protocol.send_tcp_message(target_session.conn, CMD_FILE_DATA, {
                    "from": session.username,
                    "data": data['data'], # Base64 encoded
                    "filename": data['filename']
                })

class CallHandler(BaseHandler):
    def handle(self, server, session, cmd, data):
        if not session.is_authenticated():
            return

        target_username = data.get('to')
        target_session = server.get_client(target_username)

        if cmd == CMD_CALL_INVITE:
            if target_session:
                if target_session.in_call_with:
                    Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "User is busy"})
                else:
                    Protocol.send_tcp_message(target_session.conn, CMD_CALL_INVITE, {
                        "from": session.username
                    })
            else:
                Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "User not online"})

        elif cmd == CMD_CALL_ACCEPT:
            caller_username = data['from']
            caller_session = server.get_client(caller_username)
            if caller_session:
                # Establish session
                session.in_call_with = caller_username
                caller_session.in_call_with = session.username
                
                # Set direct session references for UDP forwarding
                session.call_partner = caller_session
                caller_session.call_partner = session
                
                # Generate a unique session ID for UDP stream
                call_id = hash(session.username + caller_username) & 0xFFFFFFFF
                
                Protocol.send_tcp_message(caller_session.conn, CMD_CALL_ACCEPT, {
                    "from": session.username,
                    "call_id": call_id
                })
                Protocol.send_tcp_message(session.conn, CMD_CALL_ACCEPT, {
                    "from": caller_username, # Actually this is just ack, but let's keep it symmetric
                    "call_id": call_id
                })
        
        elif cmd == CMD_CALL_REJECT:
            caller_username = data['from']
            caller_session = server.get_client(caller_username)
            if caller_session:
                Protocol.send_tcp_message(caller_session.conn, CMD_CALL_REJECT, {
                    "from": session.username
                })

        elif cmd == CMD_CALL_END:
            # End call for both
            other_user = session.in_call_with
            if other_user:
                other_session = server.get_client(other_user)
                if other_session:
                    other_session.in_call_with = None
                    other_session.call_partner = None
                    Protocol.send_tcp_message(other_session.conn, CMD_CALL_END, {"from": session.username})
            session.in_call_with = None
            session.call_partner = None

class GroupHandler(BaseHandler):
    def handle(self, server, session, cmd, data):
        if not session.is_authenticated():
            return
        
        db = Database()

        if cmd == CMD_GROUP_LIST:
            groups = db.get_user_groups(session.user_id)
            Protocol.send_tcp_message(session.conn, CMD_GROUP_LIST, {"groups": groups})

        elif cmd == CMD_GROUP_CREATE:
            group_name = data['name']
            members = data['members'] # List of usernames
            
            # Add creator to members if not present
            if session.username not in members:
                members.append(session.username)
            
            # Resolve usernames to IDs
            member_ids = []
            for username in members:
                uid = db.get_user_id(username)
                if uid:
                    member_ids.append(uid)
            
            if not member_ids:
                Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "No valid members found"})
                return

            group_id = db.create_group(group_name, session.user_id)
            if group_id:
                for uid in member_ids:
                    db.add_group_member(group_id, uid)
                
                # Notify all members (if online) about the new group
                # We can just send a GROUP_LIST update or a specific NEW_GROUP event
                # For simplicity, let's just tell the creator it worked, and maybe others will see it on refresh
                # Better: Broadcast to online members
                for uid in member_ids:
                    # Find session
                    target_session = None
                    # This search is inefficient, but works for now
                    # Ideally server should have a map user_id -> session
                    for s in server.sessions:
                        if s.user_id == uid:
                            target_session = s
                            break
                    
                    if target_session:
                        # Send updated group list
                        groups = db.get_user_groups(uid)
                        Protocol.send_tcp_message(target_session.conn, CMD_GROUP_LIST, {"groups": groups})

            else:
                Protocol.send_tcp_message(session.conn, CMD_ERROR, {"message": "Failed to create group"})

        elif cmd == CMD_GROUP_MSG:
            group_id = data['group_id']
            message = data['message']
            
            # Verify membership
            # (Optional for speed, but good for security)
            
            # Broadcast to all members
            members = db.get_group_members(group_id)
            for uid in members:
                # Find session
                target_session = None
                for s in server.sessions:
                    if s.user_id == uid:
                        target_session = s
                        break
                
                if target_session:
                    Protocol.send_tcp_message(target_session.conn, CMD_GROUP_MSG, {
                        "group_id": group_id,
                        "from": session.username,
                        "message": message
                    })

        elif cmd == CMD_GROUP_FILE_OFFER:
            group_id = data['group_id']
            filename = data['filename']
            filesize = data['filesize']
            
            members = db.get_group_members(group_id)
            for uid in members:
                if uid == session.user_id:
                    continue # Don't send to self
                
                target_session = None
                for s in server.sessions:
                    if s.user_id == uid:
                        target_session = s
                        break
                
                if target_session:
                    Protocol.send_tcp_message(target_session.conn, CMD_GROUP_FILE_OFFER, {
                        "group_id": group_id,
                        "from": session.username,
                        "filename": filename,
                        "filesize": filesize
                    })
