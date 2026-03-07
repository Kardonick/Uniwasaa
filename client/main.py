import configparser
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from client.network_manager import NetworkManager
from client.media.video_manager import VideoManager
from client.media.audio_manager import AudioManager
from client.gui.gui_manager import GUIManager

if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(__file__), '../config.ini'))
    
    host = config['SERVER']['host']
    # If host is 0.0.0.0, client should connect to localhost or specific IP.
    if host == '0.0.0.0':
        host = 'localhost'
        
    tcp_port = int(config['SERVER']['tcp_port'])
    udp_port = int(config['SERVER']['udp_port'])
    
    network_manager = NetworkManager()
    
    # Try connecting with config host first
    connected = network_manager.connect(host, tcp_port, udp_port)
    
    if not connected:
        print(f"Could not connect to {host}:{tcp_port}")
        # Fallback: Ask user for IP
        import tkinter as tk
        from tkinter import simpledialog
        
        root = tk.Tk()
        root.withdraw() # Hide main window
        
        new_host = simpledialog.askstring("Connection Error", f"Could not connect to {host}.\nPlease enter Server IP:", initialvalue=host)
        root.destroy()
        
        if new_host:
            host = new_host
            connected = network_manager.connect(host, tcp_port, udp_port)

    if connected:
        video_manager = VideoManager()
        audio_manager = AudioManager()
        
        gui = GUIManager(network_manager, video_manager, audio_manager)
        gui.start()
    else:
        print("Could not connect to server. Exiting.")
