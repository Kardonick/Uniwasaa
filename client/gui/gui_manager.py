import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
from tkinter import ttk # Import ttk
from PIL import Image, ImageTk
import io
import base64
import threading
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from common.protocol import *

class GUIManager:
    def __init__(self, network_manager, video_manager, audio_manager):
        self.network_manager = network_manager
        self.video_manager = video_manager
        self.audio_manager = audio_manager
        self.network_manager.register_observer(self)
        
        self.root = tk.Tk()
        self.root.title("Uniwasa Client")
        self.root.geometry("450x650") # Slightly larger
        
        self._configure_styles() # Apply Dark Theme
        self.root.configure(bg='#2b2b2b')

        self.current_frame = None
        self.chat_windows = {} # username -> Toplevel
        self.group_windows = {} # group_id -> Toplevel
        self.call_window = None
        self.call_image_label = None
        
        self.users = []
        self.groups = [] # List of (id, name)
        self.pending_files = {} # target_user -> filepath (Sender side)
        self.incoming_files = {} # sender -> savepath (Receiver side)
        
        self.show_login()
        
    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam') # 'clam' allows easier color customization
        
        bg_color = '#2b2b2b'
        fg_color = '#ffffff'
        accent_color = '#007acc'
        entry_bg = '#3c3c3c'
        
        style.configure('.', background=bg_color, foreground=fg_color, font=('Segoe UI', 10))
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        style.configure('TButton', background=accent_color, foreground=fg_color, borderwidth=0, focuscolor=accent_color)
        style.map('TButton', background=[('active', '#005f9e')]) # Darker blue on hover
        
        style.configure('TEntry', fieldbackground=entry_bg, foreground=fg_color, insertcolor=fg_color)
        style.configure('TFrame', background=bg_color)
        
        # Configure standard widgets that don't have ttk equivalents or need manual config
        self.root.option_add('*Listbox*Background', entry_bg)
        self.root.option_add('*Listbox*Foreground', fg_color)
        self.root.option_add('*Listbox*selectBackground', accent_color)
        self.root.option_add('*Listbox*selectForeground', fg_color)
        
        self.root.option_add('*Text*Background', entry_bg)
        self.root.option_add('*Text*Foreground', fg_color)
        self.root.option_add('*Text*insertBackground', fg_color) # Cursor color

    def start(self):
        self.root.mainloop()

    def update(self, event, data):
        # OPTIMIZATION: Handle Audio directly in this thread (Network Thread)
        if event == "UDP_FRAME" and data['type'] == UDP_TYPE_AUDIO:
            self.audio_manager.play_audio(data['payload'])
            return

        # For everything else (GUI updates, Video), schedule on Main Thread
        self.root.after(0, lambda: self._handle_event(event, data))

    def _handle_event(self, event, data):
        print(f"Handling Event in Main Thread: {event}")
        if event == CMD_OK:
            if data.get('message') == "Login successful":
                print("Login successful, showing user list...")
                self.show_user_list()
            elif data.get('message') == "Registration successful":
                messagebox.showinfo("Success", "Registration successful! Please login.")
                self.show_login()
            elif "created" in data.get('message', ''):
                messagebox.showinfo("Success", data.get('message'))
        
        elif event == CMD_ERROR:
            messagebox.showerror("Error", data.get('message'))
        
        elif event == CMD_USER_LIST:
            self.users = data.get('users', [])
            if isinstance(self.current_frame, UserListFrame):
                self.current_frame.update_users(self.users)
        
        elif event == CMD_GROUP_LIST:
            self.groups = data.get('groups', [])
            if isinstance(self.current_frame, UserListFrame):
                self.current_frame.update_groups(self.groups)

        elif event == CMD_CHAT_MSG:
            sender = data['from']
            msg = data['message']
            self._open_chat_window(sender)
            self.chat_windows[sender].add_message(sender, msg)
        
        elif event == CMD_GROUP_MSG:
            group_id = data['group_id']
            sender = data['from']
            msg = data['message']
            self._open_group_window(group_id, f"Group {group_id}")
            self.group_windows[group_id].add_message(sender, msg)

        elif event == CMD_FILE_OFFER:
            sender = data['from']
            filename = data['filename']
            filesize = data['filesize']
            
            self._open_chat_window(sender)
            self.chat_windows[sender].add_message("System", f"{sender} offered file: {filename} ({filesize} bytes)")
            
            if messagebox.askyesno("File Transfer", f"{sender} wants to send {filename} ({filesize} bytes). Accept?"):
                save_path = filedialog.asksaveasfilename(initialfile=filename)
                if save_path:
                    self.incoming_files[sender] = save_path
                    self.network_manager.send_file_accept(sender)
                    self.chat_windows[sender].add_message("System", f"You accepted. Waiting for file...")
                else:
                    self.network_manager.send_file_reject(sender)
                    self.chat_windows[sender].add_message("System", "You cancelled the save dialog. Offer rejected.")
            else:
                self.network_manager.send_file_reject(sender)
                self.chat_windows[sender].add_message("System", "You rejected the file offer.")
        
        elif event == CMD_FILE_ACCEPT:
            receiver = data['from']
            self._open_chat_window(receiver)
            self.chat_windows[receiver].add_message("System", f"{receiver} accepted file. Sending...")
            
            filepath = self.pending_files.get(receiver)
            if filepath and os.path.exists(filepath):
                threading.Thread(target=self._send_file_thread, args=(receiver, filepath)).start()
            else:
                self.chat_windows[receiver].add_message("System", "Error: File not found or no pending file.")
        
        elif event == CMD_FILE_REJECT:
            sender = data['from']
            self._open_chat_window(sender)
            self.chat_windows[sender].add_message("System", f"{sender} rejected the file offer.")

        elif event == CMD_FILE_DATA:
            sender = data['from']
            file_data_b64 = data['data']
            filename = data['filename']
            
            save_path = self.incoming_files.get(sender)
            if save_path:
                try:
                    file_data = base64.b64decode(file_data_b64)
                    with open(save_path, 'wb') as f:
                        f.write(file_data)
                    
                    self._open_chat_window(sender)
                    self.chat_windows[sender].add_message("System", f"File received and saved to: {save_path}")
                    del self.incoming_files[sender]
                except Exception as e:
                    print(f"Error saving file: {e}")
                    self.chat_windows[sender].add_message("System", f"Error saving file: {e}")
            else:
                print(f"Received file data from {sender} but no save path found.")

        elif event == CMD_CALL_INVITE:
            sender = data['from']
            if messagebox.askyesno("Call Invite", f"{sender} is calling you. Accept?"):
                self.network_manager.send_call_accept(sender)
                self._start_call_ui(sender)
            else:
                self.network_manager.send_call_reject(sender)
        
        elif event == CMD_CALL_ACCEPT:
            sender = data['from']
            self._start_call_ui(sender)
        
        elif event == CMD_CALL_REJECT:
            messagebox.showinfo("Call", "Call rejected.")
            self._end_call_ui()
        
        elif event == CMD_CALL_END:
            messagebox.showinfo("Call", "Call ended.")
            self._end_call_ui()
            
        elif event == "UDP_FRAME":
            if self.call_window:
                packet_type = data['type']
                payload = data['payload']
                sender_id = data['sender_id']
                
                if packet_type == UDP_TYPE_VIDEO:
                    self._update_video_frame(payload, sender_id)

    def _send_file_thread(self, receiver, filepath):
        try:
            with open(filepath, 'rb') as f:
                file_data = f.read()
            
            b64_data = base64.b64encode(file_data).decode('utf-8')
            filename = os.path.basename(filepath)
            
            self.network_manager.send_file_data(receiver, filename, b64_data)
            
            self.root.after(0, lambda: self.chat_windows[receiver].add_message("System", "File sent successfully."))
        except Exception as e:
            print(f"Error sending file: {e}")
            self.root.after(0, lambda: self.chat_windows[receiver].add_message("System", f"Error sending file: {e}"))

    def _clear_frame(self):
        if self.current_frame:
            self.current_frame.destroy()

    def show_login(self):
        self._clear_frame()
        self.current_frame = LoginFrame(self.root, self)
        self.current_frame.pack(fill=tk.BOTH, expand=True)

    def show_register(self):
        self._clear_frame()
        self.current_frame = RegisterFrame(self.root, self)
        self.current_frame.pack(fill=tk.BOTH, expand=True)

    def show_user_list(self):
        self._clear_frame()
        self.current_frame = UserListFrame(self.root, self)
        self.current_frame.pack(fill=tk.BOTH, expand=True)

    def _open_chat_window(self, username):
        if username not in self.chat_windows or not tk.Toplevel.winfo_exists(self.chat_windows[username]):
            self.chat_windows[username] = ChatWindow(self.root, self, username)

    def _open_group_window(self, group_id, group_name):
        if group_id not in self.group_windows or not tk.Toplevel.winfo_exists(self.group_windows[group_id]):
            self.group_windows[group_id] = GroupChatWindow(self.root, self, group_id, group_name)

    def _start_call_ui(self, partner):
        if self.call_window:
            return
        self.call_window = tk.Toplevel(self.root)
        self.call_window.title(f"Call with {partner}")
        self.call_window.geometry("640x480")
        self.call_window.minsize(400, 300)
        self.call_window.configure(bg='#2b2b2b')
        
        # Main container for video grid
        self.video_frame = ttk.Frame(self.call_window)
        self.video_frame.pack(fill=tk.BOTH, expand=True)
        
        self.video_labels = {} # sender_id -> Label
        self.video_grid_cols = 2 # Max columns
        
        # Control buttons
        btn_frame = ttk.Frame(self.call_window)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="End Call", command=lambda: self._end_call_action(partner)).pack()
        
        # Start Media
        session_id = hash(partner) & 0xFFFFFFFF # Simplified
        
        def on_video_frame(frame):
            self.network_manager.send_udp_frame(UDP_TYPE_VIDEO, session_id, 0, frame)
            self.root.after(0, lambda: self._update_video_frame(frame, "Me"))

        self.video_manager.start_capture(on_video_frame)
        self.audio_manager.start_audio(lambda chunk: self.network_manager.send_udp_frame(UDP_TYPE_AUDIO, session_id, 0, chunk))

    def _end_call_action(self, partner):
        self.network_manager.send_call_end()
        self._end_call_ui()

    def _end_call_ui(self):
        try:
            print("Ending call UI...")
            self.video_manager.stop_capture()
            self.audio_manager.stop_audio()
            
            if self.call_window:
                try:
                    self.call_window.destroy()
                except Exception as e:
                    print(f"Error destroying call window: {e}")
                finally:
                    self.call_window = None
                    self.video_labels = {}
            print("Call UI ended successfully.")
        except Exception as e:
            print(f"Critical error in _end_call_ui: {e}")

    def _update_video_frame(self, frame_data, sender_id):
        if not self.call_window:
            return
            
        try:
            image = Image.open(io.BytesIO(frame_data))
            image.thumbnail((320, 240)) 
            photo = ImageTk.PhotoImage(image)
            
            if sender_id not in self.video_labels:
                # Create new label for this sender
                lbl = ttk.Label(self.video_frame, text=f"User {sender_id}", compound=tk.BOTTOM)
                
                # Calculate grid position
                count = len(self.video_labels)
                row = count // self.video_grid_cols
                col = count % self.video_grid_cols
                
                lbl.grid(row=row, column=col, padx=5, pady=5)
                self.video_labels[sender_id] = lbl
            
            lbl = self.video_labels[sender_id]
            lbl.config(image=photo)
            lbl.image = photo # Keep reference
            
        except Exception as e:
            print(f"Error updating video frame: {e}")

class LoginFrame(ttk.Frame):
    def __init__(self, master, manager):
        super().__init__(master)
        self.manager = manager
        
        # Center container
        container = ttk.Frame(self)
        container.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        ttk.Label(container, text="Uniwasa Login", font=('Segoe UI', 16, 'bold')).pack(pady=20)
        
        ttk.Label(container, text="Username").pack(anchor=tk.W)
        self.entry_user = ttk.Entry(container, width=30)
        self.entry_user.pack(pady=(0, 10))
        
        ttk.Label(container, text="Password").pack(anchor=tk.W)
        self.entry_pass = ttk.Entry(container, show="*", width=30)
        self.entry_pass.pack(pady=(0, 20))
        
        ttk.Button(container, text="Login", command=self.login).pack(fill=tk.X, pady=5)
        ttk.Button(container, text="Register", command=self.manager.show_register).pack(fill=tk.X)

    def login(self):
        user = self.entry_user.get()
        pwd = self.entry_pass.get()
        if user and pwd:
            self.manager.network_manager.login(user, pwd)

class RegisterFrame(ttk.Frame):
    def __init__(self, master, manager):
        super().__init__(master)
        self.manager = manager
        
        container = ttk.Frame(self)
        container.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        ttk.Label(container, text="Create Account", font=('Segoe UI', 16, 'bold')).pack(pady=20)
        
        ttk.Label(container, text="New Username").pack(anchor=tk.W)
        self.entry_user = ttk.Entry(container, width=30)
        self.entry_user.pack(pady=(0, 10))
        
        ttk.Label(container, text="New Password").pack(anchor=tk.W)
        self.entry_pass = ttk.Entry(container, show="*", width=30)
        self.entry_pass.pack(pady=(0, 20))
        
        ttk.Button(container, text="Create Account", command=self.register).pack(fill=tk.X, pady=5)
        ttk.Button(container, text="Back to Login", command=self.manager.show_login).pack(fill=tk.X)

    def register(self):
        user = self.entry_user.get()
        pwd = self.entry_pass.get()
        if user and pwd:
            self.manager.network_manager.register(user, pwd)

class UserListFrame(ttk.Frame):
    def __init__(self, master, manager):
        super().__init__(master)
        self.manager = manager
        
        self.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(self, text="Online Users", font=('Segoe UI', 12, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        self.listbox_users = tk.Listbox(self, height=10, borderwidth=0, highlightthickness=0)
        self.listbox_users.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        self.listbox_users.bind('<Double-Button-1>', self.on_select_user)
        
        ttk.Label(self, text="My Groups", font=('Segoe UI', 12, 'bold')).pack(anchor=tk.W, pady=(0, 5))
        self.listbox_groups = tk.Listbox(self, height=5, borderwidth=0, highlightthickness=0)
        self.listbox_groups.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        self.listbox_groups.bind('<Double-Button-1>', self.on_select_group)
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh_lists).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        ttk.Button(btn_frame, text="Create Group", command=self.create_group).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

    def refresh_lists(self):
        self.manager.network_manager.send_user_list_request()
        self.manager.network_manager.send_group_list_request()

    def update_users(self, users):
        self.listbox_users.delete(0, tk.END)
        for user in users:
            if user != self.manager.network_manager.username:
                self.listbox_users.insert(tk.END, user)

    def update_groups(self, groups):
        self.listbox_groups.delete(0, tk.END)
        for grp in groups:
            self.listbox_groups.insert(tk.END, f"{grp[1]} ({grp[0]})")

    def on_select_user(self, event):
        selection = self.listbox_users.curselection()
        if selection:
            user = self.listbox_users.get(selection[0])
            self.manager._open_chat_window(user)

    def on_select_group(self, event):
        selection = self.listbox_groups.curselection()
        if selection:
            item = self.listbox_groups.get(selection[0])
            try:
                group_name = item.rsplit(' (', 1)[0]
                group_id = int(item.rsplit(' (', 1)[1][:-1])
                self.manager._open_group_window(group_id, group_name)
            except:
                pass

    def create_group(self):
        dialog = tk.Toplevel(self)
        dialog.title("Create Group")
        dialog.geometry("300x400")
        dialog.configure(bg='#2b2b2b')
        
        container = ttk.Frame(dialog)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(container, text="Group Name:").pack(anchor=tk.W, pady=(0, 5))
        entry_name = ttk.Entry(container)
        entry_name.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(container, text="Select Members:").pack(anchor=tk.W, pady=(0, 5))
        
        listbox = tk.Listbox(container, selectmode=tk.MULTIPLE, bg='#3c3c3c', fg='#ffffff', borderwidth=0, highlightthickness=0)
        listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        users = self.listbox_users.get(0, tk.END)
        for user in users:
            listbox.insert(tk.END, user)
            
        def on_create():
            name = entry_name.get().strip()
            if not name:
                messagebox.showerror("Error", "Please enter a group name")
                return
            
            selected_indices = listbox.curselection()
            if not selected_indices:
                messagebox.showerror("Error", "Please select at least one member")
                return
            
            members = [listbox.get(i) for i in selected_indices]
            self.manager.network_manager.create_group(name, members)
            dialog.destroy()
            
        ttk.Button(container, text="Create", command=on_create).pack(fill=tk.X)

class ChatWindow(tk.Toplevel):
    def __init__(self, master, manager, target_user):
        super().__init__(master)
        self.manager = manager
        self.target_user = target_user
        self.title(f"Chat with {target_user}")
        self.geometry("400x500")
        self.configure(bg='#2b2b2b')
        
        self.text_area = tk.Text(self, state='disabled', bg='#3c3c3c', fg='#ffffff', borderwidth=0, highlightthickness=0, font=('Segoe UI', 10))
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        input_frame = ttk.Frame(self)
        input_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.entry_msg = ttk.Entry(input_frame)
        self.entry_msg.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))
        self.entry_msg.bind("<Return>", self.send_msg)
        
        ttk.Button(input_frame, text="Send", command=self.send_msg).pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(btn_frame, text="Send File", command=self.send_file).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        ttk.Button(btn_frame, text="Video Call", command=self.call).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

    def add_message(self, sender, msg):
        self.text_area.config(state='normal')
        self.text_area.insert(tk.END, f"[{sender}]: {msg}\n")
        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')

    def send_msg(self, event=None):
        msg = self.entry_msg.get()
        if msg:
            self.manager.network_manager.send_message(self.target_user, msg)
            self.add_message("Me", msg)
            self.entry_msg.delete(0, tk.END)

    def send_file(self):
        filename = filedialog.askopenfilename()
        if filename:
            filesize = os.path.getsize(filename)
            basename = os.path.basename(filename)
            self.manager.pending_files[self.target_user] = filename
            self.manager.network_manager.send_file_offer(self.target_user, basename, filesize)
            self.add_message("System", f"Offering file: {basename}")

    def call(self):
        self.manager.network_manager.send_call_invite(self.target_user)
        self.add_message("System", "Calling...")

class GroupChatWindow(tk.Toplevel):
    def __init__(self, master, manager, group_id, group_name):
        super().__init__(master)
        self.manager = manager
        self.group_id = group_id
        self.title(f"Group: {group_name}")
        self.geometry("400x500")
        self.configure(bg='#2b2b2b')
        
        self.text_area = tk.Text(self, state='disabled', bg='#3c3c3c', fg='#ffffff', borderwidth=0, highlightthickness=0, font=('Segoe UI', 10))
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        input_frame = ttk.Frame(self)
        input_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        self.entry_msg = ttk.Entry(input_frame)
        self.entry_msg.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))
        self.entry_msg.bind("<Return>", self.send_msg)
        
        ttk.Button(input_frame, text="Send", command=self.send_msg).pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(btn_frame, text="Send File", command=self.send_file).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))
        ttk.Button(btn_frame, text="Join Call", command=self.join_call).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))

    def add_message(self, sender, msg):
        self.text_area.config(state='normal')
        self.text_area.insert(tk.END, f"[{sender}]: {msg}\n")
        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')

    def send_msg(self, event=None):
        msg = self.entry_msg.get()
        if msg:
            self.manager.network_manager.send_group_message(self.group_id, msg)
            self.entry_msg.delete(0, tk.END)

    def send_file(self):
        filename = filedialog.askopenfilename()
        if filename:
            filesize = os.path.getsize(filename)
            basename = os.path.basename(filename)
            self.manager.network_manager.send_group_file_offer(self.group_id, basename, filesize)
            self.add_message("System", f"Offering file: {basename}")

    def join_call(self):
        self.manager._start_call_ui(f"Group {self.group_id}")
        session_id = self.group_id
        
        def on_video_frame(frame):
            self.manager.network_manager.send_udp_frame(UDP_TYPE_VIDEO, session_id, 0, frame)
            self.manager.root.after(0, lambda: self.manager._update_video_frame(frame, "Me"))

        self.manager.video_manager.start_capture(on_video_frame)
        self.manager.audio_manager.start_audio(lambda chunk: self.manager.network_manager.send_udp_frame(UDP_TYPE_AUDIO, session_id, 0, chunk))
